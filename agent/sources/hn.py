"""Hacker News Algolia source collector."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import find_spec
from typing import Any
from urllib.parse import quote_plus

from agent.models import RawItem
from agent.sources.base import SourceCollector


class HNAlgoliaCollector(SourceCollector):
    """Collect demand-signal raw items from the HN Algolia search API."""

    base_url = "https://hn.algolia.com/api/v1/search"

    def __init__(self, timeout_seconds: int = 15, user_agent: str = "china-demand-agent/phase-2a") -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def collect(self, queries: list[str], max_items: int) -> list[RawItem]:
        if max_items <= 0 or not queries:
            return []

        results: list[RawItem] = []
        seen_keys: set[tuple[str, str]] = set()

        for query in queries:
            if len(results) >= max_items:
                break
            try:
                payload = self._fetch_hits(query)
            except Exception:
                payload = {}
            hits = payload.get("hits", []) if isinstance(payload, dict) else []
            if not isinstance(hits, list):
                continue

            for hit in hits:
                if len(results) >= max_items:
                    break
                item = self._hit_to_raw_item(hit, query)
                if item is None:
                    continue
                dedupe_key = (item.url.strip().lower(), item.title.strip().lower())
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                results.append(item)

        return results

    def _fetch_hits(self, query: str) -> dict[str, Any]:
        if find_spec("httpx") is None:
            return {}

        import httpx

        try:
            with httpx.Client(timeout=self.timeout_seconds, headers={"User-Agent": self.user_agent}) as client:
                response = client.get(f"{self.base_url}?query={quote_plus(query)}")
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _hit_to_raw_item(self, hit: Any, query: str) -> RawItem | None:
        if not isinstance(hit, dict):
            return None

        title = _clean_text(hit.get("title") or hit.get("story_title"))
        url = _clean_text(hit.get("story_url"))
        object_id = _clean_text(hit.get("objectID"))
        if not url and object_id:
            url = f"https://news.ycombinator.com/item?id={object_id}"
        content = _clean_text(hit.get("comment_text") or hit.get("story_text") or title)
        author = _clean_text(hit.get("author"))
        published_at = _clean_text(hit.get("created_at"))

        if not title or not url or not content or not published_at:
            return None

        metadata = {
            key: hit.get(key)
            for key in (
                "objectID",
                "points",
                "num_comments",
                "created_at_i",
                "story_id",
                "parent_id",
                "_tags",
            )
            if key in hit
        }

        return RawItem(
            source="hn_algolia",
            source_type="discussion",
            url=url,
            title=title,
            content=content,
            author=author,
            published_at=published_at,
            fetched_at=datetime.now(UTC).isoformat(),
            query=query,
            language="en",
            raw_metadata=metadata,
        )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
