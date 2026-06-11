from __future__ import annotations

from collections import Counter
from typing import Any


def _source_bucket(source: str, source_type: str = "unknown") -> dict[str, Any]:
    return {
        "source": source,
        "source_type": source_type,
        "query_count": 0,
        "collected_count": 0,
        "deduped_raw_count": 0,
        "quality_gate_input_count": 0,
        "qualified_raw_count": 0,
        "rejected_raw_count": 0,
        "analyzed_candidate_count": 0,
        "final_qualified_count": 0,
        "final_rejected_count": 0,
        "rejection_reason_counts": {},
        "final_rejection_reason_counts": {},
        "status": "unknown",
        "warning": None,
        "error": None,
        "categories": {},
    }


def _category_bucket(category: str) -> dict[str, Any]:
    return {
        "category": category,
        "sources": set(),
        "queries": set(),
        "query_count": 0,
        "collected_count": 0,
        "deduped_raw_count": 0,
        "quality_gate_input_count": 0,
        "qualified_raw_count": 0,
        "rejected_raw_count": 0,
        "analyzed_candidate_count": 0,
        "final_qualified_count": 0,
        "final_rejected_count": 0,
        "rejection_reason_counts": {},
        "final_rejection_reason_counts": {},
    }


def build_base_telemetry() -> dict[str, Any]:
    return {"source_telemetry": {}, "category_telemetry": {}}


def ensure_source(telemetry: dict[str, Any], source: str, source_type: str = "unknown") -> dict[str, Any]:
    bucket = telemetry["source_telemetry"].setdefault(source, _source_bucket(source, source_type))
    if not bucket.get("source_type") or bucket.get("source_type") == "unknown":
        bucket["source_type"] = source_type
    return bucket


def ensure_category(telemetry: dict[str, Any], category: str) -> dict[str, Any]:
    return telemetry["category_telemetry"].setdefault(category, _category_bucket(category))


def finalize_telemetry(telemetry: dict[str, Any]) -> dict[str, Any]:
    for bucket in telemetry.get("category_telemetry", {}).values():
        bucket["sources"] = sorted(bucket["sources"])
        bucket["queries"] = sorted(bucket["queries"])
        bucket["query_count"] = len(bucket["queries"])
    return telemetry


def summarize_quality_gate_by_source(quality_results: list[tuple[Any, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for item, result in quality_results:
        src = getattr(item, "source", "unknown")
        bucket = summary.setdefault(src, {"quality_gate_input_count": 0, "qualified_raw_count": 0, "rejected_raw_count": 0, "rejection_reason_counts": {}})
        bucket["quality_gate_input_count"] += 1
        if result.is_qualified:
            bucket["qualified_raw_count"] += 1
        else:
            bucket["rejected_raw_count"] += 1
            for reason in result.rejection_reasons:
                bucket["rejection_reason_counts"][reason] = bucket["rejection_reason_counts"].get(reason, 0) + 1
    return summary


def summarize_quality_gate_by_category(quality_results: list[tuple[Any, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for item, result in quality_results:
        category = getattr(item, "query_category", None) or "uncategorized"
        bucket = summary.setdefault(category, {"quality_gate_input_count": 0, "qualified_raw_count": 0, "rejected_raw_count": 0, "rejection_reason_counts": {}})
        bucket["quality_gate_input_count"] += 1
        if result.is_qualified:
            bucket["qualified_raw_count"] += 1
        else:
            bucket["rejected_raw_count"] += 1
            for reason in result.rejection_reasons:
                bucket["rejection_reason_counts"][reason] = bucket["rejection_reason_counts"].get(reason, 0) + 1
    return summary


def top_reason(reason_counts: dict[str, int]) -> str:
    if not reason_counts:
        return "none"
    return Counter(reason_counts).most_common(1)[0][0]
