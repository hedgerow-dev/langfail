"""Report rendering.

Users author reusable report templates (Jinja syntax) that are rendered against
a model/experiment context to produce shareable summaries.
"""
from __future__ import annotations

from jinja2 import Environment

_env = Environment(autoescape=True)

DEFAULT_TEMPLATE = (
    "# {{ model.name }}\n\n"
    "Framework: {{ model.framework }}\n"
    "Owner: {{ owner }}\n\n"
    "{{ model.model_card }}\n"
)


def render_report(template_src: str, context: dict) -> str:
    """Render a user-supplied report template against ``context``."""
    template = _env.from_string(template_src or DEFAULT_TEMPLATE)
    return template.render(**context)


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
