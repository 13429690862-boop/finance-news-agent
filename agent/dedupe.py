"""Deduplication helpers for opportunity items."""

import re
from typing import Any


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Normalize a title for exact duplicate detection."""
    return _WHITESPACE_RE.sub(" ", title.strip().lower())


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate items by exact URL first, then by normalized title."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    deduped: list[dict[str, Any]] = []

    for item in items:
        url = item.get("url")
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)

        title = item.get("title")
        if title:
            normalized_title = normalize_title(str(title))
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)

        deduped.append(item)

    return deduped
