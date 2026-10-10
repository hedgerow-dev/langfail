"""Model access for copilot features.

Without a configured model endpoint the workbench runs on ``LocalCopilot``,
which replies with the request text itself so copilot flows work without a
model (questions already written in the reply format pass through unchanged).
"""
from __future__ import annotations

from typing import Annotated, Protocol

from fastapi import Depends


class Copilot(Protocol):
    def reply(self, instruction: str, prompt: str) -> str: ...


class LocalCopilot:
    def reply(self, instruction: str, prompt: str) -> str:
        return prompt.strip()


def get_copilot() -> Copilot:
    return LocalCopilot()


CopilotDep = Annotated[Copilot, Depends(get_copilot)]
