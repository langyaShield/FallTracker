"""
HTTP fetcher for the radar crawler.

Dual-engine strategy:
1. curl_cffi (fast, lightweight) — TLS fingerprint impersonation
2. Playwright + Chromium (heavy, full browser) — fallback for JS-rendered pages

负责：从目标 URL 抓取 HTML，智能提取页面内容（HTML→Markdown），支持重试/退避/SSRF防护。

AI驱动模式：爬虫只负责抓取页面和基础噪声过滤，所有内容解析交给 LLM 完成。
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from typing import Dict, Optional, Tuple

from bs4 import BeautifulSoup, Tag
from curl_cffi import requests as curl_requests

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

# 抓取引擎标识
FETCH_ENGINE = "curl_cffi / Playwright (auto fallback)"

# 记录实际使用的引擎（供测试面板展示）
_engine_used: str = ""


def get_last_engine() -> str:
    """返回最近一次抓取使用的引擎。"""
    return _engine_used


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


def _check_ssrf(url: str) -> Optional[str]:
    """Check if URL targets internal/private network. Returns error message or None."""
    import ipaddress
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    _BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "::1"}
    if hostname.lower() in _BLOCKED_HOSTS:
        return "(目标地址为内网地址，不允许访问)"
    try:
        import socket
        resolved_ip = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(resolved_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return "(目标地址为内网地址，不允许访问)"
    except (socket.gaierror, ValueError):
        pass
    return None


# ─────────────────────────────────────────────
#  Engine 1: curl_cffi (fast TLS fingerprint)
# ─────────────────────────────────────────────


def fetch_html_curl(url: str, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[str, int, str]:
    """Fetch raw HTML using curl_cffi with Chrome 120 TLS fingerprint impersonation.

    Returns (html, status_code, error_reason).
    """
    url = _normalize_url(url)
    ssrf_err = _check_ssrf(url)
    if ssrf_err:
        return ("", 0, ssrf_err)

    last_error = ""

    for attempt in range(_MAX_RETRIES):
        try:
            headers = build_headers(extra_headers=extra_headers)
            session = curl_requests.Session()
            resp = session.get(
                url,
                headers=headers,
                timeout=25.0,
                allow_redirects=True,
                impersonate="chrome120",
            )
            status = resp.status_code

            if status == 403:
                return ("", 403, "(HTTP 403 Forbidden)")
            if status == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else _RETRY_DELAY_BASE ** attempt
                time.sleep(wait)
                continue
            if status == 503:
                time.sleep(_RETRY_DELAY_BASE ** attempt)
                continue
            if status >= 400:
                return ("", status, f"(HTTP {status})")

            html_body = resp.text
            if "<title>Just a moment...</title>" in html_body or "cf-challenge" in html_body.lower():
                return ("", 0, "(被 Cloudflare 拦截)")

            # Check if content looks like an empty SPA shell
            if _is_empty_shell(html_body):
                return ("", status, "(页面需要 JS 渲染)")

            return (html_body, status, "")

        except curl_requests.RequestsError as e:
            last_error = f"(请求失败: {str(e)[:100]})"
            logger.warning("curl_cffi failed (attempt %s/%s): %s", attempt + 1, _MAX_RETRIES, e)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_BASE ** attempt)
                continue
            return ("", 0, last_error)
        except Exception as e:
            last_error = f"(请求失败: {str(e)[:100]})"
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_BASE ** attempt)
                continue
            return ("", 0, last_error)

    return ("", 0, last_error)


def _is_empty_shell(html: str) -> bool:
    """Detect if HTML is an empty SPA shell (needs JS to render content).

    Checks for common patterns:
    - Very short body with only a root div (e.g., <div id="app"></div>)
    - React/Vue/Angular root elements without content
    """
    if not html or len(html) < 500:
        return True
    try:
        soup = BeautifulSoup(html, "lxml")
        body = soup.select_one("body")
        if not body:
            return False
        text = body.get_text(strip=True)
        # If body text is very short (< 100 chars), likely a JS shell
        if len(text) < 100:
            return True
        # Check for common SPA root patterns
        root = soup.select_one("#app, #root, [data-reactroot], [ng-app]")
        if root and len(root.get_text(strip=True)) < 50:
            return True
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────
#  Engine 2: Playwright + Chromium (full browser)
# ─────────────────────────────────────────────


async def _fetch_with_playwright_async(url: str, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[str, int, str]:
    """Fetch page using Playwright + headless Chromium.

    Renders JavaScript, handles redirects, waits for network idle.
    Returns (html, status_code, error_reason).
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ("", 0, "(Playwright 未安装)")

    url = _normalize_url(url)
    ssrf_err = _check_ssrf(url)
    if ssrf_err:
        return ("", 0, ssrf_err)

    browser = None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-translate",
                "--disable-extensions",
                "--disable-default-apps",
                "--mute-audio",
                "--no-first-run",
                "--disable-breakpad",
                "--disable-component-update",
                "--disable-domain-reliability",
                "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
                "--disable-hang-monitor",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--metrics-recording-only",
                "--no-pings",
                "--password-store=basic",
                "--use-mock-keychain",
                "--export-tagged-pdf",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
            ],
        )

        context = await browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            ignore_https_errors=True,
            extra_http_headers=extra_headers or {},
        )

        page = await context.new_page()

        # Block unnecessary resources to speed up loading
        await page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot,css,mp4,webm}", lambda route: route.abort())
        await page.route("**/google-analytics.com/**", lambda route: route.abort())
        await page.route("**/googletagmanager.com/**", lambda route: route.abort())

        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=30000)
            status = resp.status if resp else 0

            # Wait a bit for any deferred rendering
            await asyncio.sleep(2)

            html_body = await page.content()

            if "<title>Just a moment...</title>" in html_body or "cf-challenge" in html_body.lower():
                return ("", 0, "(被 Cloudflare 人机验证拦截)")

            return (html_body, status, "")

        except Exception as e:
            error_msg = str(e)[:100]
            if "timeout" in error_msg.lower():
                return ("", 0, "(页面加载超时)")
            return ("", 0, f"(浏览器渲染失败: {error_msg})")
        finally:
            await context.close()

    except Exception as e:
        return ("", 0, f"(Playwright 启动失败: {str(e)[:100]})")
    finally:
        if browser:
            await browser.close()


def _fetch_with_playwright_sync(url: str, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[str, int, str]:
    """Synchronous wrapper for Playwright fetch."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running in async context (e.g., FastAPI event loop)
            # Create a new loop in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    lambda: asyncio.run(_fetch_with_playwright_async(url, extra_headers))
                )
                return future.result(timeout=60)
        else:
            return asyncio.run(_fetch_with_playwright_async(url, extra_headers))
    except RuntimeError:
        return asyncio.run(_fetch_with_playwright_async(url, extra_headers))


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

    if name in _NOISE_TAGS:
        return ""
    if _is_noise_element(tag):
        return ""

    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(name[1])
        text = tag.get_text(strip=True)
        if text:
            return f"\n{'#' * level} {text}\n"
        return ""

    if name == "a":
        text = tag.get_text(strip=True)
        href = tag.get("href", "")
        if text and href:
            return f"[{text}]({href})"
        return text

    if name == "li":
        inner = _children_to_markdown(tag, depth)
        return f"- {inner.strip()}\n"

    if name in ("strong", "b"):
        text = tag.get_text(strip=True)
        return f"**{text}**" if text else ""
    if name in ("em", "i"):
        text = tag.get_text(strip=True)
        return f"*{text}*" if text else ""

    if name == "table":
        return _table_to_markdown(tag)

    if name in ("p", "div", "section", "article", "main", "span", "dd", "dt", "dl"):
        inner = _children_to_markdown(tag, depth)
        if name in ("p",):
            return f"\n{inner.strip()}\n"
        return inner

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

    title_tag = soup.select_one("title")
    if title_tag and title_tag.get_text(strip=True):
        parts.append(f"# {title_tag.get_text(strip=True)}")

    meta_desc = soup.select_one('meta[name="description"]')
    if not meta_desc:
        meta_desc = soup.select_one('meta[property="og:description"]')
    if meta_desc and meta_desc.get("content", "").strip():
        parts.append(f"> {meta_desc['content'].strip()}\n")

    body = soup.select_one("body")
    if body:
        for tag in body.select(", ".join(_NOISE_TAGS)):
            tag.decompose()
        for tag in body.find_all(True):
            if _is_noise_element(tag):
                tag.decompose()

        markdown = _tag_to_markdown(body)
        if markdown.strip():
            parts.append(markdown)

    content = "\n".join(parts)
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r' {2,}', ' ', content)

    if not content.strip():
        return ("", 200, "(未提取到页面内容)")

    if len(content) > MAX_RAW_TEXT_CHARS:
        content = content[:MAX_RAW_TEXT_CHARS] + "\n...(内容过长已截断)"

    return (content, 200, "")


# ─────────────────────────────────────────────
#  Main Entrypoint: Dual-Engine Strategy
# ─────────────────────────────────────────────


def fetch_page(url: str, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[str, int, str]:
    """Fetch page with dual-engine strategy.

    Step 1: curl_cffi (fast, lightweight TLS fingerprint impersonation)
    Step 2: Playwright + Chromium (full browser, fallback for JS-rendered pages)

    Returns (content, status_code, error_reason).
    - content: Markdown-formatted page content, or empty string on failure
    - status_code: HTTP status code (0 if connection error)
    - error_reason: detailed error message if failed, empty string on success
    """
    global _engine_used

    # Step 1: curl_cffi fast fetch
    html_body, status, error = fetch_html_curl(url, extra_headers=extra_headers)
    if html_body and not error:
        _engine_used = "curl_cffi"
        content, _, extract_error = smart_extract(html_body)
        if content and not extract_error:
            return (content, status, "")
        # If extraction produced nothing useful, try browser
        logger.info("curl_cffi got HTML but extraction was empty for %s, trying Playwright", url)

    # Step 2: Playwright browser fallback
    logger.info("curl_cffi failed for %s (error: %s), falling back to Playwright", url, error)
    html_body, status, browser_error = _fetch_with_playwright_sync(url, extra_headers=extra_headers)
    if html_body and not browser_error:
        _engine_used = "Playwright"
        content, _, extract_error = smart_extract(html_body)
        if content and not extract_error:
            return (content, status, "")
        return ("", status, f"(Playwright 提取失败: {extract_error})")

    _engine_used = "failed"
    return ("", status, browser_error or error or "(抓取失败)")


def fetch_page_curl_only(url: str, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[str, int, str]:
    """Fetch page using curl_cffi only (no Playwright fallback).

    For scenarios where we want to avoid the heavy browser overhead.
    """
    global _engine_used
    html_body, status, error = fetch_html_curl(url, extra_headers=extra_headers)
    if error:
        _engine_used = "curl_cffi (failed)"
        return ("", status, error)
    if not html_body:
        _engine_used = "curl_cffi (empty)"
        return ("", status, error or "(页面内容为空)")
    _engine_used = "curl_cffi"
    return smart_extract(html_body)


def fetch_page_browser_only(url: str, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[str, int, str]:
    """Fetch page using Playwright only (skip curl_cffi).

    For testing the browser engine directly.
    """
    global _engine_used
    html_body, status, error = _fetch_with_playwright_sync(url, extra_headers=extra_headers)
    if error:
        _engine_used = "Playwright (failed)"
        return ("", status, error)
    if not html_body:
        _engine_used = "Playwright (empty)"
        return ("", status, "(页面内容为空)")
    _engine_used = "Playwright"
    return smart_extract(html_body)
