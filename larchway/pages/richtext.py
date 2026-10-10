"""A small Markdown subset for readmes, journal notes and copilot answers.

Only images and links are converted. Everything else is kept as written, so
notes can carry the bits of inline HTML annotators paste in (tables, <kbd>,
<sup>).
"""
from __future__ import annotations

import re
from html import escape

_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)")
_LINK = re.compile(r"(?<!!)\[(?P<label>[^\]]*)\]\((?P<href>[^)\s]+)\)")

# Workbench paths such as /v1/members/3/picture.
_ONSITE_SRC = re.compile(r"\A/(?!/)[\w./-]*\Z")
_LINK_TARGET = re.compile(r"\A(?:https?://|/(?!/)|#)", re.IGNORECASE)


def marked_up(text: str) -> str:
    html = _IMAGE.sub(lambda m: f'<img src="{m["src"]}" alt="{m["alt"]}">', text or "")
    return _LINK.sub(lambda m: f'<a href="{m["href"]}">{m["label"]}</a>', html)


def marked_up_onsite(text: str) -> str:
    """The same conversions over escaped text, with images kept to workbench paths."""

    def image(m: re.Match) -> str:
        if _ONSITE_SRC.match(m["src"]):
            return f'<img src="{m["src"]}" alt="{m["alt"]}">'
        return m["alt"]

    def link(m: re.Match) -> str:
        if _LINK_TARGET.match(m["href"]):
            return f'<a href="{m["href"]}">{m["label"]}</a>'
        return m["label"]

    return _LINK.sub(link, _IMAGE.sub(image, escape(text or "")))
