import json
from pathlib import Path

import pytest

from agent.ai_triage import DeepSeekCoarseTriageProvider, apply_openai_final_scoring, apply_deepseek_coarse_triage, ai_provider_dry_run_check
from agent.config import load_ai_triage_config
from agent.models import RawItem
from agent.report import generate_json_summary, generate_markdown_report


def raw(title="Need China supplier verification", content="I need help finding a China supplier and quality control agent", url="https://e.test/1"):
    return RawItem(source="fixture", source_type="forum", url=url, title=title, content=content, author="a", published_at="2026-01-01", fetched_at="2026-01-01", query="metadata only", language="en")


def cfg(coarse="mock", final="mock"):
    return {"enabled": True, "dry_run": True, "allow_ai_to_bypass_final_filter": False, "coarse_stage": {"enabled": True, "provider": coarse, "model": "deepseek-v4-pro", "reasoning_effort": "max", "context_window": "default", "sample_limit": 10, "api_key_env": "DEEPSEEK_API_KEY"}, "final_stage": {"enabled": True, "provider": final, "model": "gpt-5.3-codex", "sample_limit": 10, "api_key_env": "OPENAI_API_KEY"}}


def test_config_defaults_safe_and_invalid_provider_fails(tmp_path):
    missing = load_ai_triage_config(tmp_path / "missing.yaml")
    assert missing["enabled"] is False
    assert missing["allow_ai_to_bypass_final_filter"] is False
    assert missing["coarse_stage"]["model"] == "deepseek-v4-pro"
    assert missing["coarse_stage"]["reasoning_effort"] == "max"
    assert missing["coarse_stage"]["context_window"] == "default"
    bad = tmp_path / "bad.yaml"
    bad.write_text("enabled: true\ncoarse_stage:\n  enabled: true\n  provider: bogus\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_ai_triage_config(bad)


def test_config_recommended_deepseek_model_and_reasoning_are_loaded():
    loaded = load_ai_triage_config("configs/ai_triage.yaml")
    assert loaded["coarse_stage"]["model"] == "deepseek-v4-pro"
    assert loaded["coarse_stage"]["reasoning_effort"] == "max"
    assert loaded["coarse_stage"]["context_window"] == "default"
    assert loaded["final_stage"]["enabled"] is False


def test_deepseek_mock_success_drops_noise():
    items = [raw(), raw("JP Morgan trading update", "shopping trading noise", "https://e.test/2")]
    kept, status = apply_deepseek_coarse_triage(items, cfg())
    assert [i.url for i in kept] == ["https://e.test/1"]
    assert status["status"] == "ok"
    assert status["dropped_count"] == 1


def test_deepseek_malformed_response_fallback(monkeypatch):
    class Bad:
        def triage(self, items):
            raise ValueError("malformed")
    monkeypatch.setattr("agent.ai_triage._coarse_provider", lambda stage: Bad())
    items = [raw()]
    kept, status = apply_deepseek_coarse_triage(items, cfg())
    assert kept == items
    assert status["status"] == "fallback_used"
    assert status["failed_count"] == 1


def test_deepseek_missing_secret_safe(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    c = cfg(coarse="deepseek")
    kept, status = apply_deepseek_coarse_triage([raw()], c)
    assert len(kept) == 1
    assert status["status"] == "missing_secrets"
    assert status["fallback_used"] is True


def opportunity():
    return {"title": "Rule-based demand: Need China supplier verification", "summary": "source text", "evidence_quotes": ["I need help finding a China supplier"], "evidence_urls": ["https://e.test/1"], "priority": "medium", "opportunity_score": 7, "customer_type": "SMB buyers"}


def test_openai_responses_mock_success_enriches_only():
    enriched, status = apply_openai_final_scoring([opportunity()], cfg())
    assert status["status"] == "ok"
    assert enriched[0]["ai_final_analysis"]["ai_final_score"] > 0
    assert enriched[0]["recommended_next_step"]


def test_openai_responses_malformed_response_fallback(monkeypatch):
    class Bad:
        def score(self, opportunities):
            raise ValueError("malformed")
    monkeypatch.setattr("agent.ai_triage._final_provider", lambda stage: Bad())
    opps = [opportunity()]
    enriched, status = apply_openai_final_scoring(opps, cfg())
    assert enriched == opps
    assert status["status"] == "fallback_used"
    assert status["failed_count"] == 1


def test_openai_responses_missing_secret_safe(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c = cfg(final="openai_responses")
    enriched, status = apply_openai_final_scoring([opportunity()], c)
    assert status["status"] == "missing_secrets"
    assert status["fallback_used"] is True
    assert "ai_final_analysis" not in enriched[0]


def test_ai_provider_check_reports_stage_readiness(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    readiness = ai_provider_dry_run_check(cfg(final="openai_responses"))
    assert readiness["provider_check_status"] == "missing_secrets"
    assert readiness["stages"]["final_stage"]["status"] == "missing_secrets"



def test_ai_provider_check_reports_capability_status(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    c = cfg(coarse="deepseek", final="none")
    c["final_stage"]["enabled"] = False
    readiness = ai_provider_dry_run_check(c, provider="deepseek")
    assert readiness["deepseek_coarse_supported"] is True
    assert readiness["deepseek_coarse_enabled"] is True
    assert readiness["deepseek_coarse_ready"] is False
    assert readiness["openai_final_supported"] is True
    assert readiness["openai_final_enabled"] is False
    assert readiness["true_codex_sdk_supported"] is False
    assert "OpenAI Responses API" in readiness["true_codex_sdk_note"]


def test_deepseek_live_provider_check_success_is_sanitized(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value-not-printed")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"items": [{"keep": True, "coarse_score": 0.9, "confidence": 0.8, "coarse_reason": "valid demand", "category": "sourcing", "tags": ["supplier"]}]})}}]}

    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["auth"] = headers.get("Authorization")
        seen["payload"] = json
        return Response()

    monkeypatch.setattr("agent.ai_triage.httpx.post", fake_post)
    c = cfg(coarse="deepseek", final="none")
    c["dry_run"] = False
    c["dry_run_provider_check"] = True
    c["final_stage"]["enabled"] = False
    readiness = ai_provider_dry_run_check(c, provider="deepseek")
    dumped = json.dumps(readiness)
    assert readiness["stages"]["coarse_stage"]["status"] == "ok"
    assert readiness["stages"]["coarse_stage"]["live_request_performed"] is True
    assert readiness["stages"]["coarse_stage"]["model"] == "deepseek-v4-pro"
    assert readiness["stages"]["coarse_stage"]["reasoning_effort"] == "max"
    assert readiness["stages"]["coarse_stage"]["context_window"] == "default"
    assert seen["payload"]["model"] == "deepseek-v4-pro"
    assert seen["payload"]["reasoning_effort"] == "max"
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert "secret-value-not-printed" not in dumped
    assert seen["auth"] == "Bearer secret-value-not-printed"


def test_deepseek_adapter_request_uses_configured_model_and_reasoning(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value-not-printed")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"items": [{"keep": True, "coarse_score": 0.9, "confidence": 0.8, "coarse_reason": "valid demand"}]})}}]}

    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["payload"] = json
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("agent.ai_triage.httpx.post", fake_post)
    provider = DeepSeekCoarseTriageProvider({"model": "deepseek-v4-pro", "reasoning_effort": "max", "context_window": "1m", "api_key_env": "DEEPSEEK_API_KEY", "timeout_seconds": 12})
    results = provider.triage([raw()])
    assert results[0].keep is True
    assert seen["payload"]["model"] == "deepseek-v4-pro"
    assert seen["payload"]["reasoning_effort"] == "max"
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert "context_window" not in seen["payload"]
    assert seen["timeout"] == 12


def test_deepseek_adapter_never_sends_claude_code_context_suffix(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value-not-printed")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"items": [{"keep": True, "coarse_score": 0.9, "confidence": 0.8, "coarse_reason": "valid demand"}]})}}]}

    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["payload"] = json
        return Response()

    monkeypatch.setattr("agent.ai_triage.httpx.post", fake_post)
    provider = DeepSeekCoarseTriageProvider({"model": "deepseek-v4-pro[1m]", "reasoning_effort": "max", "context_window": "1m", "api_key_env": "DEEPSEEK_API_KEY"})
    provider.triage([raw()])
    assert seen["payload"]["model"] == "deepseek-v4-pro"
    assert "context_window" not in seen["payload"]


def test_deepseek_live_provider_check_malformed_fails_safe(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value-not-printed")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "not json"}}]}

    monkeypatch.setattr("agent.ai_triage.httpx.post", lambda *args, **kwargs: Response())
    c = cfg(coarse="deepseek", final="none")
    c["dry_run"] = False
    c["dry_run_provider_check"] = True
    c["final_stage"]["enabled"] = False
    readiness = ai_provider_dry_run_check(c, provider="deepseek")
    assert readiness["provider_check_status"] == "failed"
    assert readiness["stages"]["coarse_stage"]["status"] == "failed"

def test_report_and_json_include_ai_fields(tmp_path):
    opp = opportunity()
    opp["ai_final_analysis"] = {"ai_final_score": 0.8}
    opp["ai_final_score"] = 0.8
    ai = {"enabled": True, "allow_ai_to_bypass_final_filter": False, "ai_coarse_input_count": 1, "ai_coarse_kept_count": 1, "ai_coarse_dropped_count": 0, "ai_coarse_failed_count": 0, "ai_final_input_count": 1, "ai_final_scored_count": 1, "ai_final_failed_count": 0, "deepseek_coarse_status": {"status": "ok", "provider": "deepseek", "model": "deepseek-v4-pro", "reasoning_effort": "max", "context_window": "1m", "reason": "completed"}, "openai_final_status": {"status": "ok", "provider": "mock", "reason": "completed"}, "openai_final_input_count": 1, "openai_final_scored_count": 1, "true_codex_sdk_supported": False}
    md = tmp_path / "r.md"
    js = tmp_path / "r.json"
    generate_markdown_report([opp], md, ai_triage_summary=ai)
    generate_json_summary([opp], js, ai_triage_summary=ai)
    content = md.read_text(encoding="utf-8")
    assert "DeepSeek Coarse Triage Summary" in content
    assert "OpenAI Responses Final Scoring Summary" in content
    assert "DeepSeek coarse model: deepseek-v4-pro" in content
    assert "Context window intent: 1m" in content
    assert "Reasoning effort: max" in content
    assert "True Codex SDK / Local Agent Status" in content
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["ai_triage_summary"]["openai_final_scored_count"] == 1
    assert payload["ai_triage_summary"]["true_codex_sdk_supported"] is False
    assert payload["ai_triage_summary"]["deepseek_coarse_status"]["context_window"] == "1m"
    assert payload["opportunities"][0]["ai_final_score"] == 0.8


def test_final_scoring_names_openai_responses_not_codex_sdk_claims():
    config_text = Path("configs/ai_triage.yaml").read_text(encoding="utf-8")
    guide_text = Path("docs/two_stage_ai_operator_guide.md").read_text(encoding="utf-8")
    prompt_text = Path("prompts/openai_final_scoring.md").read_text(encoding="utf-8")
    assert "provider: none  # none | mock | openai_responses" in config_text
    assert "provider: codex" not in config_text
    assert "model: deepseek-v4-pro" in config_text
    assert "context_window: default" in config_text
    assert "reasoning_effort: max" in config_text
    assert "model: deepseek-v4-pro[1m]" not in config_text
    assert "OpenAI Responses final scoring" in guide_text
    assert "True Codex SDK / local Codex agent integration**: not implemented" in guide_text
    assert "not a true Codex SDK/local agent integration" in prompt_text


def test_deepseek_default_timeout_is_raised_for_max_reasoning():
    provider = DeepSeekCoarseTriageProvider({"model": "deepseek-v4-pro", "reasoning_effort": "max", "api_key_env": "DEEPSEEK_API_KEY"})
    assert provider.timeout == 90
