"""Outbound HTTP: artifact downloads, collection intake downloads, and callbacks."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

# Hosts artifact imports may be pulled from. The netloc may carry a port.
IMPORT_ORIGINS = ("objects.larchway.test", "hf.co")


def _listed(url: str) -> bool:
    netloc = urlsplit(url).netloc.lower()
    return any(netloc.startswith(origin) for origin in IMPORT_ORIGINS)


def fetch(url: str) -> bytes:
    """Download the bytes at ``url`` from one of the import origins."""
    if not _listed(url):
        raise ValueError(f"not an import origin: {url}")
    response = httpx.get(url, timeout=10.0, follow_redirects=True)
    response.raise_for_status()
    return response.content


def fetch_public(url: str) -> bytes:
    """Download ``url`` only if every address its host resolves to is public.

    Redirects are not followed, so a public host cannot bounce the request
    somewhere internal.
    """
    host = urlsplit(url).hostname or ""
    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve {host}") from exc
    for entry in resolved:
        address = ipaddress.ip_address(entry[4][0])
        if not address.is_global:
            raise ValueError(f"{host} resolves to a non-public address")
    response = httpx.get(url, timeout=10.0, follow_redirects=False)
    response.raise_for_status()
    return response.content


async def post_json(url: str, body: dict) -> None:
    """POST ``body`` to ``url``; callbacks are best effort."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            await http.post(url, json=body)
    except httpx.HTTPError:
        pass
