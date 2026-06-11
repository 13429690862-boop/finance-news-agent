"""Sanitized pipeline timing diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

_STAGE_PREFIXES = {
    "collect": "collect",
    "quality_gate": "quality_gate",
    "deepseek_coarse": "ai_coarse",
    "quick_service_classifier": "quick_service_classifier",
    "analyzer": "analyzer",
    "final_filter": "final_filter",
    "report_generation": "report",
    "delivery_send": "delivery_send",
}


def utc_now_iso() -> str:
    """Return a UTC ISO-8601 timestamp for diagnostics."""
    return datetime.now(UTC).isoformat()


def _duration(start: float | None) -> float | None:
    if start is None:
        return None
    return round(perf_counter() - start, 3)


def create_pipeline_timing() -> dict[str, Any]:
    started_at = utc_now_iso()
    return {
        "run_started_at": started_at,
        "run_finished_at": None,
        "total_runtime_seconds": None,
        "collect_started_at": None,
        "collect_finished_at": None,
        "collect_duration_seconds": None,
        "quality_gate_started_at": None,
        "quality_gate_finished_at": None,
        "quality_gate_duration_seconds": None,
        "ai_coarse_started_at": None,
        "ai_coarse_finished_at": None,
        "ai_coarse_duration_seconds": None,
        "quick_service_classifier_started_at": None,
        "quick_service_classifier_finished_at": None,
        "quick_service_classifier_duration_seconds": None,
        "analyzer_started_at": None,
        "analyzer_finished_at": None,
        "analyzer_duration_seconds": None,
        "final_filter_started_at": None,
        "final_filter_finished_at": None,
        "final_filter_duration_seconds": None,
        "report_started_at": None,
        "report_finished_at": None,
        "report_duration_seconds": None,
        "delivery_send_started_at": None,
        "delivery_send_finished_at": None,
        "delivery_send_duration_seconds": None,
        "smtp_duration_seconds": None,
        "stage_statuses": {
            stage: "not_attempted" for stage in _STAGE_PREFIXES
        },
        "_perf": {"run": perf_counter()},
    }


def start_stage(timing: dict[str, Any], stage: str) -> None:
    prefix = _STAGE_PREFIXES[stage]
    timing[f"{prefix}_started_at"] = utc_now_iso()
    timing.setdefault("stage_statuses", {})[stage] = "running"
    timing.setdefault("_perf", {})[stage] = perf_counter()


def finish_stage(timing: dict[str, Any], stage: str, status: str = "ok") -> None:
    prefix = _STAGE_PREFIXES[stage]
    timing[f"{prefix}_finished_at"] = utc_now_iso()
    timing[f"{prefix}_duration_seconds"] = _duration(timing.get("_perf", {}).get(stage))
    timing.setdefault("stage_statuses", {})[stage] = status


def skip_stage(timing: dict[str, Any], stage: str, status: str = "skipped") -> None:
    timing.setdefault("stage_statuses", {})[stage] = status


def finish_run(timing: dict[str, Any]) -> dict[str, Any]:
    timing["run_finished_at"] = utc_now_iso()
    timing["total_runtime_seconds"] = _duration(timing.get("_perf", {}).get("run"))
    timing.pop("_perf", None)
    return timing


def public_timing(timing: dict[str, Any]) -> dict[str, Any]:
    public = dict(timing)
    public.pop("_perf", None)
    return public
