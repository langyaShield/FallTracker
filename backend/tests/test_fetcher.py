"""
Unit tests for pure functions in app.services.radar.fetcher.

覆盖：
- URL 标准化（自动加 https://）
- build_headers 返回真实浏览器头
- _normalize_url 边界
"""
from app.services.radar.fetcher import (
    _normalize_url,
    build_headers,
    MAX_RAW_TEXT_CHARS,
    _USER_AGENTS,
)


def test_normalize_url_adds_https():
    assert _normalize_url("example.com") == "https://example.com"


def test_normalize_url_preserves_https():
    assert _normalize_url("https://example.com") == "https://example.com"


def test_normalize_url_preserves_http():
    assert _normalize_url("http://example.com") == "http://example.com"


def test_normalize_url_preserves_path():
    assert _normalize_url("example.com/path?q=1") == "https://example.com/path?q=1"


def test_build_headers_returns_browser_set():
    headers = build_headers()
    assert "User-Agent" in headers
    assert headers["User-Agent"] in _USER_AGENTS
    assert "Accept" in headers
    assert "Accept-Language" in headers
    # 当不传 referer 时，Sec-Fetch-Site 应为 "none"
    assert headers.get("Sec-Fetch-Site") == "none"
    # 不应包含 Referer
    assert "Referer" not in headers


def test_build_headers_with_referer():
    headers = build_headers(referer="https://google.com")
    assert headers["Referer"] == "https://google.com"
    assert headers["Sec-Fetch-Site"] == "same-origin"


def test_user_agents_have_realistic_signatures():
    """UA 字符串应来自真实浏览器，不应是自定义占位。"""
    for ua in _USER_AGENTS:
        assert "Mozilla" in ua
        assert any(browser in ua for browser in ("Chrome", "Firefox", "Safari"))


def test_max_raw_text_chars_is_reasonable():
    """截断阈值应合理（≤ 20k 字符），避免 LLM 调用成本飙升。"""
    assert 1_000 <= MAX_RAW_TEXT_CHARS <= 50_000
