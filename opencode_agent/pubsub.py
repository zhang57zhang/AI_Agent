"""Lightweight publish/subscribe event bus.

Used for decoupling the agent loop from UI components, tools,
and other subscribers. Follows the same pattern as OpenCode's
internal/pubsub package.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class Broker(Generic[T]):
    """Async-safe pub/sub broker.

    Subscribers are coroutines (async callables) that receive events.
    Events are dispatched in fire-and-forget mode — errors in one
    subscriber do not affect others.
    """

    def __init__(self) -> None:
        self._subscribers: dict[type[T], list[Callable[[T], Any]]] = defaultdict(list)
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def subscribe(self, event_type: type[T], handler: Callable[[T], Any]) -> None:
        """Register a handler for an event type."""
        async with self._get_lock():
            self._subscribers[event_type].append(handler)

    async def unsubscribe(self, event_type: type[T], handler: Callable[[T], Any]) -> None:
        """Remove a handler."""
        async with self._get_lock():
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    async def publish(self, event: T) -> None:
        """Dispatch event to all subscribers of its type (and parent types)."""
        # Collect all matching handlers
        targets: list[Callable[[T], Any]] = []
        async with self._get_lock():
            for etype, handlers in self._subscribers.items():
                if isinstance(event, etype):
                    targets.extend(handlers)

        # Fire-and-forget dispatch
        for handler in targets:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # Log but don't crash the broker
                import logging

                logging.getLogger("opencode_agent.pubsub").debug(
                    "Subscriber error for %s: %s", type(event).__name__, exc_info=True
                )

    # --- Synchronous convenience ---

    def subscribe_sync(self, event_type: type[T], handler: Callable[[T], Any]) -> None:
        """Synchronous subscribe (for non-async contexts)."""
        self._subscribers[event_type].append(handler)

    def publish_sync(self, event: T) -> None:
        """Synchronous publish (for non-async contexts)."""
        for etype, handlers in self._subscribers.items():
            if isinstance(event, etype):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:
                        pass


# Global broker instance
_broker: Broker[Any] | None = None


def get_broker() -> Broker[Any]:
    global _broker
    if _broker is None:
        _broker = Broker()
    return _broker