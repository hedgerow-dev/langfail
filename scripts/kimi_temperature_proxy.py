#!/usr/bin/env python3
"""Local proxy that forces temperature=1 on every request before forwarding to
Kimi's coding-platform API (https://api.kimi.com/coding/v1) -- the only value
its k3 model accepts, which open-rowan's CLI can't override (it hardcodes 0.1
with no flag). Point open-rowan's generic `local` backend at this proxy
instead of directly at Kimi:

    export KIMI_API_KEY=sk-kimi-...
    python scripts/kimi_temperature_proxy.py &
    LOCAL_LLM_BASE_URL=http://127.0.0.1:8934 LOCAL_LLM_MODEL=k3 \\
        LOCAL_LLM_API_KEY=unused open-rowan hunt <target> --backend local
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

KIMI_KEY = os.environ["KIMI_API_KEY"]
UPSTREAM = os.environ.get("KIMI_BASE_URL", "https://api.kimi.com/coding/v1")
PORT = int(os.environ.get("PROXY_PORT", "8934"))
FORCED_TEMPERATURE = float(os.environ.get("FORCED_TEMPERATURE", "1"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet -- avoid echoing request bodies (may contain source snippets)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        body["temperature"] = FORCED_TEMPERATURE
        resp = requests.post(
            f"{UPSTREAM}{self.path}",
            headers={"Authorization": f"Bearer {KIMI_KEY}", "Content-Type": "application/json"},
            json=body,
            timeout=280,
        )
        self.send_response(resp.status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp.content)

    def do_GET(self):
        resp = requests.get(f"{UPSTREAM}{self.path}",
                            headers={"Authorization": f"Bearer {KIMI_KEY}"}, timeout=30)
        self.send_response(resp.status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp.content)


if __name__ == "__main__":
    print(f"Kimi temperature-fixing proxy listening on http://127.0.0.1:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
