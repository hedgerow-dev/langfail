"""Clause helpers for the few listing queries whose filters vary per request."""
from __future__ import annotations


def text_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def contains(column: str, needle: str) -> str:
    return f"{column} LIKE {text_literal('%' + needle + '%')}"


def starts_with(column: str, prefix: str) -> str:
    return f"{column} LIKE '{prefix}%'"
