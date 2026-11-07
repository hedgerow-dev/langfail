"""The tools the Deskhand assistant can call, on behalf of the signed-in user.

Every call is written to the audit table with the caller's tenant and, where a row
is read, the row's tenant.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from urllib.parse import urlparse

import requests

from .store import Store

_ADDRESS_RE = re.compile(r"[a-z0-9._+-]+@([a-z0-9-]+(?:\.[a-z0-9-]+)+)")

SPECS = [
    {
        "name": "list_tickets",
        "description": "List the support tickets of the user's organisation.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_ticket",
        "description": "Read one support ticket. tenant_id is only needed by support staff handling an "
        "escalation for another organisation; leave it out otherwise.",
        "parameters": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "tenant_id": {"type": "string"}},
            "required": ["ticket_id"],
        },
    },
    {
        "name": "search_docs",
        "description": "Search the organisation's uploaded documents. Returns ids and titles.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "get_document",
        "description": "Read one of the organisation's documents in full.",
        "parameters": {"type": "object", "properties": {"doc_id": {"type": "integer"}}, "required": ["doc_id"]},
    },
    {
        "name": "add_document",
        "description": "Upload a document to the organisation's knowledge base.",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
            "required": ["title", "body"],
        },
    },
    {
        "name": "send_email",
        "description": "Email a colleague in the user's organisation.",
        "parameters": {
            "type": "object",
            "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "share_document",
        "description": "Send a document to a colleague by email.",
        "parameters": {
            "type": "object",
            "properties": {"doc_id": {"type": "integer"}, "to": {"type": "string"}},
            "required": ["doc_id", "to"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch a public web page, for example a help-centre article, and return its text.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
]


class Tools:
    def __init__(self, store: Store, caller, help_base: str, internal_base: str):
        self.store = store
        self.caller = caller  # a users row joined with its tenant (store.user)
        self.help_base = help_base.rstrip("/")
        self.internal_base = internal_base.rstrip("/")

    def call(self, name: str, args: dict) -> str:
        if name not in {s["name"] for s in SPECS}:
            return f"error: unknown tool {name}"
        try:
            return getattr(self, name)(**args)
        except Exception as exc:  # the model chose the arguments: report, never crash the request
            return f"error: bad arguments for {name}: {type(exc).__name__}"

    def list_tickets(self) -> str:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT id, subject, status FROM tickets WHERE tenant_id = ?", (self.caller["tenant_id"],)
            ).fetchall()
        self.store.audit(self.caller, "list_tickets", {}, "ok", self.caller["tenant_id"])
        return "\n".join(f"{r['id']} [{r['status']}] {r['subject']}" for r in rows) or "No tickets."

    def get_ticket(self, ticket_id: str, tenant_id: str | None = None) -> str:
        # Escalation support: staff pass the other organisation's tenant_id.
        tenant = tenant_id or self.caller["tenant_id"]
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE id = ? AND tenant_id = ?", (ticket_id, tenant)
            ).fetchone()
        args = {"ticket_id": ticket_id, "tenant_id": tenant_id}
        if row is None:
            self.store.audit(self.caller, "get_ticket", args, "not_found")
            return "Ticket not found."
        self.store.audit(self.caller, "get_ticket", args, "ok", row["tenant_id"])
        return f"{row['id']} [{row['status']}] {row['subject']}\n{row['body']}"

    def search_docs(self, query: str) -> str:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT id, title FROM documents WHERE tenant_id = ? AND (title LIKE ? OR body LIKE ?)",
                (self.caller["tenant_id"], f"%{query}%", f"%{query}%"),
            ).fetchall()
        self.store.audit(self.caller, "search_docs", {"query": query}, "ok", self.caller["tenant_id"])
        return "\n".join(f"{r['id']}: {r['title']}" for r in rows) or "No documents found."

    def get_document(self, doc_id: int) -> str:
        row = self._own_document(doc_id)
        if row is None:
            self.store.audit(self.caller, "get_document", {"doc_id": doc_id}, "not_found")
            return "Document not found."
        self.store.audit(self.caller, "get_document", {"doc_id": doc_id}, "ok", row["tenant_id"])
        return f"{row['title']}\n\n{row['body']}"

    def add_document(self, title: str, body: str) -> str:
        with self.store.connect() as conn:
            cur = conn.execute(
                "INSERT INTO documents (tenant_id, title, body, uploaded_by) VALUES (?, ?, ?, ?)",
                (self.caller["tenant_id"], title[:200], body[:20000], self.caller["email"]),
            )
        self.store.audit(self.caller, "add_document", {"title": title}, "ok", self.caller["tenant_id"])
        return f"Uploaded as document {cur.lastrowid}."

    def send_email(self, to: str, subject: str, body: str) -> str:
        args = {"to": to, "subject": subject}
        if not self._in_org(to):
            self.store.audit(self.caller, "send_email", args, "denied_external")
            return "Refused: email can only go to addresses in your organisation."
        self._deliver(to, subject[:200], body[:20000], "send_email")
        self.store.audit(self.caller, "send_email", args, "sent")
        return f"Sent to {to}."

    def share_document(self, doc_id: int, to: str) -> str:
        row = self._own_document(doc_id)
        args = {"doc_id": doc_id, "to": to}
        if row is None:
            self.store.audit(self.caller, "share_document", args, "not_found")
            return "Document not found."
        self._deliver(to, f"Shared: {row['title']}", row["body"], "share_document")
        self.store.audit(self.caller, "share_document", args, "sent", row["tenant_id"])
        return f"Shared '{row['title']}' with {to}."

    def fetch_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            self.store.audit(self.caller, "fetch_url", {"url": url}, "denied_scheme")
            return "Refused: only http and https URLs."
        # The help centre is ours, so it skips the address check. Everything else must
        # resolve to a public address.
        if not url.startswith(self.help_base + "/") and not _resolves_public(parsed.hostname):
            self.store.audit(self.caller, "fetch_url", {"url": url}, "denied_internal")
            return "Refused: that address is not public."
        try:
            resp = requests.get(url, timeout=5, stream=True)
            with resp:
                raw = resp.raw.read(16000, decode_content=True)
        except requests.RequestException as exc:
            self.store.audit(self.caller, "fetch_url", {"url": url}, "error")
            return f"Fetch failed: {type(exc).__name__}"
        self.store.audit(self.caller, "fetch_url", {"url": url, "final": resp.url}, f"status_{resp.status_code}")
        return raw.decode(resp.encoding or "utf-8", errors="replace")[:4000]

    def _own_document(self, doc_id):
        with self.store.connect() as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE id = ? AND tenant_id = ?", (doc_id, self.caller["tenant_id"])
            ).fetchone()

    def _in_org(self, address: str) -> bool:
        match = _ADDRESS_RE.fullmatch(address.strip().lower())
        return bool(match) and match.group(1) == self.caller["domain"]

    def _deliver(self, to: str, subject: str, body: str, via: str) -> None:
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO outbox (ts, sender, recipient, subject, body, via) VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), self.caller["email"], to.strip(), subject, body, via),
            )


def _resolves_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)
