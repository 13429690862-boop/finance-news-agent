"""Deterministic offline fixture collector."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.models import RawItem
from agent.sources.base import SourceCollector


DEFAULT_FIXTURE_PATH = Path("tests/fixtures/sample_raw_items.json")


class MockCollector(SourceCollector):
    """Offline-only collector backed by static JSON fixtures."""

    def __init__(self, fixture_path: str | Path = DEFAULT_FIXTURE_PATH) -> None:
        self.fixture_path = Path(fixture_path)

    def collect(self, queries: list[str], max_items: int) -> list[RawItem]:
        """Return deterministic fixture items, capped by max_items."""
        if max_items <= 0:
            return []

        records = self._load_fixture_records()
        items = [RawItem(**record) for record in records]
        return items[:max_items]

    def _load_fixture_records(self) -> list[dict[str, Any]]:
        if self.fixture_path.exists():
            return json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return []
