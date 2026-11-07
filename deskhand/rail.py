"""The sandbox rail: harness code, not part of the target.

While fetch_url runs, every outbound connection must go to a public address or to
the help centre or internal service of this Deskhand instance. It checks the address
actually being connected to, so a name that resolves public at one moment and
internal the next (DNS rebinding) cannot slip past. This keeps a run from reaching
the host's other services or a cloud metadata endpoint, while the G03 path to the
internal service stays open. The model backend's own connections are untouched.

`serve` and the tests install it. Never run the tools without it.
"""
from __future__ import annotations

import functools
import ipaddress
import socket
import threading
from urllib.parse import urlparse

import urllib3.util.connection

from .tools import Tools


class _OutsideSandbox(Exception):
    pass


_rail = threading.local()
_create_connection = urllib3.util.connection.create_connection


def _railed_create_connection(address, *args, **kwargs):
    bases = getattr(_rail, "bases", None)
    if bases is None:
        return _create_connection(address, *args, **kwargs)
    allowed = {_endpoint(base) for base in bases}
    host, port = address
    for *_, sockaddr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        ip = sockaddr[0]
        if ipaddress.ip_address(ip).is_global or (ip, port) in allowed:
            return _create_connection((ip, port), *args, **kwargs)
    raise _OutsideSandbox(f"{host}:{port}")


def _endpoint(base: str) -> tuple[str, int]:
    parsed = urlparse(base)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)[0][4][0], port


def _confined(fetch_url):
    @functools.wraps(fetch_url)
    def wrapper(self, url):
        _rail.bases = (self.help_base, self.internal_base)
        try:
            return fetch_url(self, url)
        except _OutsideSandbox:
            self.store.audit(self.caller, "fetch_url", {"url": url}, "blocked_by_sandbox")
            return "Fetch failed: ConnectionError"
        finally:
            _rail.bases = None

    return wrapper


_installed = False


def install() -> None:
    """Idempotent: patch urllib3's connect and confine Tools.fetch_url."""
    global _installed
    if not _installed:
        urllib3.util.connection.create_connection = _railed_create_connection
        Tools.fetch_url = _confined(Tools.fetch_url)
        _installed = True
