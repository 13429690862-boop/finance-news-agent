"""Base contracts for source collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agent.models import RawItem


class CollectorStatus(str, Enum):
    """Status values describing a collector run."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class CollectorResult:
    """Structured result metadata for future collector implementations."""

    status: CollectorStatus
    items: list[RawItem] = field(default_factory=list)
    message: str = ""


class SourceCollector:
    """Interface implemented by source collectors."""

    def collect(self, queries: list[str], max_items: int) -> list[RawItem]:
        """Collect raw items for the provided queries."""
        raise NotImplementedError
