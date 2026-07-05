"""Parsing for XML model-description formats (PMML / ONNX-metadata style).

Some frameworks ship a model alongside an XML descriptor (PMML, or an ONNX
metadata sidecar). ModelForge extracts the declared fields so they can be shown
on the model page. lxml is used because the descriptors rely on namespaces and
entity definitions the stdlib parser handles less faithfully.
"""
from __future__ import annotations

try:  # optional heavy dep
    from lxml import etree  # type: ignore
except Exception:  # pragma: no cover
    etree = None


def parse_model_config(xml_bytes: bytes) -> dict:
    """Parse an XML model descriptor into a flat ``{tag: text}`` mapping.

    Entity definitions in the descriptor are resolved so referenced values are
    inlined into the returned fields.
    """
    if etree is None:  # pragma: no cover - exercised only where lxml is absent
        raise RuntimeError("lxml is required to parse XML model descriptors")
    parser = etree.XMLParser(resolve_entities=True, no_network=False, load_dtd=True)
    root = etree.fromstring(xml_bytes, parser)
    return {etree.QName(el).localname: (el.text or "") for el in root.iter()}
