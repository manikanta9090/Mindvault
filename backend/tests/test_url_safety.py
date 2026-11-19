"""Tests for SSRF-oriented URL validation (no network access)."""

from __future__ import annotations

import socket

import pytest

from app.services import url_safety
from app.services.url_safety import (
    UnsafeUrlError,
    is_disallowed_ip,
    validate_url_target,
)

# Use literal, globally-routable IPs so validation never performs real DNS.
_PUBLIC_HTTP = "http://93.184.216.34/page"
_PUBLIC_HTTPS = "https://93.184.216.34/page"


def test_accepts_public_http_url_without_dns() -> None:
    parts = validate_url_target(_PUBLIC_HTTP)

    assert parts.scheme == "http"
    assert parts.hostname == "93.184.216.34"


def test_accepts_public_https_url_without_dns() -> None:
    parts = validate_url_target(_PUBLIC_HTTPS)

    assert parts.scheme == "https"


def test_accepts_public_port_and_path() -> None:
    parts = validate_url_target("https://93.184.216.34:8443/articles/1?q=2#frag")

    assert parts.port == 8443
    assert parts.path == "/articles/1"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/page",
        "http://localhost:8000/docs",
        "https://LOCALHOST./x",
        "http://foo.localhost/x",
        "http://localhost.localdomain/x",
    ],
)
def test_rejects_localhost_hostnames(url: str) -> None:
    with pytest.raises(UnsafeUrlError, match="Localhost"):
        validate_url_target(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.55/x",
        "https://[::1]/x",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/admin",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://0.0.0.0/",
        "http://224.0.0.1/",
        "http://240.0.0.1/",
        "http://100.64.0.1/",
        "https://[fd00::1]/",
        "https://[fe80::1]/",
        "https://[::ffff:127.0.0.1]/",
    ],
)
def test_rejects_disallowed_literal_addresses(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url_target(url)


def test_rejects_embedded_credentials() -> None:
    with pytest.raises(UnsafeUrlError, match="credentials"):
        validate_url_target("https://user:pass@93.184.216.34/page")

    with pytest.raises(UnsafeUrlError, match="credentials"):
        validate_url_target("https://user@93.184.216.34/page")


@pytest.mark.parametrize(
    "url",
    [
        "ftp://93.184.216.34/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
        "gopher://93.184.216.34/",
    ],
)
def test_rejects_non_http_protocols(url: str) -> None:
    with pytest.raises(UnsafeUrlError, match="HTTP"):
        validate_url_target(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com:0/",
        "https://example.com:99999/",
        "https://example.com:notaport/",
        "no-scheme-here",
        "http://",
        "https://93.184.216.34/\nHeader: injected",
    ],
)
def test_rejects_malformed_or_invalid_targets(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url_target(url)


def test_hostname_resolving_to_private_ip_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_safety, "resolve_host", lambda host, port: ["10.0.0.7"])

    with pytest.raises(UnsafeUrlError, match="non-public"):
        validate_url_target("https://public-looking.example/page")


def test_hostname_resolving_to_loopback_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_safety, "resolve_host", lambda host, port: ["127.0.0.1"])

    with pytest.raises(UnsafeUrlError, match="non-public"):
        validate_url_target("https://public-looking.example/page")


def test_redirect_to_internal_ip_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulates revalidating a redirect destination before following it.
    monkeypatch.setattr(url_safety, "resolve_host", lambda host, port: ["192.168.1.10"])

    with pytest.raises(UnsafeUrlError, match="non-public"):
        validate_url_target("http://redirect-target.example/internal")


def test_hostname_resolving_to_public_ip_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        url_safety, "resolve_host", lambda host, port: ["93.184.216.34", "8.8.8.8"]
    )

    parts = validate_url_target("https://public-looking.example/page")

    assert parts.hostname == "public-looking.example"


def test_dns_resolution_failure_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(host: str, port: int) -> list[str]:
        raise socket.gaierror("name resolution failed")

    monkeypatch.setattr(url_safety, "resolve_host", fail)

    with pytest.raises(UnsafeUrlError, match="could not be resolved"):
        validate_url_target("https://does-not-exist.example/page")


def test_empty_dns_result_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_safety, "resolve_host", lambda host, port: [])

    with pytest.raises(UnsafeUrlError, match="no addresses"):
        validate_url_target("https://no-addresses.example/page")


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "100.64.0.1",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_is_disallowed_ip_flags_internal_addresses(address: str) -> None:
    import ipaddress

    assert is_disallowed_ip(ipaddress.ip_address(address)) is True


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"])
def test_is_disallowed_ip_allows_public_addresses(address: str) -> None:
    import ipaddress

    assert is_disallowed_ip(ipaddress.ip_address(address)) is False
