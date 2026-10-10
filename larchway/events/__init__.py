"""In-process event bus.

Subscribers register with a decorator::

    @on("member.signed_in")
    async def note_sign_in(payload: dict) -> None: ...

``await emit(topic, payload)`` calls every subscriber for that topic in
registration order. Subscribers may be sync or async.
"""
from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Callable

SUBSCRIBERS: dict[str, list[Callable]] = defaultdict(list)


def on(topic: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        SUBSCRIBERS[topic].append(fn)
        return fn

    return register


async def emit(topic: str, payload: dict) -> None:
    for fn in list(SUBSCRIBERS.get(topic, ())):
        result = fn(payload)
        if inspect.isawaitable(result):
            await result
