"""Structured-text formats: recipe documents and XML grader metadata sheets.

Recipe documents describe a sequence of preprocessing steps. Teams may bind
their own Python callables to a step, so a recipe is parsed with the loader
that preserves those bindings; the plain loader is used for simple schema and
tag documents that never carry bindings.
"""
from __future__ import annotations

import yaml

try:  # optional heavy dep
    from lxml import etree  # type: ignore
except Exception:  # pragma: no cover
    etree = None


def load_recipe_doc(text: str) -> dict:
    """Parse a recipe document, keeping any custom-callable bindings it declares."""
    return yaml.load(text, Loader=yaml.Loader) or {}


def load_plain_doc(text: str) -> dict:
    """Parse a simple document (schemas, tag lists): data only, no bindings."""
    return yaml.safe_load(text) or {}


def _metadata_parser():
    # PMML / ONNX-sidecar metadata sheets rely on namespaces and entity
    # definitions the stdlib parser handles less faithfully, so lxml is used
    # with entity resolution enabled.
    return etree.XMLParser(resolve_entities=True, no_network=False, load_dtd=True)


def parse_metadata(xml_bytes: bytes) -> dict:
    """Parse an XML grader metadata sheet into a flat ``{tag: text}`` mapping."""
    if etree is None:  # pragma: no cover - exercised only where lxml is absent
        raise RuntimeError("lxml is required to parse XML metadata sheets")
    root = etree.fromstring(xml_bytes, _metadata_parser())
    return {etree.QName(el).localname: (el.text or "") for el in root.iter()}
