from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from agent.models import RawItem

DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
REQUIRED_AI_SECRETS = [DEEPSEEK_API_KEY_ENV, OPENAI_API_KEY_ENV]
ALLOWED_COARSE_PROVIDERS = {"none", "mock", "deepseek"}
ALLOWED_FINAL_PROVIDERS = {"none", "mock", "openai_responses"}
TRUE_CODEX_SDK_NOTE = "Not implemented; current final scoring uses OpenAI Responses API."


@dataclass
class CoarseTriageResult:
    keep: bool
    coarse_score: float
    confidence: float
    coarse_reason: str
    category: str = "uncategorized"
    tags: list[str] = field(default_factory=list)


@dataclass
class FinalScoringResult:
    ai_final_score: float
    feasibility_score: float
    urgency_score: float
    confidence_score: float
    why_this_is_an_opportunity: str
    risks: list[str]
    assumptions: list[str]
    recommended_next_step: str
    commercial_summary: str


@dataclass
class AITriageSummary:
    enabled: bool = False
    allow_ai_to_bypass_final_filter: bool = False
    ai_coarse_input_count: int = 0
    ai_coarse_kept_count: int = 0
    ai_coarse_dropped_count: int = 0
    ai_coarse_failed_count: int = 0
    ai_final_input_count: int = 0
    ai_final_scored_count: int = 0
    ai_final_failed_count: int = 0
    coarse_stage: dict[str, Any] = field(default_factory=dict)
    final_stage: dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False
    fallback_reason: str | None = None
    used_for_opportunity_qualification: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "allow_ai_to_bypass_final_filter": self.allow_ai_to_bypass_final_filter,
            "ai_coarse_input_count": self.ai_coarse_input_count,
            "ai_coarse_kept_count": self.ai_coarse_kept_count,
            "ai_coarse_dropped_count": self.ai_coarse_dropped_count,
            "ai_coarse_failed_count": self.ai_coarse_failed_count,
            "ai_final_input_count": self.ai_final_input_count,
            "ai_final_scored_count": self.ai_final_scored_count,
            "ai_final_failed_count": self.ai_final_failed_count,
            "deepseek_coarse_status": dict(self.coarse_stage),
            "deepseek_coarse_input_count": self.ai_coarse_input_count,
            "deepseek_coarse_kept_count": self.ai_coarse_kept_count,
            "deepseek_coarse_dropped_count": self.ai_coarse_dropped_count,
            "deepseek_coarse_failed_count": self.ai_coarse_failed_count,
            "openai_final_status": dict(self.final_stage),
            "openai_final_input_count": self.ai_final_input_count,
            "openai_final_scored_count": self.ai_final_scored_count,
            "true_codex_sdk_supported": False,
            "true_codex_sdk_enabled": False,
            "true_codex_sdk_note": TRUE_CODEX_SDK_NOTE,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "used_for_opportunity_qualification": self.used_for_opportunity_qualification,
        }


class CoarseTriageProvider(Protocol):
    def triage(self, items: list[RawItem]) -> list[CoarseTriageResult]: ...


class FinalScoringProvider(Protocol):
    def score(self, opportunities: list[dict[str, Any]]) -> list[FinalScoringResult]: ...


def _stage(config: dict[str, Any], name: str) -> dict[str, Any]:
    return dict(config.get(name, {}) or {})


def _prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _bounded_float(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    number = float(value)
    if number < low or number > high:
        raise ValueError(f"score out of bounds: {number}")
    return number


def _extract_json_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = (choices[0] or {}).get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
    output = data.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            for content in (item or {}).get("content", []) or []:
                text = content.get("text") if isinstance(content, dict) else None
                if isinstance(text, str):
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks).strip()
    return ""


def _parse_json_list(raw: str, key: str) -> list[Any]:
    parsed = json.loads(raw)
    if isinstance(parsed, dict) and isinstance(parsed.get(key), list):
        return parsed[key]
    if isinstance(parsed, list):
        return parsed
    raise ValueError(f"provider response must be a JSON list or object with {key}")


def _validate_coarse_record(record: Any) -> CoarseTriageResult:
    if not isinstance(record, dict):
        raise ValueError("coarse result must be an object")
    return CoarseTriageResult(
        keep=bool(record["keep"]),
        coarse_score=_bounded_float(record["coarse_score"]),
        confidence=_bounded_float(record["confidence"]),
        coarse_reason=str(record["coarse_reason"])[:500],
        category=str(record.get("category", "uncategorized"))[:80],
        tags=[str(tag)[:40] for tag in (record.get("tags") or []) if str(tag).strip()][:5],
    )


def _validate_final_record(record: Any) -> FinalScoringResult:
    if not isinstance(record, dict):
        raise ValueError("final result must be an object")
    return FinalScoringResult(
        ai_final_score=_bounded_float(record["ai_final_score"]),
        feasibility_score=_bounded_float(record["feasibility_score"]),
        urgency_score=_bounded_float(record["urgency_score"]),
        confidence_score=_bounded_float(record["confidence_score"]),
        why_this_is_an_opportunity=str(record["why_this_is_an_opportunity"])[:1200],
        risks=[str(x)[:300] for x in record.get("risks", []) if str(x).strip()][:8],
        assumptions=[str(x)[:300] for x in record.get("assumptions", []) if str(x).strip()][:8],
        recommended_next_step=str(record["recommended_next_step"])[:600],
        commercial_summary=str(record.get("commercial_summary", ""))[:600],
    )


class MockCoarseTriageProvider:
    def triage(self, items: list[RawItem]) -> list[CoarseTriageResult]:
        results: list[CoarseTriageResult] = []
        for item in items:
            text = f"{item.title} {item.content}".lower()
            noise = any(term in text for term in ("jp morgan", "spoof", "trading", "big hack", "shopping", "provider-side"))
            results.append(CoarseTriageResult(keep=not noise, coarse_score=0.15 if noise else 0.82, confidence=0.7, coarse_reason="mock_rejected_obvious_noise" if noise else "mock_kept_demand_like", category="mock"))
        return results


class MockFinalScoringProvider:
    def score(self, opportunities: list[dict[str, Any]]) -> list[FinalScoringResult]:
        results: list[FinalScoringResult] = []
        for opp in opportunities:
            text = json.dumps(opp, ensure_ascii=False).lower()
            strong = any(term in text for term in ("1688", "freight", "wechat", "supplier", "quality", "sourcing"))
            results.append(FinalScoringResult(
                ai_final_score=0.88 if strong else 0.55,
                feasibility_score=0.74,
                urgency_score=0.68 if strong else 0.45,
                confidence_score=0.72,
                why_this_is_an_opportunity="Mock final scorer found source-primary demand evidence in the final-filter-qualified opportunity.",
                risks=["Mock score; validate with live customer evidence before acting."],
                assumptions=["Deterministic final filter already accepted this opportunity."],
                recommended_next_step="Validate the top evidence quote with two matching operators.",
                commercial_summary="Potential managed service or advisory package for the described China workflow.",
            ))
        return results


# Backward-compatible analyzer names retained for older tests/operator imports.
@dataclass
class LegacyCoarseTriageResult:
    accepted: bool
    reason: str


@dataclass
class LegacyFinalScoringResult:
    score: float
    reason: str


class MockCoarseTriageAnalyzer:
    def analyze(self, item: RawItem) -> LegacyCoarseTriageResult:
        result = MockCoarseTriageProvider().triage([item])[0]
        return LegacyCoarseTriageResult(accepted=result.keep, reason=result.coarse_reason)


class MockFinalScoringAnalyzer:
    def analyze(self, item: RawItem) -> LegacyFinalScoringResult:
        text = f"{item.title} {item.content}".lower()
        demand = any(term in text for term in ("1688", "freight forwarder", "wechat pay", "alibaba api", "qc inspection", "shenzhen", "supplier"))
        noise = any(term in text for term in ("shopping", "provider-side", "jp morgan", "big hack"))
        if noise:
            return LegacyFinalScoringResult(score=0.05, reason="mock_noise")
        if demand:
            return LegacyFinalScoringResult(score=0.95, reason="mock_true_demand")
        return LegacyFinalScoringResult(score=0.3, reason="mock_unknown")


class DeepSeekCoarseTriageProvider:
    def __init__(self, config: dict[str, Any]) -> None:
        self.api_key = os.getenv(str(config.get("api_key_env", DEEPSEEK_API_KEY_ENV)), "").strip()
        self.base_url = str(os.getenv("AI_COARSE_BASE_URL", "") or os.getenv("DEEPSEEK_BASE_URL", "") or config.get("base_url") or "https://api.deepseek.com").rstrip("/")
        # The daily agent model is a raw provider id. Claude Code context aliases such
        # as deepseek-v4-pro[1m] are represented separately as context_window metadata
        # and are never sent in the DeepSeek chat/completions model field.
        self.model = str(config.get("model") or "deepseek-v4-pro").strip()
        if self.model.endswith("[1m]"):
            self.model = self.model[:-4]
        self.reasoning_effort = str(os.getenv("AI_COARSE_REASONING_EFFORT", "") or os.getenv("DEEPSEEK_REASONING_EFFORT", "") or config.get("reasoning_effort") or "max").strip()
        self.timeout = float(config.get("timeout_seconds", 90))
        self.config = dict(config)
        self.prompt = _prompt("prompts/deepseek_coarse_triage.md")

    def triage(self, items: list[RawItem]) -> list[CoarseTriageResult]:
        payload_items = [item.model_dump() for item in items]
        request_json: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": json.dumps({"items": payload_items}, ensure_ascii=False)},
            ],
            "temperature": float(self.config.get("temperature", 0)) if hasattr(self, "config") else 0,
            "response_format": {"type": "json_object"},
        }
        if hasattr(self, "config") and self.config.get("max_output_tokens"):
            request_json["max_output_tokens"] = int(self.config["max_output_tokens"])
        if self.reasoning_effort:
            request_json["reasoning_effort"] = self.reasoning_effort
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=request_json,
            timeout=self.timeout,
        )
        response.raise_for_status()
        records = _parse_json_list(_extract_json_text(response.json()), "items")
        if len(records) != len(items):
            raise ValueError("coarse result count mismatch")
        return [_validate_coarse_record(record) for record in records]


class OpenAIResponsesFinalScoringProvider:
    """OpenAI Responses API adapter for optional final opportunity enrichment.

    This is not a true Codex SDK, Codex CLI, or local Codex agent integration.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.api_key = os.getenv(str(config.get("api_key_env", OPENAI_API_KEY_ENV)), "").strip()
        self.model = str(os.getenv("AI_FINAL_MODEL", "") or os.getenv("CODEX_MODEL", "") or os.getenv("OPENAI_MODEL", "") or config.get("model") or "gpt-5.3-codex")
        self.timeout = float(config.get("timeout_seconds", 60))
        self.base_url = str(os.getenv("AI_FINAL_BASE_URL", "") or os.getenv("OPENAI_BASE_URL", "") or config.get("base_url") or "").strip() or None
        self.prompt = _prompt("prompts/openai_final_scoring.md")

    def score(self, opportunities: list[dict[str, Any]]) -> list[FinalScoringResult]:
        from openai import OpenAI  # optional dependency, imported only for explicitly enabled OpenAI Responses final scoring

        kwargs: dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        client = OpenAI(**kwargs)
        response = client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": self.prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps({"opportunities": opportunities}, ensure_ascii=False)}]},
            ],
            temperature=0,
        )
        raw = getattr(response, "output_text", "") or str(response)
        records = _parse_json_list(raw, "opportunities")
        if len(records) != len(opportunities):
            raise ValueError("final scoring result count mismatch")
        return [_validate_final_record(record) for record in records]


def _missing_secret(env_name: str) -> bool:
    return not os.getenv(env_name, "").strip()


def _coarse_provider(config: dict[str, Any]) -> CoarseTriageProvider:
    provider = str(config.get("provider", "none"))
    if provider == "mock":
        return MockCoarseTriageProvider()
    if provider == "deepseek":
        return DeepSeekCoarseTriageProvider(config)
    raise ValueError(f"unsupported coarse provider: {provider}")


def _final_provider(config: dict[str, Any]) -> FinalScoringProvider:
    provider = str(config.get("provider", "none"))
    if provider == "mock":
        return MockFinalScoringProvider()
    if provider == "openai_responses":
        return OpenAIResponsesFinalScoringProvider(config)
    raise ValueError(f"unsupported final provider: {provider}")


def apply_deepseek_coarse_triage(items: list[RawItem], config: dict[str, Any]) -> tuple[list[RawItem], dict[str, Any]]:
    stage = _stage(config, "coarse_stage")
    status = {"enabled": bool(config.get("enabled", False) and stage.get("enabled", False)), "provider": stage.get("provider", "none"), "model": stage.get("model", ""), "reasoning_effort": stage.get("reasoning_effort", ""), "context_window": stage.get("context_window", "default"), "status": "disabled", "reason": "disabled", "fallback_used": False}
    if not status["enabled"]:
        return items, {**status, "input_count": 0, "kept_count": len(items), "dropped_count": 0, "failed_count": 0, "results": []}
    sample_limit = int(stage.get("sample_limit", len(items)) or len(items))
    batch = items[:sample_limit]
    status.update({"status": "running", "reason": "provider_requested", "input_count": len(batch)})
    if str(stage.get("provider")) != "mock" and _missing_secret(str(stage.get("api_key_env", DEEPSEEK_API_KEY_ENV))):
        status.update({"status": "missing_secrets", "reason": "missing_secrets", "missing_secrets": [str(stage.get("api_key_env", DEEPSEEK_API_KEY_ENV))], "fallback_used": True, "kept_count": len(items), "dropped_count": 0, "failed_count": len(batch), "results": []})
        return items, status
    try:
        results = _coarse_provider(stage).triage(batch)
        kept_urls = {item.url for item, result in zip(batch, results, strict=True) if result.keep}
        kept = [item for item in items if item.url in kept_urls or item not in batch]
        result_payload = [{"url": item.url, **result.__dict__} for item, result in zip(batch, results, strict=True)]
        status.update({"status": "ok", "reason": "completed", "kept_count": len(kept), "dropped_count": len(items) - len(kept), "failed_count": 0, "results": result_payload})
        return kept, status
    except Exception as exc:
        status.update({"status": "fallback_used", "reason": f"provider_error:{type(exc).__name__}", "fallback_used": True, "kept_count": len(items), "dropped_count": 0, "failed_count": len(batch), "results": []})
        return items, status


def apply_openai_final_scoring(opportunities: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stage = _stage(config, "final_stage")
    status = {"enabled": bool(config.get("enabled", False) and stage.get("enabled", False)), "provider": stage.get("provider", "none"), "model": stage.get("model", ""), "status": "disabled", "reason": "disabled", "fallback_used": False}
    if not status["enabled"]:
        return opportunities, {**status, "input_count": 0, "scored_count": 0, "failed_count": 0}
    sample_limit = int(stage.get("sample_limit", len(opportunities)) or len(opportunities))
    batch = opportunities[:sample_limit]
    status.update({"status": "running", "reason": "provider_requested", "input_count": len(batch)})
    if str(stage.get("provider")) != "mock" and _missing_secret(str(stage.get("api_key_env", OPENAI_API_KEY_ENV))):
        status.update({"status": "missing_secrets", "reason": "missing_secrets", "missing_secrets": [str(stage.get("api_key_env", OPENAI_API_KEY_ENV))], "fallback_used": True, "scored_count": 0, "failed_count": len(batch)})
        return opportunities, status
    try:
        results = _final_provider(stage).score(batch)
        enriched = [dict(opp) for opp in opportunities]
        for idx, result in enumerate(results):
            enriched[idx]["ai_final_analysis"] = result.__dict__.copy()
            enriched[idx].update(result.__dict__)
        status.update({"status": "ok", "reason": "completed", "scored_count": len(results), "failed_count": 0})
        return enriched, status
    except Exception as exc:
        status.update({"status": "fallback_used", "reason": f"provider_error:{type(exc).__name__}", "fallback_used": True, "scored_count": 0, "failed_count": len(batch)})
        return opportunities, status


def build_ai_triage_summary(config: dict[str, Any], coarse_status: dict[str, Any], final_status: dict[str, Any]) -> dict[str, Any]:
    return AITriageSummary(
        enabled=bool(config.get("enabled", False)),
        allow_ai_to_bypass_final_filter=bool(config.get("allow_ai_to_bypass_final_filter", False)),
        ai_coarse_input_count=int(coarse_status.get("input_count", 0) or 0),
        ai_coarse_kept_count=int(coarse_status.get("kept_count", 0) or 0),
        ai_coarse_dropped_count=int(coarse_status.get("dropped_count", 0) or 0),
        ai_coarse_failed_count=int(coarse_status.get("failed_count", 0) or 0),
        ai_final_input_count=int(final_status.get("input_count", 0) or 0),
        ai_final_scored_count=int(final_status.get("scored_count", 0) or 0),
        ai_final_failed_count=int(final_status.get("failed_count", 0) or 0),
        coarse_stage=coarse_status,
        final_stage=final_status,
        fallback_used=bool(coarse_status.get("fallback_used") or final_status.get("fallback_used")),
        fallback_reason=str(coarse_status.get("reason") or final_status.get("reason")) if (coarse_status.get("fallback_used") or final_status.get("fallback_used")) else None,
    ).to_dict()


def _capability_fields(config: dict[str, Any], readiness: dict[str, Any] | None = None) -> dict[str, Any]:
    coarse = _stage(config, "coarse_stage")
    final = _stage(config, "final_stage")
    stages = (readiness or {}).get("stages", {}) if isinstance(readiness, dict) else {}
    coarse_status = (stages.get("coarse_stage") or {}).get("status")
    final_status = (stages.get("final_stage") or {}).get("status")
    return {
        "deepseek_coarse_supported": True,
        "deepseek_coarse_enabled": bool(config.get("enabled", False) and coarse.get("enabled", False) and coarse.get("provider") == "deepseek"),
        "deepseek_coarse_ready": coarse_status in {"ready", "ok"},
        "openai_final_supported": True,
        "openai_final_enabled": bool(config.get("enabled", False) and final.get("enabled", False) and final.get("provider") == "openai_responses"),
        "openai_final_ready": final_status in {"ready", "ok"},
        "true_codex_sdk_supported": False,
        "true_codex_sdk_enabled": False,
        "true_codex_sdk_note": TRUE_CODEX_SDK_NOTE,
    }


def _deepseek_provider_check_sample() -> RawItem:
    return RawItem(
        source="provider_check",
        source_type="manual_dry_run",
        url="https://example.invalid/deepseek-provider-check",
        title="Need China supplier verification help",
        content="I need help finding and verifying a China supplier and arranging quality control.",
        author="provider-check",
        published_at="2026-01-01T00:00:00Z",
        fetched_at="2026-01-01T00:00:00Z",
        query="provider check sample",
        language="en",
    )


def ai_provider_dry_run_check(config: dict[str, Any], sample_limit: int | None = None, provider: str | None = None) -> dict[str, Any]:
    if "dry_run_provider_check" in config and "coarse_stage" not in config and "final_stage" not in config:
        base = {"provider_check_status": "skipped", "provider_check_reason": "disabled", "missing_secrets": [], "fallback_mode": "rule_based", "checked_provider": "none", "sample_limit": int(sample_limit if sample_limit is not None else config.get("provider_check_sample_limit", 3)), "used_for_opportunity_qualification": False}
        if not bool(config.get("dry_run_provider_check", False)):
            return base
        missing = ["COARSE_AI_API_KEY", "COARSE_AI_MODEL", "FINAL_AI_API_KEY", "FINAL_AI_MODEL"]
        base.update({"provider_check_reason": "missing_secrets", "missing_secrets": missing})
        return base
    selected = provider or "all"
    result: dict[str, Any] = {"enabled": bool(config.get("enabled", False)), "allow_ai_to_bypass_final_filter": bool(config.get("allow_ai_to_bypass_final_filter", False)), "used_for_opportunity_qualification": False, "sample_limit": int(sample_limit or config.get("provider_check_sample_limit", 3)), "checked_provider": selected, "stages": {}}
    for name, allowed_secret in (("coarse_stage", DEEPSEEK_API_KEY_ENV), ("final_stage", OPENAI_API_KEY_ENV)):
        stage = _stage(config, name)
        enabled = bool(config.get("enabled", False) and stage.get("enabled", False))
        provider_name = str(stage.get("provider", "none"))
        if selected == "deepseek" and name != "coarse_stage":
            enabled = False
        if selected in {"openai", "openai_responses"} and name != "final_stage":
            enabled = False
        stage_result = {"enabled": enabled, "provider": provider_name, "model": stage.get("model", ""), "reasoning_effort": stage.get("reasoning_effort", "") if name == "coarse_stage" else "", "context_window": stage.get("context_window", "default") if name == "coarse_stage" else "", "status": "disabled", "reason": "disabled", "missing_secrets": [], "live_request_performed": False}
        if enabled:
            env_name = str(stage.get("api_key_env", allowed_secret))
            if provider_name == "none":
                stage_result.update({"status": "disabled", "reason": "provider_none"})
            elif provider_name != "mock" and _missing_secret(env_name):
                stage_result.update({"status": "missing_secrets", "reason": "missing_secrets", "missing_secrets": [env_name]})
            elif provider_name == "mock":
                stage_result.update({"status": "ready", "reason": "mock_ready_no_live_request"})
            elif name == "coarse_stage" and provider_name == "deepseek" and bool(config.get("dry_run_provider_check", False)):
                try:
                    DeepSeekCoarseTriageProvider(stage).triage([_deepseek_provider_check_sample()])
                    stage_result.update({"status": "ok", "reason": "live_json_contract_valid", "live_request_performed": True})
                except Exception as exc:
                    stage_result.update({"status": "failed", "reason": f"provider_error:{type(exc).__name__}", "live_request_performed": True})
            elif bool(config.get("dry_run", True)) or bool(stage.get("dry_run", True)):
                stage_result.update({"status": "ready", "reason": "dry_run_ready_no_live_request"})
            else:
                stage_result.update({"status": "ready", "reason": "live_request_not_performed_by_check"})
        result["stages"][name] = stage_result
    result.update(_capability_fields(config, result))
    result["provider_check_status"] = "ready" if all(s["status"] in {"disabled", "ready", "ok"} for s in result["stages"].values()) else "missing_secrets" if any(s["status"] == "missing_secrets" for s in result["stages"].values()) else "failed"
    result["missing_secrets"] = sorted({m for s in result["stages"].values() for m in s.get("missing_secrets", [])})
    result["no_secret_safe"] = not result["enabled"] or not result["missing_secrets"] or all(not s["enabled"] for s in result["stages"].values())
    return result
