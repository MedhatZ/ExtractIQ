from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.errors import invalid_input, ssrf_blocked

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.google",
    "instance-data",
}
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home")
CGNAT = ipaddress.ip_network("100.64.0.0/10")
MAX_URL_LENGTH = 2048


def _normalize_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address):
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    ip = _normalize_ip(ip)
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return True
    if ip in CGNAT:
        return True
    return False


def is_blocked_hostname(hostname: str) -> bool:
    host = hostname.strip(".").lower()
    if not host:
        return True
    if host in BLOCKED_HOSTNAMES:
        return True
    return any(host.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES)


def parse_public_url(raw: str):
    if not isinstance(raw, str) or not raw.strip():
        raise invalid_input("url is required")
    if len(raw) > MAX_URL_LENGTH:
        raise invalid_input("url exceeds the maximum length of 2048 characters")

    parsed = urlparse(raw.strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ssrf_blocked("only http and https URLs are allowed")
    if parsed.username or parsed.password:
        raise ssrf_blocked("URLs with credentials are not allowed")
    if not parsed.hostname:
        raise invalid_input("url must include a hostname")
    if parsed.port == 0:
        raise ssrf_blocked("invalid port")

    hostname = parsed.hostname.lower()
    if is_blocked_hostname(hostname):
        raise ssrf_blocked("hostname is not allowed")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and is_blocked_ip(literal_ip):
        raise ssrf_blocked("IP address is not allowed")

    return parsed


def resolve_hostname(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ssrf_blocked(f"hostname could not be resolved: {hostname}") from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        raw_ip = sockaddr[0]
        try:
            ip = ipaddress.ip_address(raw_ip.split("%")[0])
        except ValueError:
            continue
        key = str(ip)
        if key in seen:
            continue
        seen.add(key)
        addresses.append(ip)
    if not addresses:
        raise ssrf_blocked(f"hostname resolved to no usable addresses: {hostname}")
    return addresses


def validate_resolved_url(raw: str) -> str:
    parsed = parse_public_url(raw)
    hostname = parsed.hostname
    assert hostname is not None
    try:
        literal_ip = ipaddress.ip_address(hostname)
        ips = [literal_ip]
    except ValueError:
        ips = resolve_hostname(hostname)
    blocked = [str(ip) for ip in ips if is_blocked_ip(ip)]
    if blocked:
        raise ssrf_blocked("URL resolves to a private or reserved address")
    return parsed.geturl()
