"""Report rendering.

Users author reusable report templates (Jinja syntax) that are rendered against
a model/experiment context to produce shareable summaries.
"""
from __future__ import annotations

import os
from pathlib import Path

from jinja2 import Environment

_env = Environment(autoescape=True)

DEFAULT_TEMPLATE = (
    "# {{ model.name }}\n\n"
    "Framework: {{ model.framework }}\n"
    "Owner: {{ owner }}\n\n"
    "{{ model.model_card }}\n"
)

# Built-in report templates shipped with the app (report_templates/*.tpl).
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "assets" / "report_templates"

# The small fixed set of report styles exposed through the "kind" parameter.
BUILTIN_KINDS = {"summary": "summary.tpl", "minimal": "minimal.tpl"}


def render_report(template_src: str, context: dict) -> str:
    """Render a user-supplied report template against ``context``."""
    template = _env.from_string(template_src or DEFAULT_TEMPLATE)
    return template.render(**context)


def load_template_file(template_name: str) -> str:
    """Read a report-template file by name from the built-in template directory."""
    path = os.path.join(str(TEMPLATE_DIR), template_name)
    with open(path, "r") as fh:
        return fh.read()


def render_builtin_report(kind: str, context: dict) -> str:
    """Render one of the small fixed set of built-in report kinds (see BUILTIN_KINDS)."""
    filename = BUILTIN_KINDS.get(kind, "summary.tpl")
    template_src = load_template_file(filename)
    return _env.from_string(template_src).render(**context)


def render_custom_report(template_name: str, context: dict) -> str:
    """Render a report from a caller-referenced template file.

    Lets a team point at their own ``.tpl`` file placed alongside the built-ins
    (uploaded out of band) instead of inlining the full template source in the
    request body.
    """
    template_src = load_template_file(template_name)
    return _env.from_string(template_src).render(**context)


# Rendering environment for dashboard/preview pages. Content is Markdown/HTML
# authored by users and assistants, so it is emitted verbatim into the page.
_page_env = Environment(autoescape=False)

_PAGE_SHELL = (
    "<!doctype html><html><head><title>{{ title }}</title></head>"
    "<body><main class=\"report\">{{ body }}</main></body></html>"
)


def render_page(title: str, body_html: str) -> str:
    """Wrap already-rendered report ``body_html`` in the dashboard page shell."""
    return _page_env.from_string(_PAGE_SHELL).render(title=title, body=body_html)
