from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from datetime import UTC, datetime, timezone
from time import perf_counter
from pathlib import Path
from typing import Any
import json
import re


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _elapsed_seconds(start: float | None) -> float | None:
    if start is None:
        return None
    return round(perf_counter() - start, 3)


def _workflow_context() -> dict[str, Any]:
    event = os.getenv("GITHUB_EVENT_NAME", "").strip()
    return {
        "workflow_event": event or None,
        "attempted_from_manual_dispatch": event == "workflow_dispatch" if event else None,
        "scheduled": event == "schedule" if event else None,
        "github_sha": os.getenv("GITHUB_SHA", "").strip() or None,
        "github_ref": os.getenv("GITHUB_REF", "").strip() or None,
        "github_workflow": os.getenv("GITHUB_WORKFLOW", "").strip() or None,
        "github_run_id": os.getenv("GITHUB_RUN_ID", "").strip() or None,
    }


def _sanitize_delivery_error(exc: Exception) -> str:
    text = str(exc)
    replacements = [
        os.getenv("SMTP_PASSWORD", ""),
        os.getenv("SMTP_USERNAME", ""),
        os.getenv("REPORT_SENDER_EMAIL", ""),
        os.getenv("REPORT_TEST_RECIPIENT_EMAIL", ""),
        os.getenv("REPORT_RECIPIENT_EMAIL", ""),
    ]
    for value in replacements:
        if value:
            text = text.replace(value, "[redacted]")
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", text, flags=re.IGNORECASE)
    return text[:500]


def _merge_delivery_status_into_json(path: Path | None, delivery_status: dict[str, Any]) -> None:
    if path is None or not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return
        payload["delivery_status"] = dict(delivery_status)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        return


REQUIRED_SMTP = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "REPORT_SENDER_EMAIL"]


def _resolve_recipient(config: dict[str, Any]) -> tuple[str, str, bool]:
    test_mode = bool(config.get("test_recipient_mode", True))
    if test_mode:
        return (os.getenv("REPORT_TEST_RECIPIENT_EMAIL", "").strip(), "test", True)
    return (os.getenv("REPORT_RECIPIENT_EMAIL", "").strip(), "primary", False)


def delivery_dry_run_check(config: dict[str, Any]) -> dict[str, Any]:
    if not bool(config.get("dry_run_delivery_check", False)):
        return {"status": "skipped", "reason": "disabled", "missing_secrets": []}
    missing = [k for k in REQUIRED_SMTP if not os.getenv(k, "").strip()]
    recipient, _, test_mode = _resolve_recipient(config)
    if not recipient:
        missing.append("REPORT_TEST_RECIPIENT_EMAIL" if test_mode else "REPORT_RECIPIENT_EMAIL")
    if missing:
        return {"status": "skipped", "reason": "missing_secrets", "missing_secrets": sorted(set(missing))}
    return {"status": "ok", "reason": "ready", "missing_secrets": []}


def delivery_check_send(config: dict[str, Any], markdown_path: Path | None = None, json_path: Path | None = None) -> dict[str, Any]:
    enabled = bool(config.get("dry_run_delivery_check", False))
    recipient, _, test_mode = _resolve_recipient(config)
    result = {
        "enabled": enabled,
        "status": "skipped" if not enabled else "failed",
        "reason": "disabled" if not enabled else "missing_secrets",
        "recipient_mode": "test" if test_mode else "primary",
        "sent_to_test_recipient": False,
        "blocked_by_safety": False,
        "missing_secrets": [],
        "error": "",
    }
    if not enabled:
        return result
    if not test_mode:
        result.update({"status": "skipped", "reason": "non_test_recipient_blocked", "blocked_by_safety": True})
        return result
    primary_recipient = os.getenv("REPORT_RECIPIENT_EMAIL", "").strip()
    if primary_recipient and recipient != primary_recipient:
        result["recipient_mode"] = "test"
    missing = [k for k in REQUIRED_SMTP if not os.getenv(k, "").strip()]
    if not recipient:
        missing.append("REPORT_TEST_RECIPIENT_EMAIL")
    if missing:
        result.update({"status": "skipped", "reason": "missing_secrets", "missing_secrets": sorted(set(missing))})
        return result
    body = "China Demand Agent delivery-check test email."
    if markdown_path and markdown_path.exists():
        body = markdown_path.read_text(encoding="utf-8")
    try:
        msg = EmailMessage()
        msg["Subject"] = "China demand delivery-check test"
        msg["From"] = os.environ["REPORT_SENDER_EMAIL"]
        msg["To"] = recipient
        msg.set_content(body)
        if json_path and json_path.exists() and bool(config.get("attach_json_summary", True)):
            msg.add_attachment(json_path.read_bytes(), maintype="application", subtype="json", filename=json_path.name)
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as smtp:
            smtp.starttls()
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return {
            "enabled": True,
            "status": "sent",
            "reason": "test_recipient_delivery_sent",
            "recipient_mode": "test",
            "sent_to_test_recipient": True,
            "blocked_by_safety": False,
            "missing_secrets": [],
            "error": "",
        }
    except Exception as exc:
        return {
            "enabled": True,
            "status": "failed",
            "reason": "smtp_send_failed",
            "sent_to_test_recipient": False,
            "error": _sanitize_delivery_error(exc),
        }


def deliver_report(markdown_path: Path, json_path: Path | None, opportunities_count: int, config: dict[str, Any], summary_counts: dict[str, int] | None = None) -> dict[str, Any]:
    send_perf = perf_counter()
    enabled = bool(config.get("enabled", False))
    channel = str(config.get("channel", "none"))
    recipient, recipient_mode, test_mode = _resolve_recipient(config)
    result = {"enabled": enabled, "status": "disabled" if not enabled else "skipped", "channel": channel, "reason": "delivery_disabled" if not enabled else "not_attempted", "missing_secrets": [], "recipient": "configured" if recipient else "", "recipient_mode": recipient_mode, "test_recipient_mode": test_mode, "blocked_by_safety": False, "dry_run_delivery_check": bool(config.get("dry_run_delivery_check", False)), "sent_to_test_recipient": False, "attachment_count": 0, "error": "", "send_started_at": _utc_now_iso(), "send_finished_at": None, "send_duration_seconds": None, "smtp_started_at": None, "smtp_finished_at": None, "smtp_duration_seconds": None, "report_generated_at": config.get("report_generated_at") or (datetime.fromtimestamp(markdown_path.stat().st_mtime, UTC).isoformat() if markdown_path.exists() else None), **_workflow_context()}
    def finish_delivery() -> dict[str, Any]:
        result["send_finished_at"] = _utc_now_iso()
        result["send_duration_seconds"] = _elapsed_seconds(send_perf)
        return result
    if not enabled:
        return finish_delivery()
    if channel == "smtp":
        channel = "email"
        result["channel"] = "email"
    if channel != "email":
        result.update({"status": "skipped", "reason": "unsupported_channel"})
        return finish_delivery()
    if opportunities_count == 0 and not bool(config.get("send_empty_report", True)):
        result.update({"status": "skipped", "reason": "empty_report_disabled"})
        return finish_delivery()
    if not test_mode and not bool(config.get("allow_non_test_recipient", False)):
        result.update({"status": "skipped", "reason": "non_test_recipient_blocked", "blocked_by_safety": True})
        return finish_delivery()
    if test_mode and os.getenv("REPORT_RECIPIENT_EMAIL", "").strip() and recipient != os.getenv("REPORT_RECIPIENT_EMAIL", "").strip() and not bool(config.get("allow_non_test_recipient", False)):
        result["recipient_mode"] = "test_only"
    missing = [k for k in REQUIRED_SMTP if not os.getenv(k, "").strip()]
    if not recipient:
        missing.append("REPORT_TEST_RECIPIENT_EMAIL" if test_mode else "REPORT_RECIPIENT_EMAIL")
    if missing:
        result.update({"status": "skipped", "reason": "missing_secrets", "missing_secrets": sorted(set(missing))})
        return finish_delivery()
    try:
        port = int(os.environ["SMTP_PORT"])
        msg = EmailMessage()
        msg["Subject"] = "China Demand Daily Report"
        msg["From"] = os.environ["REPORT_SENDER_EMAIL"]
        msg["To"] = recipient
        counts = summary_counts or {}
        msg.set_content(
            "China Demand Daily Report\n"
            f"raw={counts.get('raw', 0)}, qualified={counts.get('qualified', 0)}, "
            f"quick_service_leads={counts.get('quick_service_leads', 0)}, "
            f"product_opportunities={counts.get('product_opportunities', counts.get('final', opportunities_count))}, "
            f"final={counts.get('final', opportunities_count)}"
        )
        attachments = 0
        if markdown_path.exists() and bool(config.get("attach_markdown", True)):
            msg.add_attachment(markdown_path.read_bytes(), maintype="text", subtype="markdown", filename=markdown_path.name)
            attachments += 1
        attach_json = bool(json_path and json_path.exists() and bool(config.get("attach_json_summary", True)))
        if attach_json:
            attachments += 1
            prospective_status = dict(result)
            prospective_status.update({"status": "sent", "reason": "sent", "attachment_count": attachments, "sent_to_test_recipient": test_mode})
            _merge_delivery_status_into_json(json_path, prospective_status)
            msg.add_attachment(json_path.read_bytes(), maintype="application", subtype="json", filename=json_path.name)
        smtp_perf = perf_counter()
        result["smtp_started_at"] = _utc_now_iso()
        with smtplib.SMTP(os.environ["SMTP_HOST"], port) as smtp:
            smtp.starttls(); smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"]); smtp.send_message(msg)
        result["smtp_finished_at"] = _utc_now_iso()
        result["smtp_duration_seconds"] = _elapsed_seconds(smtp_perf)
        result.update({"status": "sent", "reason": "sent", "attachment_count": attachments, "sent_to_test_recipient": test_mode})
        finished = finish_delivery()
        _merge_delivery_status_into_json(json_path, finished)
        return finished
    except Exception as exc:
        if result.get("smtp_started_at") and not result.get("smtp_finished_at"):
            result["smtp_finished_at"] = _utc_now_iso()
            result["smtp_duration_seconds"] = _elapsed_seconds(locals().get("smtp_perf"))
        result.update({"status": "failed", "reason": "smtp_send_failed", "error": _sanitize_delivery_error(exc)})
        failed = finish_delivery()
        _merge_delivery_status_into_json(json_path, failed)
        return failed


def send_daily_report_to_test_recipient(markdown_path: Path, json_path: Path | None, summary_counts: dict[str, int], config: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(config)
    cfg.update({"enabled": True, "channel": "email", "test_recipient_mode": True, "allow_non_test_recipient": False})
    result = deliver_report(markdown_path, json_path, summary_counts.get("final", 0), cfg, summary_counts=summary_counts)
    if result.get("status") == "sent":
        result.update({"enabled": True, "reason": "daily_report_sent_to_test_recipient", "sent_to_test_recipient": True, "error": ""})
    return result


def write_daily_delivery_status(path: Path, delivery_result: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": bool(delivery_result.get("enabled", False)),
        "status": str(delivery_result.get("status", "unknown")),
        "reason": str(delivery_result.get("reason", "unknown")),
        "sent_to_test_recipient": bool(delivery_result.get("sent_to_test_recipient", False)),
        "recipient_mode": str(delivery_result.get("recipient_mode", "unknown")),
        "blocked_by_safety": bool(delivery_result.get("blocked_by_safety", False)),
        "attachment_count": int(delivery_result.get("attachment_count", 0)),
        "missing_secrets": [str(x) for x in delivery_result.get("missing_secrets", [])],
        "error": str(delivery_result.get("error", "")),
        "send_started_at": delivery_result.get("send_started_at"),
        "send_finished_at": delivery_result.get("send_finished_at"),
        "send_duration_seconds": delivery_result.get("send_duration_seconds"),
        "smtp_started_at": delivery_result.get("smtp_started_at"),
        "smtp_finished_at": delivery_result.get("smtp_finished_at"),
        "smtp_duration_seconds": delivery_result.get("smtp_duration_seconds"),
        "report_generated_at": delivery_result.get("report_generated_at"),
        "workflow_event": delivery_result.get("workflow_event"),
        "attempted_from_manual_dispatch": delivery_result.get("attempted_from_manual_dispatch"),
        "scheduled": delivery_result.get("scheduled"),
        "github_sha": delivery_result.get("github_sha"),
        "github_ref": delivery_result.get("github_ref"),
        "github_workflow": delivery_result.get("github_workflow"),
        "github_run_id": delivery_result.get("github_run_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def load_delivery_config(path: str | Path = "configs/delivery.yaml") -> dict[str, Any]:
    from agent.config import load_delivery_config as _ldr
    return _ldr(path)
