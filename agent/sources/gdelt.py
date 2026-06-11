"""GDELT source collector."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import find_spec
from typing import Any
from urllib.parse import quote_plus

from agent.models import RawItem
from agent.sources.base import SourceCollector


class GDELTCollector(SourceCollector):
    """Collect demand-signal raw items from the GDELT doc API."""

    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, timeout_seconds: int = 15, user_agent: str = "china-demand-agent/phase-2b") -> None:
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
                payload = self._fetch_articles(query, max_items=max_items)
            except Exception:
                payload = {}

            articles = payload.get("articles", []) if isinstance(payload, dict) else []
            if not isinstance(articles, list):
                continue

            for article in articles:
                if len(results) >= max_items:
                    break
                item = self._article_to_raw_item(article, query)
                if item is None:
                    continue
                dedupe_key = (item.url.strip().lower(), item.title.strip().lower())
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                results.append(item)

        return results

    def _fetch_articles(self, query: str, max_items: int) -> dict[str, Any]:
        if find_spec("httpx") is None:
            return {}

        import httpx

        request_url = (
            f"{self.base_url}?query={quote_plus(query)}"
            f"&mode=ArtList&maxrecords={max(1, max_items)}&format=json&sort=DateDesc"
        )

        try:
            with httpx.Client(timeout=self.timeout_seconds, headers={"User-Agent": self.user_agent}) as client:
                response = client.get(request_url)
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _article_to_raw_item(self, article: Any, query: str) -> RawItem | None:
        if not isinstance(article, dict):
            return None

        title = _clean_text(article.get("title"))
        url = _clean_text(article.get("url"))
        if not title or not url:
            return None

        context = _clean_text(article.get("snippet") or article.get("socialimage") or article.get("domain"))
        content = " | ".join(part for part in [title, context] if part)
        if not content:
            content = title

        published_at = _clean_text(article.get("seendate") or article.get("date"))
        if not published_at:
            return None

        metadata = {
            key: article.get(key)
            for key in ("domain", "language", "sourcecountry", "tone", "socialimage", "seendate")
            if key in article
        }

        return RawItem(
            source="gdelt",
            source_type="news",
            url=url,
            title=title,
            content=content,
            author=_clean_text(article.get("source")),
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
