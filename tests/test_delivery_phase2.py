from pathlib import Path

import json

from agent.delivery import deliver_report, delivery_check_send, delivery_dry_run_check, send_daily_report_to_test_recipient, write_daily_delivery_status
from agent.main import _delivery_check_config_for_profile


def test_delivery_disabled_by_default(tmp_path):
    md = tmp_path / "r.md"; md.write_text("x", encoding="utf-8")
    res = deliver_report(md, None, 0, {"enabled": False})
    assert res["status"] == "disabled"


def test_delivery_missing_secrets_skips(tmp_path):
    md = tmp_path / "r.md"; md.write_text("x", encoding="utf-8")
    res = deliver_report(md, None, 1, {"enabled": True, "channel": "email"})
    assert res["status"] == "skipped"
    assert res["reason"] == "missing_secrets"


def test_delivery_empty_report_can_skip(tmp_path):
    md = tmp_path / "r.md"; md.write_text("x", encoding="utf-8")
    res = deliver_report(md, None, 0, {"enabled": True, "channel": "email", "send_empty_report": False})
    assert res["reason"] == "empty_report_disabled"


def test_delivery_check_disabled_returns_skipped():
    r = delivery_dry_run_check({"dry_run_delivery_check": False})
    assert r["status"] == "skipped"


def test_delivery_check_requires_test_recipient_in_test_mode():
    r = delivery_dry_run_check({"dry_run_delivery_check": True, "test_recipient_mode": True})
    assert r["status"] == "skipped"
    assert "REPORT_TEST_RECIPIENT_EMAIL" in r["missing_secrets"]


def test_non_test_recipient_blocked(tmp_path):
    md = tmp_path / "r.md"; md.write_text("x", encoding="utf-8")
    res = deliver_report(md, None, 1, {"enabled": True, "channel": "email", "test_recipient_mode": False, "allow_non_test_recipient": False})
    assert res["blocked_by_safety"] is True


def test_delivery_test_recipient_profile_enables_delivery_check_even_if_default_disabled():
    cfg = _delivery_check_config_for_profile("delivery_test_recipient")
    assert cfg["dry_run_delivery_check"] is True
    assert cfg["test_recipient_mode"] is True
    assert cfg["allow_non_test_recipient"] is False


def test_no_secret_default_profile_keeps_delivery_check_disabled():
    cfg = _delivery_check_config_for_profile("no_secret_default")
    assert cfg["dry_run_delivery_check"] is False


class _SMTPStub:
    def __init__(self, *_args, **_kwargs):
        self.sent = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def starttls(self):
        return None

    def login(self, *_args):
        return None

    def send_message(self, _msg):
        self.sent = True


def _set_delivery_env(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    monkeypatch.setenv("REPORT_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("REPORT_TEST_RECIPIENT_EMAIL", "test@example.com")


def test_delivery_check_profile_sends_with_valid_secrets(monkeypatch, tmp_path):
    _set_delivery_env(monkeypatch)
    monkeypatch.setattr("agent.delivery.smtplib.SMTP", _SMTPStub)
    md = tmp_path / "r.md"; md.write_text("body", encoding="utf-8")
    r = delivery_check_send({"dry_run_delivery_check": True, "test_recipient_mode": True, "allow_non_test_recipient": False}, md, None)
    assert r["status"] == "sent"
    assert r["reason"] == "test_recipient_delivery_sent"
    assert r["sent_to_test_recipient"] is True


def test_delivery_check_returns_failed_on_smtp_error(monkeypatch):
    class _SMTPFail(_SMTPStub):
        def send_message(self, _msg):
            raise RuntimeError("smtp exploded")
    _set_delivery_env(monkeypatch)
    monkeypatch.setattr("agent.delivery.smtplib.SMTP", _SMTPFail)
    r = delivery_check_send({"dry_run_delivery_check": True, "test_recipient_mode": True, "allow_non_test_recipient": False})
    assert r["status"] == "failed"
    assert r["reason"] == "smtp_send_failed"
    assert r["sent_to_test_recipient"] is False


def test_delivery_check_blocks_non_test_recipient(monkeypatch):
    _set_delivery_env(monkeypatch)
    r = delivery_check_send({"dry_run_delivery_check": True, "test_recipient_mode": False, "allow_non_test_recipient": False})
    assert r["status"] == "skipped"
    assert r["reason"] == "non_test_recipient_blocked"


def test_delivery_check_missing_secrets_does_not_send():
    r = delivery_check_send({"dry_run_delivery_check": True, "test_recipient_mode": True, "allow_non_test_recipient": False})
    assert r["status"] == "skipped"
    assert r["reason"] == "missing_secrets"


def test_manual_report_delivery_sends_with_attachments(monkeypatch, tmp_path):
    _set_delivery_env(monkeypatch)
    monkeypatch.setattr("agent.delivery.smtplib.SMTP", _SMTPStub)
    md = tmp_path / "daily-demand-report.md"; md.write_text("# report", encoding="utf-8")
    js = tmp_path / "daily-demand-summary.json"; js.write_text("{}", encoding="utf-8")
    r = send_daily_report_to_test_recipient(md, js, {"raw": 10, "qualified": 3, "final": 2}, {"attach_json_summary": True})
    assert r["status"] == "sent"
    assert r["reason"] == "daily_report_sent_to_test_recipient"
    assert r["attachment_count"] == 2


def test_delivery_status_json_written_when_send_attempted(monkeypatch, tmp_path):
    _set_delivery_env(monkeypatch)
    monkeypatch.setattr("agent.delivery.smtplib.SMTP", _SMTPStub)
    md = tmp_path / "daily-demand-report.md"; md.write_text("# report", encoding="utf-8")
    js = tmp_path / "daily-demand-summary.json"; js.write_text("{}", encoding="utf-8")
    result = send_daily_report_to_test_recipient(md, js, {"raw": 1, "qualified": 1, "final": 1}, {"attach_json_summary": True})
    out = write_daily_delivery_status(tmp_path / "daily-delivery-status.json", result)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "sent"
    assert payload["sent_to_test_recipient"] is True
    assert payload["attachment_count"] == 2
    assert "generated_at" in payload
    assert payload["send_started_at"]
    assert payload["send_finished_at"]
    assert isinstance(payload["send_duration_seconds"], (int, float))
    assert payload["smtp_started_at"]
    assert payload["smtp_finished_at"]
    assert isinstance(payload["smtp_duration_seconds"], (int, float))
    assert payload["report_generated_at"]
    assert "workflow_event" in payload
    assert "attempted_from_manual_dispatch" in payload
    assert "scheduled" in payload


def test_manual_report_delivery_missing_report_fails_clearly(monkeypatch, tmp_path):
    _set_delivery_env(monkeypatch)
    r = send_daily_report_to_test_recipient(tmp_path / "missing.md", None, {"raw": 0, "qualified": 0, "final": 0}, {})
    assert r["status"] == "failed"
    assert r["reason"] == "smtp_send_failed"


def test_manual_report_delivery_forces_email_channel(monkeypatch, tmp_path):
    _set_delivery_env(monkeypatch)
    monkeypatch.setattr("agent.delivery.smtplib.SMTP", _SMTPStub)
    md = tmp_path / "daily-demand-report.md"; md.write_text("# report", encoding="utf-8")
    js = tmp_path / "daily-demand-summary.json"; js.write_text("{}", encoding="utf-8")
    result = send_daily_report_to_test_recipient(
        md,
        js,
        {"raw": 1, "qualified": 1, "final": 1},
        {"enabled": True, "channel": "slack", "attach_json_summary": True},
    )
    assert result["status"] == "sent"
    assert result["reason"] == "daily_report_sent_to_test_recipient"
    assert result["channel"] == "email"
    assert result["sent_to_test_recipient"] is True
    assert result["reason"] != "unsupported_channel"


def test_delivery_status_json_includes_github_runtime_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_WORKFLOW", "Daily Demand Pipeline")
    monkeypatch.setenv("GITHUB_RUN_ID", "987")
    _set_delivery_env(monkeypatch)
    monkeypatch.setattr("agent.delivery.smtplib.SMTP", _SMTPStub)
    md = tmp_path / "daily-demand-report.md"; md.write_text("# report", encoding="utf-8")
    result = send_daily_report_to_test_recipient(md, None, {"raw": 1, "qualified": 1, "final": 1}, {})
    out = write_daily_delivery_status(tmp_path / "daily-delivery-status.json", result)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["workflow_event"] == "schedule"
    assert payload["scheduled"] is True
    assert payload["github_sha"] == "abc123"
    assert payload["github_ref"] == "refs/heads/main"
    assert payload["github_workflow"] == "Daily Demand Pipeline"
    assert payload["github_run_id"] == "987"

class _SMTPCapture(_SMTPStub):
    messages = []

    def send_message(self, msg):
        type(self).messages.append(msg)
        self.sent = True


def _json_attachment_payload(msg):
    for part in msg.iter_attachments():
        if part.get_filename() == "daily-demand-summary.json":
            return json.loads(part.get_content())
    raise AssertionError("daily-demand-summary.json attachment not found")


def test_explicit_test_recipient_ignores_channel_none_and_attaches_sent_json(monkeypatch, tmp_path):
    _set_delivery_env(monkeypatch)
    _SMTPCapture.messages = []
    monkeypatch.setattr("agent.delivery.smtplib.SMTP", _SMTPCapture)
    md = tmp_path / "daily-demand-report.md"; md.write_text("# report", encoding="utf-8")
    js = tmp_path / "daily-demand-summary.json"; js.write_text(json.dumps({"delivery_status": {"status": "skipped", "reason": "unsupported_channel"}}), encoding="utf-8")

    result = send_daily_report_to_test_recipient(
        md,
        js,
        {"raw": 1, "qualified": 1, "quick_service_leads": 0, "product_opportunities": 0, "final": 0},
        {"enabled": False, "channel": "none", "attach_json_summary": True},
    )

    assert result["status"] == "sent"
    assert result["sent_to_test_recipient"] is True
    assert result["channel"] == "email"
    assert result["reason"] != "unsupported_channel"
    written = json.loads(js.read_text(encoding="utf-8"))
    assert written["delivery_status"]["status"] == "sent"
    assert written["delivery_status"]["sent_to_test_recipient"] is True
    attached = _json_attachment_payload(_SMTPCapture.messages[0])
    assert attached["delivery_status"]["status"] == "sent"
    assert attached["delivery_status"]["sent_to_test_recipient"] is True


def test_explicit_test_recipient_missing_secrets_not_unsupported_channel(tmp_path):
    md = tmp_path / "daily-demand-report.md"; md.write_text("# report", encoding="utf-8")
    js = tmp_path / "daily-demand-summary.json"; js.write_text("{}", encoding="utf-8")
    result = send_daily_report_to_test_recipient(md, js, {"final": 1}, {"channel": "none"})
    assert result["reason"] == "missing_secrets"
    assert result["reason"] != "unsupported_channel"
    assert result["channel"] == "email"


def test_explicit_test_recipient_smtp_error_is_sanitized(monkeypatch, tmp_path):
    class _SMTPFail(_SMTPStub):
        def send_message(self, _msg):
            raise RuntimeError("smtp exploded for test@example.com with p")

    _set_delivery_env(monkeypatch)
    monkeypatch.setattr("agent.delivery.smtplib.SMTP", _SMTPFail)
    md = tmp_path / "daily-demand-report.md"; md.write_text("# report", encoding="utf-8")
    js = tmp_path / "daily-demand-summary.json"; js.write_text("{}", encoding="utf-8")
    result = send_daily_report_to_test_recipient(md, js, {"final": 1}, {"channel": "none"})
    assert result["status"] == "failed"
    assert result["reason"] == "smtp_send_failed"
    assert "test@example.com" not in result["error"]
    assert " p" not in result["error"]
