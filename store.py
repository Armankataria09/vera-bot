"""
State management for the Magicpin Vera bot.

The judge pushes versioned contexts. This module owns the rules for replacing
contexts, retrieving the latest copy, conversations, suppression keys, and reset.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from threading import RLock
from typing import Any


class ContextStore:
    def __init__(self) -> None:
        self._contexts: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = RLock()

    def put(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
        delivered_at: str | None = None,
    ) -> tuple[bool, str, int | None]:
        key = (scope, context_id)

        with self._lock:
            current = self._contexts.get(key)

            if current is not None and current["version"] >= version:
                return False, "stale_version", current["version"]

            self._contexts[key] = {
                "version": version,
                "payload": deepcopy(payload),
                "delivered_at": delivered_at,
            }

        return True, "accepted", None

    def get(self, scope: str, context_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._contexts.get((scope, context_id))
            return deepcopy(item) if item is not None else None

    def payload(self, scope: str, context_id: str) -> dict[str, Any] | None:
        item = self.get(scope, context_id)
        return item["payload"] if item else None

    def counts(self) -> dict[str, int]:
        counts = {
            "category": 0,
            "merchant": 0,
            "customer": 0,
            "trigger": 0,
        }

        with self._lock:
            for scope, _ in self._contexts:
                if scope in counts:
                    counts[scope] += 1

        return counts

    def all_contexts(self) -> dict[tuple[str, str], dict[str, Any]]:
        with self._lock:
            return deepcopy(self._contexts)

    def clear(self) -> None:
        with self._lock:
            self._contexts.clear()


class ConversationStore:
    def __init__(self) -> None:
        self._turns: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = RLock()

    def append(self, conversation_id: str, turn: dict[str, Any]) -> None:
        with self._lock:
            self._turns[conversation_id].append(deepcopy(turn))

    def get(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._turns.get(conversation_id, []))

    def last_message(self, conversation_id: str) -> str | None:
        with self._lock:
            turns = self._turns.get(conversation_id, [])
            if not turns:
                return None
            return turns[-1].get("message")

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()


class SuppressionStore:
    """Tracks suppression keys and message bodies to avoid spam/repetition."""

    def __init__(self) -> None:
        self._keys: set[str] = set()
        self._bodies: dict[str, set[str]] = defaultdict(set)
        self._lock = RLock()

    def seen_key(self, suppression_key: str) -> bool:
        if not suppression_key:
            return False
        with self._lock:
            return suppression_key in self._keys

    def mark_key(self, suppression_key: str) -> None:
        if suppression_key:
            with self._lock:
                self._keys.add(suppression_key)

    def seen_body(self, conversation_id: str, body: str) -> bool:
        normalized = " ".join(body.lower().split())
        with self._lock:
            return normalized in self._bodies[conversation_id]

    def mark_body(self, conversation_id: str, body: str) -> None:
        normalized = " ".join(body.lower().split())
        with self._lock:
            self._bodies[conversation_id].add(normalized)

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()
            self._bodies.clear()


class BotState:
    """Single state container used by the API layer."""

    def __init__(self) -> None:
        self.contexts = ContextStore()
        self.conversations = ConversationStore()
        self.suppression = SuppressionStore()

    def clear(self) -> None:
        self.contexts.clear()
        self.conversations.clear()
        self.suppression.clear()


state = BotState()
