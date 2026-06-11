from agent.production_audit import run_production_audit


def test_production_audit_passes_no_secret_env():
    summary = run_production_audit()
    assert isinstance(summary["checks"], list)
    assert summary["ok"] is True
    assert summary["no_secret_safe"] is True


def test_production_audit_ai_missing_secrets(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    summary = run_production_audit()
    assert "missing_ai_secrets" in summary


def test_production_audit_delivery_keys_present_field():
    summary = run_production_audit()
    assert "missing_delivery_secrets" in summary


def test_production_audit_reports_codex_not_implemented():
    summary = run_production_audit()
    assert summary["true_codex_sdk_supported"] is False
    assert summary["true_codex_sdk_enabled"] is False
    assert "OpenAI Responses API" in summary["true_codex_sdk_note"]
    assert summary["openai_final_supported"] is True
