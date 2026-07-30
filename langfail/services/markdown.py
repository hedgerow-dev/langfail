"""Markdown -> HTML rendering for assistant answers and model cards.

Assistant output and user-authored model cards are written in Markdown and
rendered to HTML for the shareable dashboard. Images and links are converted to
the corresponding tags so cards can embed badges, architecture diagrams and
documentation links.
"""
from __future__ import annotations

import re
from html import escape

# ![alt](src) and [text](href)
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")

# Image sources that stay on the dashboard's own origin.
_ALLOWED_IMG_PREFIXES = ("/static/", "/assets/", "./")

# Link targets the strict renderer will emit: same-origin paths, or http(s)
# to somewhere else. Anything else (javascript:, data:, vbscript:) is dropped.
_ALLOWED_LINK_RE = re.compile(r"\A(?:https?://|/(?!/)|\./|#)", re.IGNORECASE)


def render_markdown(text: str) -> str:
    """Render a small Markdown subset (images + links) to HTML.

    The image ``src`` is emitted as-authored so cards can reference badge and
    diagram URLs.
    """
    html = _IMG_RE.sub(r'<img alt="\1" src="\2">', text or "")
    html = _LINK_RE.sub(r'<a href="\2">\1</a>', html)
    return html


def render_card_markdown(text: str) -> str:
    """Render the same Markdown subset, emitting only same-origin images.

    Every value that reaches an attribute is HTML-escaped before it is
    interpolated, so a crafted ``src``/``alt``/``href`` cannot close the
    attribute it sits in and introduce another one; link targets are limited
    to http(s) and same-origin paths.
    """

    def _img(m: "re.Match[str]") -> str:
        alt, src = m.group(1), m.group(2)
        if src.startswith(_ALLOWED_IMG_PREFIXES) and "://" not in src:
            return f'<img alt="{escape(alt, quote=True)}" src="{escape(src, quote=True)}">'
        return escape(alt, quote=True)

    def _link(m: "re.Match[str]") -> str:
        label, href = m.group(1), m.group(2)
        if not _ALLOWED_LINK_RE.match(href.strip()):
            return escape(label, quote=True)
        return (f'<a href="{escape(href.strip(), quote=True)}">'
                f'{escape(label, quote=True)}</a>')

    html = _IMG_RE.sub(_img, text or "")
    html = _LINK_RE.sub(_link, html)
    return html
