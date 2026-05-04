from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatResult:
    answer: str
    context: dict

