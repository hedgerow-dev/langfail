"""Printable sheets for checkpoints and eval runs.

A sheet is a Jinja template rendered against the object it describes. Preset
layouts ship in ``pages/layouts``; teams keep their own layout files beside
them and pick one by file name.
"""
from __future__ import annotations

import os
from typing import Any

from jinja2 import BaseLoader, Environment, TemplateNotFound

LAYOUT_ROOT = os.path.join(os.path.dirname(__file__), "layouts")
PRESET_LAYOUTS = {"brief": "brief.html", "full": "full.html"}

DEFAULT_SHEET = (
    "{{ checkpoint.name }} ({{ checkpoint.size_bytes }} bytes)\n"
    "Prepared for {{ viewer }}\n\n"
    "{{ checkpoint.readme }}\n"
)


class LayoutLoader(BaseLoader):
    """Loads layout files from a folder, re-reading a file when it changes."""

    def __init__(self, root: str):
        self.root = root

    def get_source(self, environment: Environment, template: str):
        path = os.path.normpath(os.path.join(self.root, template))
        if not os.path.isfile(path):
            raise TemplateNotFound(template)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        mtime = os.path.getmtime(path)
        return source, path, lambda: os.path.getmtime(path) == mtime


_sheets = Environment(loader=LayoutLoader(LAYOUT_ROOT), autoescape=True)


def fill_sheet(source: str, context: dict[str, Any]) -> str:
    return _sheets.from_string(source or DEFAULT_SHEET).render(**context)


def layout_sheet(layout: str, context: dict[str, Any]) -> str:
    return _sheets.get_template(layout).render(**context)


def preset_sheet(style: str, context: dict[str, Any]) -> str:
    return _sheets.get_template(PRESET_LAYOUTS.get(style, "brief.html")).render(**context)


# Sheet bodies arrive as finished HTML; the shell only frames them.
_shell = Environment(autoescape=False).from_string(
    '<!doctype html><html><head><meta charset="utf-8"><title>{{ title }}</title></head>'
    '<body><article class="sheet">{{ body }}</article></body></html>'
)


def page_shell(title: str, body: str) -> str:
    return _shell.render(title=title, body=body)
