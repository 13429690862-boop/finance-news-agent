import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agent.config import load_ai_triage_config, load_delivery_config, load_sources_config
from agent.operator_audit import build_config_audit, build_env_inventory


def test_source_config_enabled_disabled_and_env_override(tmp_path, monkeypatch):
    cfg_path = tmp_path / "sources.yaml"
    cfg_path.write_text(
        "hn_algolia:\n  enabled: true\n  source_type: discussion\n  role: developer\n  max_results: 5\n  timeout_seconds: 4\n"
        "gdelt:\n  enabled: true\n  source_type: news\n  role: news\n  max_results: 6\n  timeout_seconds: 4\n"
        "stackexchange:\n  enabled: true\n  source_type: discussion\n  role: stack\n  max_results: 7\n  timeout_seconds: 4\n  sites: [stackoverflow]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SOURCE_HN_ENABLED", "false")
    cfg = load_sources_config(cfg_path)
    assert cfg["hn_algolia"]["enabled"] is False
    assert cfg["gdelt"]["enabled"] is True
    assert cfg["stackexchange"]["sites"] == ["stackoverflow"]


def test_invalid_source_name_and_stackexchange_sites_fail_cleanly(tmp_path):
    bad_name = tmp_path / "bad-name.yaml"
    bad_name.write_text("unknown:\n  enabled: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown source"):
        load_sources_config(bad_name)
    bad_sites = tmp_path / "bad-sites.yaml"
    bad_sites.write_text("stackexchange:\n  sites: not-a-list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stackexchange.sites"):
        load_sources_config(bad_sites)


def test_ai_env_overrides_and_safety_rejections(monkeypatch):
    monkeypatch.setenv("AI_COARSE_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("AI_COARSE_REASONING_EFFORT", "max")
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    assert cfg["coarse_stage"]["model"] == "deepseek-v4-pro"
    assert cfg["coarse_stage"]["reasoning_effort"] == "max"
    assert cfg["coarse_stage"]["context_window"] == "default"
    assert cfg["final_stage"]["enabled"] is False
    monkeypatch.setenv("AI_COARSE_REASONING_EFFORT", "extreme")
    with pytest.raises(ValueError, match="reasoning_effort"):
        load_ai_triage_config("configs/ai_triage.yaml")
    monkeypatch.setenv("AI_COARSE_REASONING_EFFORT", "max")
    monkeypatch.setenv("AI_ALLOW_BYPASS_FINAL_FILTER", "true")
    with pytest.raises(ValueError, match="bypass"):
        load_ai_triage_config("configs/ai_triage.yaml")


def test_delivery_env_overrides_default_safe(monkeypatch):
    monkeypatch.setenv("DELIVERY_ATTACH_JSON", "false")
    monkeypatch.setenv("DELIVERY_ATTACH_MARKDOWN", "true")
    cfg = load_delivery_config("configs/delivery.yaml")
    assert cfg["attach_json_summary"] is False
    assert cfg["attach_markdown"] is True
    assert cfg["allow_non_test_recipient"] is False


def test_config_audit_and_env_inventory_are_sanitized(monkeypatch):
    secret = "secret-value-not-printed"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    monkeypatch.setenv("REPORT_TEST_RECIPIENT_EMAIL", "operator@example.com")
    config = build_config_audit()
    inventory = build_env_inventory()
    dumped = json.dumps({"config": config, "inventory": inventory}, sort_keys=True)
    assert secret not in dumped
    assert "operator@example.com" not in dumped
    assert config["coarse_model"] == "deepseek-v4-pro"
    assert config["coarse_reasoning_effort"] == "max"
    assert config["coarse_context_window"] == "default"
    assert config["final_enabled"] is False
    assert config["true_codex_sdk_supported"] is False
    assert config["allow_ai_to_bypass_final_filter"] is False
    for key in ["required_now", "required_for_delivery", "required_for_deepseek", "required_for_openai_final", "optional", "unused_or_delete_candidates"]:
        assert key in inventory
    assert inventory["required_for_deepseek"] == []
    assert "REPORT_RECIPIENT_EMAIL" in inventory["unused_or_delete_candidates"]


def test_cli_config_audit_and_env_inventory_do_not_print_secret(monkeypatch):
    env = os.environ.copy()
    env["DEEPSEEK_API_KEY"] = "secret-value-not-printed"
    for mode in ("config-audit", "env-inventory"):
        out = subprocess.check_output([sys.executable, "-m", "agent.main", "--mode", mode], text=True, env=env)
        assert "secret-value-not-printed" not in out
        data = json.loads(out)
        assert data


def test_workflow_inputs_exist_and_default_safe():
    workflow = yaml.safe_load(Path(".github/workflows/daily.yml").read_text(encoding="utf-8"))
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert inputs["run_deepseek_provider_check"]["default"] is False
    assert inputs["run_daily_with_deepseek_coarse"]["default"] is False
    assert inputs["ai_coarse_model"]["default"] == "deepseek-v4-pro"
    assert inputs["ai_coarse_reasoning_effort"]["default"] == "max"
    assert inputs["ai_coarse_reasoning_effort"]["options"] == ["none", "low", "medium", "high", "max"]
    assert inputs["ai_coarse_context_window"]["default"] == "default"
    assert inputs["ai_coarse_context_window"]["options"] == ["default", "1m"]
    text = Path(".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "github.event_name == 'schedule' && env.SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT != 'true'" in text
    assert "AI_FINAL_ENABLED: 'false'" in text


def test_empty_env_vars_do_not_override_ai_defaults(monkeypatch):
    monkeypatch.setenv("AI_COARSE_MODEL", "")
    monkeypatch.setenv("AI_COARSE_REASONING_EFFORT", "")
    monkeypatch.setenv("AI_COARSE_PROVIDER", "")
    monkeypatch.setenv("AI_TRIAGE_ENABLED", "")
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    assert cfg["enabled"] is False
    assert cfg["coarse_stage"]["provider"] == "deepseek"
    assert cfg["coarse_stage"]["model"] == "deepseek-v4-pro"
    assert cfg["coarse_stage"]["reasoning_effort"] == "max"


def test_claude_code_suffix_ai_coarse_model_is_reported_clearly(monkeypatch):
    monkeypatch.setenv("AI_TRIAGE_ENABLED", "true")
    monkeypatch.setenv("AI_COARSE_ENABLED", "true")
    monkeypatch.setenv("AI_COARSE_MODEL", "deepseek-v4-pro[1m]")
    with pytest.raises(ValueError, match="AI_COARSE_MODEL=deepseek-v4-pro and AI_COARSE_CONTEXT_WINDOW=1m"):
        load_ai_triage_config("configs/ai_triage.yaml")


def test_claude_code_suffix_disabled_ai_coarse_model_falls_back_with_warning(monkeypatch):
    monkeypatch.setenv("AI_COARSE_MODEL", "deepseek-v4-pro[1m]")
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    assert cfg["coarse_stage"]["model"] == "deepseek-v4-pro"
    assert cfg["coarse_stage"]["context_window"] == "1m"
    assert cfg["validation_warnings"] == ["AI_COARSE_MODEL contains Claude Code [1m] suffix; use AI_COARSE_MODEL=deepseek-v4-pro and AI_COARSE_CONTEXT_WINDOW=1m"]


def test_workflow_dispatch_default_inputs_do_not_crash(monkeypatch):
    for name in (
        "AI_TRIAGE_ENABLED",
        "AI_COARSE_ENABLED",
        "AI_COARSE_PROVIDER",
        "AI_COARSE_MODEL",
        "AI_COARSE_REASONING_EFFORT",
        "SOURCE_HN_ENABLED",
        "SOURCE_GDELT_ENABLED",
        "SOURCE_STACKEXCHANGE_ENABLED",
    ):
        monkeypatch.setenv(name, "")
    assert load_ai_triage_config("configs/ai_triage.yaml")["coarse_stage"]["model"] == "deepseek-v4-pro"
    sources = load_sources_config("configs/sources.yaml")
    assert sources["hn_algolia"]["enabled"] is True
    assert sources["gdelt"]["enabled"] is True
    assert sources["stackexchange"]["enabled"] is True


def test_scheduled_deepseek_env_vars_are_optional_unless_feature_enabled(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("AI_TRIAGE_ENABLED", "")
    monkeypatch.setenv("AI_COARSE_ENABLED", "")
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    from agent.ai_triage import ai_provider_dry_run_check

    check = ai_provider_dry_run_check(cfg, provider="deepseek")
    assert check["provider_check_status"] == "ready"
    assert check["missing_secrets"] == []

    monkeypatch.setenv("AI_TRIAGE_ENABLED", "true")
    monkeypatch.setenv("AI_COARSE_ENABLED", "true")
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    check = ai_provider_dry_run_check(cfg, provider="deepseek")
    assert check["provider_check_status"] == "missing_secrets"
    assert check["missing_secrets"] == ["DEEPSEEK_API_KEY"]


def test_ai_coarse_context_window_is_accepted_and_reported(monkeypatch):
    monkeypatch.setenv("AI_COARSE_CONTEXT_WINDOW", "1m")
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    assert cfg["coarse_stage"]["model"] == "deepseek-v4-pro"
    assert cfg["coarse_stage"]["context_window"] == "1m"
    audit = build_config_audit()
    inventory = build_env_inventory()
    assert audit["coarse_context_window"] == "1m"
    assert "AI_COARSE_CONTEXT_WINDOW" in inventory["optional"]


def test_ai_coarse_enable_1m_context_boolean_alias(monkeypatch):
    monkeypatch.setenv("AI_COARSE_ENABLE_1M_CONTEXT", "true")
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    assert cfg["coarse_stage"]["context_window"] == "1m"


def test_daily_agent_defaults_do_not_contain_claude_code_context_suffix():
    assert load_ai_triage_config("configs/ai_triage.yaml")["coarse_stage"]["model"] == "deepseek-v4-pro"
    config_text = Path("configs/ai_triage.yaml").read_text(encoding="utf-8")
    workflow_text = Path(".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "model: deepseek-v4-pro[1m]" not in config_text
    assert "AI_COARSE_MODEL: ${{ vars.AI_COARSE_MODEL || 'deepseek-v4-pro[1m]' }}" not in workflow_text
    assert "ANTHROPIC_MODEL=deepseek-v4-pro[1m]" in Path("docs/two_stage_ai_operator_guide.md").read_text(encoding="utf-8")


def test_send_report_to_test_recipient_forces_email_channel(monkeypatch, tmp_path):
    from agent.delivery import send_daily_report_to_test_recipient

    report = tmp_path / "report.md"
    report.write_text("# Report\n", encoding="utf-8")
    result = send_daily_report_to_test_recipient(report, None, {"final": 1}, {"enabled": False, "channel": "none"})
    assert result["reason"] == "missing_secrets"
    assert result["reason"] != "unsupported_channel"


def test_deepseek_invalid_key_reports_failed_provider_status(monkeypatch):
    from agent.ai_triage import DeepSeekCoarseTriageProvider, ai_provider_dry_run_check

    monkeypatch.setenv("DEEPSEEK_API_KEY", "invalid-test-key")
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    cfg["enabled"] = True
    cfg["dry_run_provider_check"] = True
    cfg["coarse_stage"] = {**cfg["coarse_stage"], "enabled": True, "provider": "deepseek", "dry_run": False}
    cfg["final_stage"] = {**cfg["final_stage"], "enabled": False, "provider": "none"}

    def fail_live_check(self, items):
        raise RuntimeError("unauthorized")

    monkeypatch.setattr(DeepSeekCoarseTriageProvider, "triage", fail_live_check)
    check = ai_provider_dry_run_check(cfg, provider="deepseek")
    assert check["provider_check_status"] == "failed"
    assert check["missing_secrets"] == []
    assert check["stages"]["coarse_stage"]["reason"] == "provider_error:RuntimeError"


def test_cli_malformed_ai_coarse_model_reports_json_error():
    env = os.environ.copy()
    env["AI_TRIAGE_ENABLED"] = "true"
    env["AI_COARSE_ENABLED"] = "true"
    env["AI_COARSE_MODEL"] = "deepseek-v4-pro[1m]"
    proc = subprocess.run([sys.executable, "-m", "agent.main", "--mode", "config-audit"], text=True, env=env, capture_output=True)
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["status"] == "invalid_config"
    assert "AI_COARSE_CONTEXT_WINDOW=1m" in payload["error"]
    assert "reserved for Claude Code" in payload["error"]
    assert "deepseek-v4-pro[1m]" not in proc.stdout
    assert "Traceback" not in proc.stderr
