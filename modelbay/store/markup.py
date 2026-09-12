"""Markdown -> HTML rendering for assistant answers and bundle notes.

Assistant output and user-authored bundle notes are written in Markdown and
rendered to HTML for the portal. Images and links are converted to the
corresponding tags so notes can embed badges, diagrams and documentation links.
"""
from __future__ import annotations

import re
from html import escape

# ![alt](src) and [text](href)
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")

# Image sources that stay on the portal's own origin.
_LOCAL_IMG_PREFIXES = ("/static/", "/assets/", "./")

# Link targets the strict renderer will emit: same-origin paths, or http(s)
# to somewhere else. Anything else (javascript:, data:, vbscript:) is dropped.
_LOCAL_LINK_RE = re.compile(r"\A(?:https?://|/(?!/)|\./|#)", re.IGNORECASE)


def to_html(text: str) -> str:
    """Render a small Markdown subset (images + links) to HTML.

    The image ``src`` is emitted as-authored so notes can reference badge and
    diagram URLs.
    """
    html = _IMG_RE.sub(r'<img alt="\1" src="\2">', text or "")
    html = _LINK_RE.sub(r'<a href="\2">\1</a>', html)
    return html


def to_html_local(text: str) -> str:
    """Render the same Markdown subset, emitting only same-origin images.

    Every value that reaches an attribute is HTML-escaped before it is
    interpolated, so a crafted ``src``/``alt``/``href`` cannot close the
    attribute it sits in and introduce another one; link targets are limited
    to http(s) and same-origin paths.
    """

    def _img(m: "re.Match[str]") -> str:
        alt, src = m.group(1), m.group(2)
        if src.startswith(_LOCAL_IMG_PREFIXES) and "://" not in src:
            return f'<img alt="{escape(alt, quote=True)}" src="{escape(src, quote=True)}">'
        return escape(alt, quote=True)

    def _link(m: "re.Match[str]") -> str:
        label, href = m.group(1), m.group(2)
        if not _LOCAL_LINK_RE.match(href.strip()):
            return escape(label, quote=True)
        return (f'<a href="{escape(href.strip(), quote=True)}">'
                f'{escape(label, quote=True)}</a>')

    html = _IMG_RE.sub(_img, text or "")
    html = _LINK_RE.sub(_link, html)
    return html
