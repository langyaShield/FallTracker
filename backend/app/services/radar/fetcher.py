"""
HTTP fetcher for the radar crawler.

负责：从目标 URL 抓取 HTML，提取正文文本，支持 CSS 选择器与重试/退避。

拆分为单一职责的子函数便于测试与复用：
- build_headers: 构造浏览器请求头
- fetch_html: 拉取 HTML 原始字符串（含重试）
- extract_text: 从 HTML 中按 CSS 选择器或全页提取文本
- fetch_page: 顶层组合函数，保留原 (content, status, error) 三元组接口
"""
from __future__ import annotations

import logging
import random
import re
import time
from typing import Tuple

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("falltracker.radar.fetcher")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Maximum number of retries for fetch failures
_MAX_RETRIES = 3
_RETRY_DELAY_BASE = 1.5  # seconds, exponential backoff
# 单次抓取最大保存字符数，避免 LLM 输入过长导致成本飙升
MAX_RAW_TEXT_CHARS = 10000


def build_headers(referer: str = "") -> dict:
    """Build a realistic browser request header set."""
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
    return headers


def _normalize_url(url: str) -> str:
    """Auto-prepend https:// if no scheme is present."""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def fetch_html(url: str) -> Tuple[str, int, str]:
    """Fetch raw HTML with retry / backoff. Returns (html, status_code, error_reason).

    Distinguishes recoverable vs terminal failures:
    - 429 / 503 with Retry-After: retry with backoff
    - 403: terminal (anti-bot)
    - Cloudflare challenge: terminal
    """
    url = _normalize_url(url)
    last_error = ""

    for attempt in range(_MAX_RETRIES):
        try:
            headers = build_headers()
            with httpx.Client(
                timeout=25.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5),
            ) as client:
                resp = client.get(url, headers=headers)
                status = resp.status_code

                # 403 — terminal, no retry
                if status == 403:
                    return ("", 403, "(HTTP 403 Forbidden — 站点拒绝访问，可能需要更换 IP 或使用代理)")
                # 429 — rate limited, wait and retry
                if status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else _RETRY_DELAY_BASE ** attempt
                    time.sleep(wait)
                    continue
                # 503 — temporary outage, retry
                if status == 503:
                    time.sleep(_RETRY_DELAY_BASE ** attempt)
                    continue
                # 4xx/5xx — terminal
                if status >= 400:
                    return ("", status, f"(HTTP {status} — 请求失败)")

                html_body = resp.text
                # Detect common bot-challenge pages
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


def _extract_by_selector(soup: BeautifulSoup, css_selector: str, status: int) -> Tuple[str, int, str]:
    """Extract text from elements matched by a CSS selector.

    Returns ("", status, error) on no match, (content, status, "") on success.
    """
    elements = soup.select(css_selector)
    if not elements:
        return ("", status, "(CSS选择器未匹配到任何元素)")
    texts = [el.get_text(strip=True) for el in elements]
    texts = [t for t in texts if t]
    if not texts:
        return ("", status, "(CSS选择器未匹配到任何文本内容)")
    return ("\n---\n".join(texts), status, "")


def _extract_full_page(soup: BeautifulSoup, status: int) -> Tuple[str, int, str]:
    """Extract a structured summary of the page: title / meta description / body text.

    Strips <script>, <style>, navigation, and collapses excessive whitespace.
    """
    parts: list[str] = []
    title_tag = soup.select_one("title")
    if title_tag and title_tag.get_text(strip=True):
        parts.append(f"标题: {title_tag.get_text(strip=True)}")
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get("content", "").strip():
        parts.append(f"页面标题: {og_title['content'].strip()}")

    meta_desc = soup.select_one('meta[name="description"]')
    if meta_desc and meta_desc.get("content"):
        parts.append(f"描述: {meta_desc['content'].strip()}")
    else:
        og_desc = soup.select_one('meta[property="og:description"]')
        if og_desc and og_desc.get("content"):
            parts.append(f"描述: {og_desc['content'].strip()}")

    body = soup.select_one("body")
    if body:
        for tag in body.select("script, style, nav, footer, header, iframe, noscript, svg"):
            tag.decompose()
        body_text = body.get_text(separator="\n", strip=True)
        body_text = re.sub(r'\n{3,}', '\n\n', body_text)
        if len(body_text) > 8000:
            body_text = body_text[:8000] + "\n...(内容过长已截断)"
        parts.append(body_text)

    content = "\n\n".join(parts)
    if not content.strip():
        return ("", status, "(未提取到页面内容)")
    return (content, status, "")


def extract_text(html_body: str, css_selector: str, status: int) -> Tuple[str, int, str]:
    """Parse HTML and extract content. Dispatches to selector or full-page extractor."""
    try:
        soup = BeautifulSoup(html_body, "lxml")
    except Exception as e:
        logger.exception("BeautifulSoup parse failed: %s", e)
        return ("", 0, "(页面解析失败)")

    if css_selector:
        return _extract_by_selector(soup, css_selector, status)
    return _extract_full_page(soup, status)


def fetch_page(url: str, css_selector: str = "") -> Tuple[str, int, str]:
    """Top-level entrypoint: fetch HTML then extract text content.

    Returns (content, status_code, error_reason).
    - content: extracted text, or empty string on failure
    - status_code: HTTP status code (0 if connection error)
    - error_reason: detailed error message if failed, empty string on success
    """
    html_body, status, error = fetch_html(url)
    if error:
        return ("", status, error)
    if not html_body:
        return ("", status, error or "(页面内容为空)")
    return extract_text(html_body, css_selector, status)
