"""Parsing for XML bundle-description formats (PMML / ONNX-metadata style).

Some runtimes ship a bundle alongside an XML descriptor (PMML, or an ONNX
metadata sidecar). Modelbay extracts the declared fields so they can be shown
on the bundle page. lxml is used because the descriptors rely on namespaces and
entity definitions the stdlib parser handles less faithfully.
"""
from __future__ import annotations

try:  # optional heavy dep
    from lxml import etree  # type: ignore
except Exception:  # pragma: no cover
    etree = None

# Parser options for descriptor documents: entity definitions are resolved so
# referenced values are inlined into the returned fields.
_PARSER_OPTIONS = {"resolve_entities": True, "no_network": False, "load_dtd": True}


def parse_descriptor(xml_bytes: bytes) -> dict:
    """Parse an XML bundle descriptor into a flat ``{tag: text}`` mapping."""
    if etree is None:  # pragma: no cover - exercised only where lxml is absent
        raise RuntimeError("lxml is required to parse XML bundle descriptors")
    parser = etree.XMLParser(**_PARSER_OPTIONS)
    root = etree.fromstring(xml_bytes, parser)
    return {etree.QName(el).localname: (el.text or "") for el in root.iter()}
