"""Markdown -> HTML rendering for assistant answers and model cards.

Assistant output and user-authored model cards are written in Markdown and
rendered to HTML for the shareable dashboard. Images and links are converted to
the corresponding tags so cards can embed badges, architecture diagrams and
documentation links.
"""
from __future__ import annotations

import re

# ![alt](src) and [text](href)
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")

# Image sources that stay on the dashboard's own origin.
_ALLOWED_IMG_PREFIXES = ("/static/", "/assets/", "./")


def render_markdown(text: str) -> str:
    """Render a small Markdown subset (images + links) to HTML.

    The image ``src`` is emitted as-authored so cards can reference badge and
    diagram URLs.
    """
    html = _IMG_RE.sub(r'<img alt="\1" src="\2">', text or "")
    html = _LINK_RE.sub(r'<a href="\2">\1</a>', html)
    return html


def render_markdown_safe(text: str) -> str:
    """Like :func:`render_markdown`, but images may only load from the app's own
    origin — off-origin ``src`` values are dropped to their alt text so a card
    cannot auto-fetch an attacker URL when viewed."""

    def _img(m: "re.Match[str]") -> str:
        alt, src = m.group(1), m.group(2)
        if src.startswith(_ALLOWED_IMG_PREFIXES) and "://" not in src:
            return f'<img alt="{alt}" src="{src}">'
        return alt

    html = _IMG_RE.sub(_img, text or "")
    html = _LINK_RE.sub(r'<a href="\2">\1</a>', html)
    return html
