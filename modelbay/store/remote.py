"""Remote import helper.

Downloads corpora and bundle artifacts referenced by URL. Imports are gated by
the platform's host allow-list (see :func:`modelbay.core.naming.host_allowed`).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests

from ..core.naming import host_allowed

MAX_BYTES = 512 * 1024 * 1024


def download(url: str, timeout: int = 15) -> bytes:
    """Fetch the bytes at ``url`` after validating it against the allow-list."""
    if not host_allowed(url):
        raise ValueError(f"host not allowed: {url}")
    resp = requests.get(url, timeout=timeout, stream=True, allow_redirects=True)
    resp.raise_for_status()
    chunks = bytearray()
    for chunk in resp.iter_content(64 * 1024):
        chunks.extend(chunk)
        if len(chunks) > MAX_BYTES:
            break
    return bytes(chunks)


def download_guarded(url: str, timeout: int = 15) -> bytes:
    """Fetch ``url`` with redirects disabled and private/loopback targets blocked.

    Resolves the host first and rejects any address that lands in a private,
    loopback, link-local or reserved range, closing the usual SSRF pivots.
    """
    host = urlparse(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve host: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"blocked non-public address: {ip}")
    resp = requests.get(url, timeout=timeout, allow_redirects=False)
    resp.raise_for_status()
    return resp.content[:MAX_BYTES]
