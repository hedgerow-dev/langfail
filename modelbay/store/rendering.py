"""Report rendering.

Users author reusable report templates (Jinja syntax) that are rendered
against a bundle context to produce shareable summaries.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment

_env = Environment(autoescape=True)

FALLBACK_TEMPLATE = (
    "# {{ bundle.name }}\n\n"
    "Runtime: {{ bundle.runtime }}\n"
    "Owner: {{ owner }}\n\n"
    "{{ bundle.notes }}\n"
)

# Stock report templates shipped with the app (report_templates/*.tpl).
TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "assets" / "report_templates"

# The small fixed set of report styles exposed through the "style" parameter.
STOCK_STYLES = {"summary": "summary.tpl", "minimal": "minimal.tpl"}


def render_template_source(template_src: str, context: dict) -> str:
    """Render a caller-supplied report template against ``context``."""
    template = _env.from_string(template_src or FALLBACK_TEMPLATE)
    return template.render(**context)


def read_template_file(template_name: str) -> str:
    """Read a report-template file by name from the stock template directory."""
    return TEMPLATE_ROOT.joinpath(template_name).read_text()


def render_stock_report(style: str, context: dict) -> str:
    """Render one of the small fixed set of stock report styles (see STOCK_STYLES)."""
    filename = STOCK_STYLES.get(style, "summary.tpl")
    template_src = read_template_file(filename)
    return _env.from_string(template_src).render(**context)


def render_named_report(template_name: str, context: dict) -> str:
    """Render a report from a caller-referenced template file.

    Lets a team point at their own ``.tpl`` file placed alongside the stock
    ones (uploaded out of band) instead of inlining the full template source
    in the request body.
    """
    template_src = read_template_file(template_name)
    return _env.from_string(template_src).render(**context)


# Rendering environment for dashboard/preview pages. Content is Markdown/HTML
# authored by users and assistants, so it is emitted verbatim into the page.
_page_env = Environment(autoescape=False)

_PAGE_SHELL = (
    "<!doctype html><html><head><title>{{ title }}</title></head>"
    "<body><main class=\"report\">{{ body }}</main></body></html>"
)


def wrap_page(title: str, body_html: str) -> str:
    """Wrap already-rendered report ``body_html`` in the dashboard page shell."""
    return _page_env.from_string(_PAGE_SHELL).render(title=title, body=body_html)
