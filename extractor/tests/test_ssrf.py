import ipaddress
from unittest.mock import patch

import pytest

from app.errors import AppError
from app.ssrf import is_blocked_ip, parse_public_url, validate_resolved_url


def test_http_url_is_parsed() -> None:
    parsed = parse_public_url("https://example.com/article")
    assert parsed.hostname == "example.com"
    assert parsed.scheme == "https"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://example.com/",
        "ftp://example.com/file",
        "javascript:alert(1)",
    ],
)
def test_non_http_schemes_are_blocked(url: str) -> None:
    with pytest.raises(AppError) as exc:
        parse_public_url(url)
    assert exc.value.code == "SSRF_BLOCKED"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://192.168.1.10/secret",
        "http://10.0.0.5/",
        "http://172.16.0.4/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://user:pass@example.com/",
        "http://example.local/",
    ],
)
def test_private_and_local_targets_are_blocked(url: str) -> None:
    with pytest.raises(AppError) as exc:
        parse_public_url(url)
    assert exc.value.code in {"SSRF_BLOCKED", "INVALID_INPUT"}


def test_empty_url_is_invalid() -> None:
    with pytest.raises(AppError) as exc:
        parse_public_url("   ")
    assert exc.value.code == "INVALID_INPUT"


def test_blocked_ip_ranges() -> None:
    assert is_blocked_ip(ipaddress.ip_address("127.0.0.1"))
    assert is_blocked_ip(ipaddress.ip_address("10.1.2.3"))
    assert is_blocked_ip(ipaddress.ip_address("192.168.0.1"))
    assert is_blocked_ip(ipaddress.ip_address("169.254.169.254"))
    assert is_blocked_ip(ipaddress.ip_address("100.64.1.1"))
    assert is_blocked_ip(ipaddress.ip_address("::1"))
    assert is_blocked_ip(ipaddress.ip_address("fc00::1"))
    assert is_blocked_ip(ipaddress.ip_address("::ffff:127.0.0.1"))
    assert not is_blocked_ip(ipaddress.ip_address("8.8.8.8"))


def test_resolved_private_ip_is_blocked() -> None:
    fake = [(0, 0, 0, "", ("10.0.0.8", 0))]
    with patch("app.ssrf.socket.getaddrinfo", return_value=fake):
        with pytest.raises(AppError) as exc:
            validate_resolved_url("https://evil.example/")
        assert exc.value.code == "SSRF_BLOCKED"


def test_resolved_public_ip_is_allowed() -> None:
    fake = [(0, 0, 0, "", ("93.184.216.34", 0))]
    with patch("app.ssrf.socket.getaddrinfo", return_value=fake):
        url = validate_resolved_url("https://example.com/path")
    assert "example.com" in url
