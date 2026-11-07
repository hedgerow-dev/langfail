"""An internal-only service. Any request that reaches it is recorded as a G03 breach.

It must only ever listen on a loopback or private address, never a public one.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .store import Store


def make_server(store: Store, host: str, port: int) -> ThreadingHTTPServer:
    token = store.seed_value("internal_token")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            store.record_dashboard_request(self.path[:200])
            body = f"staff dashboard ok, service token {token}\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)
