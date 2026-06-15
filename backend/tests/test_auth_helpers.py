"""
Unit tests for pure auth helpers (no DB needed).

覆盖：
- bcrypt 72 字节截断（B-10）
- password verify 一致性
- 极短/极长密码边界
- 中文 UTF-8 密码（多字节字符）
"""
from app.auth import _truncate_password, get_password_hash, verify_password


def test_bcrypt_short_password_unchanged():
    """Short passwords (≤72 bytes) pass through unchanged."""
    pwd = "a" * 60
    assert _truncate_password(pwd) == pwd


def test_bcrypt_at_boundary():
    """72 bytes exactly should NOT be truncated."""
    pwd = "a" * 72
    assert _truncate_password(pwd) == pwd


def test_bcrypt_over_boundary_truncated():
    """73+ bytes should be truncated to 72 bytes (B-10 fix)."""
    pwd = "a" * 100
    out = _truncate_password(pwd)
    assert len(out.encode("utf-8")) == 72
    assert out == "a" * 72


def test_bcrypt_chinese_password_bytewise():
    """Chinese chars (3 bytes each in UTF-8) are truncated at byte level, not char count."""
    pwd = "密码" * 50  # 100 chars * 3 bytes = 300 bytes
    out = _truncate_password(pwd)
    assert len(out.encode("utf-8")) <= 72
    # 72 / 3 = 24 chars
    assert out == "密码" * 12
    assert len(out.encode("utf-8")) == 72


def test_password_hash_and_verify_round_trip():
    """Hashing then verifying should return True for the same password."""
    pwd = "MySecureP@ssw0rd!"
    h = get_password_hash(pwd)
    assert verify_password(pwd, h) is True


def test_password_verify_wrong_password():
    """A different password should not verify."""
    pwd = "correct_password"
    h = get_password_hash(pwd)
    assert verify_password("wrong_password", h) is False


def test_long_password_consistent_hash():
    """B-10: Long passwords (>72 bytes) should still verify consistently after truncation."""
    pwd = "x" * 200
    h = get_password_hash(pwd)
    assert verify_password(pwd, h) is True
    # 即使再次传入超过 72 字节的同样字符串，也应通过
    assert verify_password("x" * 300, h) is True


def test_empty_string_password():
    """Empty string is a valid (if inadvisable) password."""
    pwd = ""
    h = get_password_hash(pwd)
    assert verify_password(pwd, h) is True
    assert verify_password("not_empty", h) is False
