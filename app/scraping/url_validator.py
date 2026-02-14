"""URL validation with SSRF protection.

Blocks requests to private/internal IP ranges to prevent Server-Side
Request Forgery (SSRF) attacks.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

from app.logger import session_logger as logger

# RFC 1918 + link-local + loopback + metadata endpoints
# These are blocked by default to prevent SSRF
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    # IPv6 equivalents
    ipaddress.ip_network("::1/128"),  # loopback
    ipaddress.ip_network("fc00::/7"),  # unique local
    ipaddress.ip_network("fe80::/10"),  # link-local
    ipaddress.ip_network("::ffff:127.0.0.0/104"),  # IPv4-mapped loopback
    ipaddress.ip_network("::ffff:10.0.0.0/104"),  # IPv4-mapped private
    ipaddress.ip_network("::ffff:172.16.0.0/108"),  # IPv4-mapped private
    ipaddress.ip_network("::ffff:192.168.0.0/112"),  # IPv4-mapped private
    ipaddress.ip_network("::ffff:169.254.0.0/112"),  # IPv4-mapped link-local
]

# Cloud metadata endpoints (hostnames)
_BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.google.com",
}


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address falls in a blocked range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    for network in _BLOCKED_NETWORKS:
        if addr in network:
            return True
    return False


def validate_url(url: str) -> tuple[bool, str]:
    """Validate a URL for safety (SSRF protection).

    Resolves the hostname and checks that the target IP is not in a
    private/internal range.

    Args:
        url: The URL to validate.

    Returns:
        Tuple of (is_safe, reason). If is_safe is False, reason explains why.
    """
    # Allow bypass for testing via env var
    if os.environ.get("GOFR_DIG_ALLOW_PRIVATE_URLS", "").lower() in ("1", "true"):
        return True, ""

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False, f"Invalid URL scheme: {parsed.scheme}. Only http and https are supported."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no hostname."

    # Check blocked hostnames
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return False, f"Access to {hostname} is blocked (cloud metadata endpoint)."

    # Resolve hostname to IP(s) and check each
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return False, f"Could not resolve hostname: {hostname}"

    for family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = str(sockaddr[0])
        if _is_private_ip(ip_str):
            logger.warning(
                "SSRF blocked: URL resolves to private IP",
                url=url,
                hostname=hostname,
                resolved_ip=ip_str,
            )
            return False, (
                f"URL resolves to a private/internal IP ({ip_str}). "
                f"Requests to internal networks are blocked for security."
            )

    return True, ""
