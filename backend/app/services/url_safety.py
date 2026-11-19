"""SSRF-oriented validation for user-supplied URLs.

This module performs pre-connect validation: scheme and credential checks,
hostname checks, and DNS resolution with classification of every resolved
address. It never opens a network connection itself.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Final
from urllib.parse import SplitResult, urlsplit

_ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})
_LOCALHOST_NAMES: Final[frozenset[str]] = frozenset({"localhost", "localhost.localdomain"})


class UnsafeUrlError(ValueError):
    """A URL must not be fetched (invalid target or disallowed destination)."""


def is_disallowed_ip(address: ipaddress._BaseAddress) -> bool:
    """Return True for any address that must never be used for outbound fetches."""

    # IPv4-mapped IPv6 addresses can smuggle an IPv4 literal past v6-only checks.
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        return is_disallowed_ip(mapped)

    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    )


def resolve_host(host: str, port: int) -> list[str]:
    """Resolve a hostname to its IP strings, failing closed on resolution errors."""

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise UnsafeUrlError("The URL host could not be resolved.") from exc

    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise UnsafeUrlError("The URL host has no addresses.")
    return addresses


def validate_url_target(url: str, *, resolve: bool = True) -> SplitResult:
    """Validate ``url`` and its resolved addresses; return the parsed URL.

    ``resolve=False`` is only for validating literal IP URLs or for callers
    that supply their own address information.
    """

    if not isinstance(url, str) or any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise UnsafeUrlError("The URL is malformed.")

    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError("Only HTTP and HTTPS URLs are supported.")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError("URLs with embedded credentials are not allowed.")

    host = parts.hostname
    if not host:
        raise UnsafeUrlError("The URL must include a host.")

    try:
        explicit_port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("The URL port is invalid.") from exc
    port = explicit_port if explicit_port is not None else (
        443 if parts.scheme.lower() == "https" else 80
    )
    if not 1 <= port <= 65535:
        raise UnsafeUrlError("The URL port is invalid.")

    normalized_host = host.lower().rstrip(".")
    if normalized_host in _LOCALHOST_NAMES or normalized_host.endswith(".localhost"):
        raise UnsafeUrlError("Localhost targets are not allowed.")

    try:
        literal = ipaddress.ip_address(normalized_host)
    except ValueError:
        literal = None

    if literal is not None:
        if is_disallowed_ip(literal):
            raise UnsafeUrlError("The URL host is not a public address.")
        return parts

    if resolve:
        try:
            addresses = resolve_host(normalized_host, port)
        except UnsafeUrlError:
            raise
        except OSError as exc:
            # socket.gaierror is an OSError; fail closed on any resolution error.
            raise UnsafeUrlError("The URL host could not be resolved.") from exc

        if not addresses:
            raise UnsafeUrlError("The URL host has no addresses.")

        for address in addresses:
            try:
                resolved_ip = ipaddress.ip_address(address)
            except ValueError as exc:
                raise UnsafeUrlError("The URL host resolved to an invalid address.") from exc
            if is_disallowed_ip(resolved_ip):
                raise UnsafeUrlError("The URL host resolves to a non-public address.")

    return parts
