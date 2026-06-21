"""
HTTP fetcher for the radar crawler.

负责：从目标 URL 抓取 HTML，智能提取页面内容（HTML→Markdown），支持重试/退避/SSRF防护。

AI驱动模式：爬虫只负责抓取页面和基础噪声过滤，所有内容解析交给 LLM 完成。
"""
from __future__ import annotations

import logging
import random
import re
import time
from typing import Dict, Optional, Tuple

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("falltracker.radar.fetcher")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

_MAX_RETRIES = 3
_RETRY_DELAY_BASE = 1.5
# AI驱动模式下，LLM上下文窗口足够大，可以保留更多内容
MAX_RAW_TEXT_CHARS = 15000


def build_headers(referer: str = "", extra_headers: Optional[Dict[str, str]] = None) -> dict:
    """Build a realistic browser request header set, with optional extra headers (e.g. Cookie)."""
    ua = random.choice(_USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "max-age=0",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _normalize_url(url: str) -> str:
    """Auto-prepend https:// if no scheme is present."""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def fetch_html(url: str, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[str, int, str]:
    """Fetch raw HTML with retry / backoff. Returns (html, status_code, error_reason)."""
    url = _normalize_url(url)
    # SSRF protection: block private/internal network addresses
    import ipaddress
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    _BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "::1"}
    if hostname.lower() in _BLOCKED_HOSTS:
        return ("", 0, "(目标地址为内网地址，不允许访问)")
    try:
        import socket
        resolved_ip = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(resolved_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return ("", 0, "(目标地址为内网地址，不允许访问)")
    except (socket.gaierror, ValueError):
        pass
    last_error = ""

    for attempt in range(_MAX_RETRIES):
        try:
            headers = build_headers(extra_headers=extra_headers)
            with httpx.Client(
                timeout=25.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5),
            ) as client:
                resp = client.get(url, headers=headers)
                status = resp.status_code

                if status == 403:
                    return ("", 403, "(HTTP 403 Forbidden — 站点拒绝访问，可能需要更换 IP 或使用代理)")
                if status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else _RETRY_DELAY_BASE ** attempt
                    time.sleep(wait)
                    continue
                if status == 503:
                    time.sleep(_RETRY_DELAY_BASE ** attempt)
                    continue
                if status >= 400:
                    return ("", status, f"(HTTP {status} — 请求失败)")

                html_body = resp.text
                if "<title>Just a moment...</title>" in html_body or "cf-challenge" in html_body.lower():
                    return ("", 0, "(被 Cloudflare 人机验证拦截，该站点需要浏览器环境拿不到)")

                return (html_body, status, "")

        except httpx.TimeoutException:
            last_error = "(请求超时)"
            time.sleep(_RETRY_DELAY_BASE ** attempt)
            continue
        except httpx.ConnectError:
            return ("", 0, "(无法连接目标站点)")
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (429, 503) and attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_BASE ** attempt)
                continue
            return ("", status, f"(HTTP {status} — {str(e)[:100]})")
        except Exception as e:
            last_error = f"(页面请求失败: {str(e)[:100]})"
            logger.warning("HTTP request failed (attempt %s/%s) for %s: %s", attempt + 1, _MAX_RETRIES, url, e)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_BASE ** attempt)
                continue
            return ("", 0, last_error)

    return ("", 0, last_error)


# ─────────────────────────────────────────────
#  Smart Extract: HTML → Markdown (AI-driven)
# ─────────────────────────────────────────────

# Tags to completely remove (noise / non-content)
_NOISE_TAGS = {"script", "style", "nav", "footer", "header", "iframe", "noscript", "svg",
               "aside", "form", "button", "input", "select", "textarea", "label",
               "img", "video", "audio", "canvas", "map", "area"}

# CSS class/id keywords indicating ads/popups/cookies
_NOISE_CLASS_KEYWORDS = {"ad", "banner", "popup", "modal", "cookie", "consent",
                          "sidebar", "widget", "social", "share", "comment",
                          "disclaimer", "notification-bar", "top-bar"}


def _is_noise_element(tag: Tag) -> bool:
    """Check if an element is likely noise (ad, popup, sidebar, etc.)."""
    try:
        classes = " ".join(tag.get("class", []) or [])
        elem_id = tag.get("id", "") or ""
        combined = (classes + " " + elem_id).lower()
        return any(kw in combined for kw in _NOISE_CLASS_KEYWORDS)
    except (AttributeError, TypeError):
        return False


def _tag_to_markdown(tag: Tag, depth: int = 0) -> str:
    """Recursively convert a BeautifulSoup tag tree to lightweight Markdown."""
    if not isinstance(tag, Tag):
        return str(tag).strip()

    name = tag.name.lower()

    # Skip noise tags entirely
    if name in _NOISE_TAGS:
        return ""
    if _is_noise_element(tag):
        return ""

    # Headings
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(name[1])
        text = tag.get_text(strip=True)
        if text:
            return f"\n{'#' * level} {text}\n"
        return ""

    # Links — preserve href for LLM to extract
    if name == "a":
        text = tag.get_text(strip=True)
        href = tag.get("href", "")
        if text and href:
            return f"[{text}]({href})"
        return text

    # List items
    if name == "li":
        inner = _children_to_markdown(tag, depth)
        return f"- {inner.strip()}\n"

    # Bold / italic
    if name in ("strong", "b"):
        text = tag.get_text(strip=True)
        return f"**{text}**" if text else ""
    if name in ("em", "i"):
        text = tag.get_text(strip=True)
        return f"*{text}*" if text else ""

    # Table — simple text rendering
    if name == "table":
        return _table_to_markdown(tag)

    # Paragraphs / divs / spans — just render children with spacing
    if name in ("p", "div", "section", "article", "main", "span", "dd", "dt", "dl"):
        inner = _children_to_markdown(tag, depth)
        if name in ("p",):
            return f"\n{inner.strip()}\n"
        return inner

    # For other tags, just render children
    return _children_to_markdown(tag, depth)


def _children_to_markdown(tag: Tag, depth: int = 0) -> str:
    """Convert all children of a tag to Markdown."""
    parts = []
    for child in tag.children:
        if isinstance(child, Tag):
            parts.append(_tag_to_markdown(child, depth + 1))
        else:
            text = str(child).strip()
            if text:
                parts.append(text)
    return " ".join(p for p in parts if p)


def _table_to_markdown(table: Tag) -> str:
    """Convert a simple HTML table to text-based Markdown."""
    rows = []
    for tr in table.select("tr"):
        cells = []
        for cell in tr.select("td, th"):
            cells.append(cell.get_text(strip=True))
        if cells:
            rows.append(" | ".join(cells))
    if not rows:
        return ""
    return "\n" + "\n".join(rows) + "\n"


def smart_extract(html_body: str) -> Tuple[str, int, str]:
    """AI-driven content extraction: HTML → Markdown with noise removal.

    Preserves semantic structure (headings, links, lists) for LLM to understand.
    Returns (markdown_content, status_code, error_reason).
    """
    try:
        soup = BeautifulSoup(html_body, "lxml")
    except Exception as e:
        logger.exception("BeautifulSoup parse failed: %s", e)
        return ("", 0, "(页面解析失败)")

    parts = []

    # Extract page title
    title_tag = soup.select_one("title")
    if title_tag and title_tag.get_text(strip=True):
        parts.append(f"# {title_tag.get_text(strip=True)}")

    # Extract meta description
    meta_desc = soup.select_one('meta[name="description"]')
    if not meta_desc:
        meta_desc = soup.select_one('meta[property="og:description"]')
    if meta_desc and meta_desc.get("content", "").strip():
        parts.append(f"> {meta_desc['content'].strip()}\n")

    # Extract body content
    body = soup.select_one("body")
    if body:
        # Remove noise tags first
        for tag in body.select(", ".join(_NOISE_TAGS)):
            tag.decompose()
        # Remove noise elements by class/id
        for tag in body.find_all(True):
            if _is_noise_element(tag):
                tag.decompose()

        markdown = _tag_to_markdown(body)
        if markdown.strip():
            parts.append(markdown)

    content = "\n".join(parts)

    # Clean up excessive whitespace
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r' {2,}', ' ', content)

    if not content.strip():
        return ("", 200, "(未提取到页面内容)")

    # Truncate to max length
    if len(content) > MAX_RAW_TEXT_CHARS:
        content = content[:MAX_RAW_TEXT_CHARS] + "\n...(内容过长已截断)"

    return (content, 200, "")


def fetch_page(url: str, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[str, int, str]:
    """Top-level entrypoint: fetch HTML then smart-extract to Markdown.

    Returns (content, status_code, error_reason).
    - content: Markdown-formatted page content, or empty string on failure
    - status_code: HTTP status code (0 if connection error)
    - error_reason: detailed error message if failed, empty string on success
    """
    html_body, status, error = fetch_html(url, extra_headers=extra_headers)
    if error:
        return ("", status, error)
    if not html_body:
        return ("", status, error or "(页面内容为空)")
    return smart_extract(html_body)
