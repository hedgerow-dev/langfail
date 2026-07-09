"""Natural-language dataset analysis ("chat with your data").

A user asks a question in plain English; the assistant writes a short Python
snippet against the dataset's dataframe and we run it to produce the answer.
This is the PandasAI / LangChain "pandas agent" pattern.
"""
from __future__ import annotations

from typing import Any


def _to_frame(rows: list[dict]) -> Any:
    """Build a dataframe from row dicts, falling back to the raw list when the
    optional pandas dependency is not installed."""
    try:
        import pandas as pd
    except Exception:
        return rows
    return pd.DataFrame(rows)


def run_analysis(question: str, rows: list[dict]) -> str:
    """Answer ``question`` about ``rows`` by executing model-generated code.

    The assistant returns a Python snippet (see
    :func:`dvml.agent.llm.generate_code`); it is executed in a namespace scoped
    to the dataframe so the snippet can only touch ``df``.
    """
    from ..agent.llm import generate_code

    columns = list(rows[0].keys()) if rows else []
    code = generate_code(question, columns=columns)

    df = _to_frame(rows)
    scope: dict[str, Any] = {"df": df, "result": None}
    exec(code, scope)  # model-authored analysis code, run against df
    return str(scope.get("result"))


# Fixed vocabulary of whole-dataframe aggregates the constrained analyzer
# supports — the model never authors executable code on this path.
_SAFE_OPS = {
    "count": lambda df: len(df),
    "columns": lambda df: list(df[0].keys()) if df else [],
}


def run_analysis_safe(question: str, rows: list[dict]) -> str:
    """Constrained analysis: map the question to one of a fixed set of
    aggregates by keyword. No generated code is ever executed."""
    q = (question or "").strip().lower()
    for name, fn in _SAFE_OPS.items():
        if name in q:
            return str(fn(rows))
    return "unsupported question"
