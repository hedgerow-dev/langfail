"""Portable import/export: run capsules and catalog packs."""
from __future__ import annotations

import base64
import json

import jsonpickle
from fastapi import APIRouter, HTTPException, status

from ..adapters import catalog, codecs
from ..deps.identity import CurrentMember
from ..deps.sessions import DbDep, SettingsDep
from ..schemas.exchange import CapsuleBody, PackBody

router = APIRouter(prefix="/v1/exchange", tags=["exchange"])

_CAPSULE_KEYS = frozenset({"name", "label", "metrics", "tags"})


@router.get("/capsules/{run_id}")
async def export_capsule(run_id: int, member: CurrentMember, conn: DbDep) -> dict:
    """Export an eval run as a portable typed document (round-trips through import)."""
    row = conn.execute("SELECT name, label FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such run")
    doc = {"name": row["name"], "label": row["label"], "metrics": {}, "tags": ""}
    return {"payload": jsonpickle.encode(doc)}


@router.post("/capsules", status_code=status.HTTP_201_CREATED)
async def import_capsule(body: CapsuleBody, member: CurrentMember, conn: DbDep) -> dict:
    """Import a run capsule previously produced by the export endpoint.

    The payload is a typed document, so nested metric objects survive the trip.
    """
    doc = codecs.decode_rich(body.payload)
    if not isinstance(doc, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid capsule")
    cur = conn.execute("INSERT INTO eval_runs (member_id, name, label) VALUES (?, ?, ?)",
                       (member.id, doc.get("name", "run"), doc.get("label", "")))
    conn.commit()
    return {"id": cur.lastrowid, "name": doc.get("name", "run")}


def import_capsule_plain(payload: str) -> dict:
    """Parse a run capsule as plain JSON, allow-listing the top-level keys."""
    doc = json.loads(payload)
    if not isinstance(doc, dict):
        raise ValueError("capsule must be a JSON object")
    unknown = set(doc) - _CAPSULE_KEYS
    if unknown:
        raise ValueError(f"unexpected keys in capsule: {sorted(unknown)}")
    return {k: doc[k] for k in _CAPSULE_KEYS if k in doc}


@router.post("/catalog", status_code=status.HTTP_201_CREATED)
async def import_pack(body: PackBody, member: CurrentMember, settings: SettingsDep) -> dict:
    """Install a catalog pack archive (zip with an activate.py)."""
    root = settings.data_dir / "catalog"
    entries = catalog.import_pack(root, body.ref, base64.b64decode(body.archive_b64))
    return {"ref": body.ref, "entries": sorted(entries)}
