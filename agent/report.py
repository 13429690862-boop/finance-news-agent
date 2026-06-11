"""Markdown and JSON report generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from agent.demand_classifier import summarize_compliance, summarize_quick_service_leads, summarize_requester_attribution


def _opportunity_to_dict(opportunity: Any) -> dict[str, Any]:
    if isinstance(opportunity, Mapping):
        return dict(opportunity)
    if hasattr(opportunity, "model_dump"):
        return opportunity.model_dump()
    return opportunity.__dict__.copy()


def _sorted_records(opportunities: list[Any]) -> list[dict[str, Any]]:
    records = [_opportunity_to_dict(opportunity) for opportunity in opportunities]
    records.sort(key=_score_value, reverse=True)
    return records


def _sorted_leads(leads: list[Any]) -> list[dict[str, Any]]:
    records = [_opportunity_to_dict(lead) for lead in leads]
    records.sort(key=lambda row: (int(row.get("monetization_score", 0) or 0), int(row.get("urgency_score", 0) or 0), int(row.get("simplicity_score", 0) or 0)), reverse=True)
    return records


def _score_value(opportunity: dict[str, Any]) -> float:
    value = opportunity.get("opportunity_score", opportunity.get("score", 0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _display_score(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _priority_counts(opportunities: list[dict[str, Any]]) -> dict[str, int]:
    return {
        priority: sum(1 for opportunity in opportunities if opportunity.get("priority") == priority)
        for priority in ("high", "medium", "low")
    }


def _evidence_urls(opportunity: dict[str, Any]) -> list[str]:
    urls = opportunity.get("evidence_urls")
    if isinstance(urls, list):
        return [str(url) for url in urls]
    url = opportunity.get("url")
    return [str(url)] if url else []


def _evidence_quotes(opportunity: dict[str, Any]) -> list[str]:
    quotes = opportunity.get("evidence_quotes")
    if isinstance(quotes, list):
        return [str(quote) for quote in quotes]
    return []


def _generated_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _table_text(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

def _severity_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(value).lower(), 9)




def _source_recall_rows(telemetry: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = []
    src_t = (telemetry or {}).get("source_telemetry", {}) if isinstance(telemetry, Mapping) else {}
    for source, bucket in src_t.items():
        role = "supporting/news" if source == "gdelt" or str(bucket.get("source_type", "")).lower() == "news" else ("technical/api workflows" if source == "stackexchange" else "primary discovery")
        collected = int(bucket.get("collected_count", 0) or 0)
        qualified = int(bucket.get("qualified_raw_count", 0) or 0)
        final_count = int(bucket.get("final_qualified_count", 0) or 0)
        top_rejection_reason = "none"
        reason_counts = bucket.get("rejection_reason_counts", {})
        if isinstance(reason_counts, Mapping) and reason_counts:
            top_rejection_reason = str(next(iter(sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)))[0])
        diagnostic = "healthy"
        action = "monitor"
        if source == "stackexchange" and collected == 0 and int((bucket.get("attempted_query_count", 0) or (int(bucket.get("strict_query_count", 0) or 0) + int(bucket.get("fallback_query_count", 0) or 0) or int(bucket.get("query_count", 0) or 0)))) > 0:
            diagnostic = "zero recall despite strict+fallback query attempts"
            action = "review_source_profile"
        elif source == "stackexchange" and collected > 0 and qualified == 0:
            diagnostic = "collected but quality rejected; query precision low or demand signals missing"
            action = "narrow_stackexchange_query_terms"
        elif source == "gdelt" and collected > 0 and qualified == 0:
            diagnostic = "collected but quality rejected; keep supporting-only"
            action = "keep_supporting_only"
        elif source == "hn_algolia" and qualified > 0 and final_count == 0:
            diagnostic = "collected demand-adjacent content; final filter correctly strict"
            action = "refine_demand_shaped_queries"
        rows.append({"source": source, "role": role, "query_count": bucket.get("query_count", 0), "site_count": bucket.get("site_count", 1), "collected": collected, "qualified": qualified, "final": final_count, "diagnostic": diagnostic, "recommended_next_action": action, "top_rejection_reason": top_rejection_reason})
    return sorted(rows, key=lambda r: r["source"])


def _fmt_timing_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _timing_status(timing: Mapping[str, Any], stage: str) -> str:
    statuses = timing.get("stage_statuses", {})
    if isinstance(statuses, Mapping):
        return str(statuses.get(stage, "not_attempted"))
    return "not_attempted"


def _timing_rows(timing: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    t = timing or {}
    stages = [
        ("collect", "collect"),
        ("quality_gate", "quality_gate"),
        ("deepseek_coarse", "ai_coarse"),
        ("quick_service_classifier", "quick_service_classifier"),
        ("analyzer", "analyzer"),
        ("final_filter", "final_filter"),
        ("report_generation", "report"),
        ("delivery_send", "delivery_send"),
    ]
    return [
        {
            "stage": stage,
            "started_at": t.get(f"{prefix}_started_at"),
            "finished_at": t.get(f"{prefix}_finished_at"),
            "duration_seconds": t.get(f"{prefix}_duration_seconds"),
            "status": _timing_status(t, stage),
        }
        for stage, prefix in stages
    ]


def _delivery_status_lines(delivery_status: Mapping[str, Any]) -> list[str]:
    """Render operator-friendly Markdown delivery status without stale raw JSON."""
    status = str(delivery_status.get("status", "unknown") or "unknown")
    enabled = bool(delivery_status.get("enabled", False))
    delivery_expected = bool(delivery_status.get("delivery_expected_after_report_generation", False)) or status == "pending_send"
    channel = str(delivery_status.get("channel", "email") or "email")
    recipient_mode = str(delivery_status.get("recipient_mode", "test" if delivery_status.get("sent_to_test_recipient") else "production") or "production")

    if delivery_expected and status in {"pending_send", "not_attempted", "disabled"}:
        return [
            "- Status at report generation: pending_send",
            f"- Channel: {channel}",
            f"- Recipient mode: {recipient_mode}",
            "- Final delivery status: see daily-demand-summary.json / daily-delivery-status.json",
        ]

    if not enabled and status in {"not_attempted", "disabled"}:
        return [
            "- Status: not_attempted",
            "- Reason: delivery disabled",
        ]

    lines = [f"- Status: {status}"]
    if channel:
        lines.append(f"- Channel: {channel}")
    if recipient_mode:
        lines.append(f"- Recipient mode: {recipient_mode}")
    reason = delivery_status.get("reason")
    if reason:
        lines.append(f"- Reason: {reason}")
    if "sent_to_test_recipient" in delivery_status:
        lines.append(f"- Sent to test recipient: {bool(delivery_status.get('sent_to_test_recipient'))}")
    lines.append("- JSON remains authoritative for final delivery status.")
    return lines

def generate_markdown_report(
    opportunities: list[Any],
    output_path: str | Path,
    source_statuses: Mapping[str, Any] | None = None,
    analyzer_mode: str = "rule_based",
    quality_summary: Mapping[str, Any] | None = None,
    final_filter_summary: Mapping[str, Any] | None = None,
    telemetry: Mapping[str, Any] | None = None,
    recall_diagnostics: Mapping[str, Any] | None = None,
    query_adjustment_proposals: list[dict[str, Any]] | None = None,
    ai_triage_summary: Mapping[str, Any] | None = None,
    delivery_status: Mapping[str, Any] | None = None,
    timing_diagnostics: Mapping[str, Any] | None = None,
    quick_service_leads: list[Any] | None = None,
    blocked_quick_service_items: list[dict[str, Any]] | None = None,
) -> Path:
    """Generate a polished Markdown report from opportunity objects or dict fixtures."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    records = _sorted_records(opportunities)
    leads = _sorted_leads(quick_service_leads or [])
    blocked_leads = list(blocked_quick_service_items or [])
    counts = _priority_counts(records)
    qs = quality_summary or {}
    ff = final_filter_summary or {}
    qsl_summary = summarize_quick_service_leads(leads, blocked_leads)
    compliance_summary = summarize_compliance(leads, blocked_leads)

    lines = [
        "# China Demand Opportunities Report",
        "",
        f"Generated at: {_generated_at()}",
        "",
        "## Executive Summary",
        "",
        f"Total raw items: {qs.get('total_raw_items', 'n/a')}",
        f"Qualified raw items: {qs.get('qualified_raw_items', 'n/a')}",
        f"Rejected raw items: {qs.get('rejected_raw_items', 'n/a')}",
        f"Quick service leads: {len(leads)}",
        f"Product opportunities: {len(records)}",
        f"Total opportunities: {len(records)}",
        f"High priority: {counts['high']}",
        f"Medium priority: {counts['medium']}",
        f"Low priority: {counts['low']}",
        f"Analyzer mode: {analyzer_mode}",
        "",
        (
            "This report ranks deterministic demand opportunities generated from collected source "
            "items. Scores are rule-based and should be validated with fresh evidence before "
            "any product or go-to-market commitment."
        ),
        "",
        "## Quick Service Leads",
        "",
        "| Rank | Demand | Requested service | Source | Requester | Compliance risk | Monetization score | Suggested next step | Evidence |",
        "| --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]

    if not leads:
        lines.append("No quick service leads found today.")

    lines.extend([
        "",
        f"Quick service candidates reviewed: {qsl_summary.get('candidate_count', len(leads) + len(blocked_leads))}",
        f"Quick service accepted: {qsl_summary.get('accepted_count', len(leads))}",
        f"quick_service_rejected_article_count: {qsl_summary.get('quick_service_rejected_article_count', 0)}",
        f"quick_service_rejected_no_request_count: {qsl_summary.get('quick_service_rejected_no_request_count', 0)}",
        f"quick_service_rejected_provider_side_count: {qsl_summary.get('quick_service_rejected_provider_side_count', 0)}",
        f"quick_service_rejected_product_launch_count: {qsl_summary.get('quick_service_rejected_product_launch_count', 0)}",
        "",
    ])

    for index, lead in enumerate(leads, start=1):
        requester = lead.get("requester", {}) if isinstance(lead.get("requester"), Mapping) else {}
        requester_label = requester.get("requester_display_name") or requester.get("requester_handle") or "unknown"
        lines.append(
            f"| {index} | {_table_text(lead.get('title', 'Untitled lead'))} | {_table_text(lead.get('requested_service', 'n/a'))} | {_table_text(lead.get('source', 'n/a'))} | {_table_text(requester_label)} | {_table_text(lead.get('compliance_risk', 'unknown'))} | {_table_text(lead.get('monetization_score', 'n/a'))} | {_table_text(lead.get('suggested_next_step', 'n/a'))} | {_table_text(lead.get('evidence_excerpt', 'n/a'))} |"
        )

    lines.extend([
        "",
        "## Top Opportunities",
        "",
        "See Product Opportunities below; Track B remains strict.",
        "",
        "## Product Opportunities",
        "",
        "| Rank | Title | Priority | Opportunity score | Weighted score | Customer type |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ])

    if not records:
        lines.append("No product opportunities found today.")
        lines.append("No qualified opportunities found today.")

    for index, opportunity in enumerate(records, start=1):
        lines.append(
            "| {rank} | {title} | {priority} | {score} | {weighted} | {customer_type} |".format(
                rank=index,
                title=_table_text(opportunity.get("title", "Untitled opportunity")),
                priority=_table_text(opportunity.get("priority", "unknown")),
                score=_display_score(opportunity.get("opportunity_score", opportunity.get("score", "unknown"))),
                weighted=_display_score(opportunity.get("weighted_score", "n/a")),
                customer_type=_table_text(opportunity.get("customer_type", "n/a")),
            )
        )

    lines.extend([
        "",
        "## Requester Attribution Notes",
        "",
        "- Only public source metadata already returned by source APIs is used.",
        "- Usernames/display names are not treated as real identities and no identity inference is performed.",
        "- `contact_allowed=false` by default; any source reply/profile review is manual and outside the pipeline.",
        "- Private contact details are not collected; public emails/phones in source text are redacted in excerpts.",
        "",
        "## Compliance Notes",
        "",
        f"- Quick service leads by risk: low={compliance_summary.get('low', 0)}, medium={compliance_summary.get('medium', 0)}, high={compliance_summary.get('high', 0)}, blocked={compliance_summary.get('blocked', 0)}.",
        f"- High monetization leads: {qsl_summary.get('high_monetization_count', 0)}.",
        "- Blocked categories include KYC/identity evasion, account selling, payment fraud, credential sharing, sanctions/export-control evasion, impersonation, private-data scraping, and spam outreach.",
    ])
    lines.extend(["", "## Quality Gate Summary", "", "| Source | Raw | Qualified | Rejected |", "| --- | ---: | ---: | ---: |"])
    for source, status in (qs.get("source_quality", {}) or {}).items():
        lines.append(f"| {_table_text(source)} | {_table_text((status or {}).get('raw', 0))} | {_table_text((status or {}).get('qualified', 0))} | {_table_text((status or {}).get('rejected', 0))} |")

    lines.extend(["", "## Rejection Reasons", "", "| Reason | Count |", "| --- | ---: |"])
    reasons = dict(sorted((qs.get("rejection_reasons", {}) or {}).items(), key=lambda x: x[1], reverse=True))
    if reasons:
        for reason, count in reasons.items():
            lines.append(f"| {_table_text(reason)} | {_table_text(count)} |")
    else:
        lines.append("| none | 0 |")

    lines.extend(["", "## Sample Rejected Items", "", "| Title | Source | Rejection reasons |", "| --- | --- | --- |"])
    samples = qs.get("sample_rejected_items", []) or []
    if samples:
        for sample in samples:
            lines.append(f"| {_table_text(sample.get('title', 'n/a'))} | {_table_text(sample.get('source', 'n/a'))} | {_table_text(', '.join(sample.get('rejection_reasons', [])))} |")
    else:
        lines.append("| none | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Final Opportunity Filter Summary",
            "",
            f"Analyzed opportunities before final filter: {ff.get('analyzed_before_final_filter', len(records))}",
            f"Final qualified opportunities: {ff.get('final_qualified_opportunities', len(records))}",
            f"Final rejected opportunities: {ff.get('final_rejected_opportunities', 0)}",
            "",
            "| Final rejection reason | Count |",
            "| --- | ---: |",
        ]
    )
    final_reasons = dict(sorted((ff.get("final_rejection_reasons", {}) or {}).items(), key=lambda x: x[1], reverse=True))
    if final_reasons:
        for reason, count in final_reasons.items():
            lines.append(f"| {_table_text(reason)} | {_table_text(count)} |")
    else:
        lines.append("| none | 0 |")

    raw_items = int(qs.get("total_raw_items", 0) or 0)
    final_count = len(records)
    recall_notes = ["- The pipeline found raw items and applied deterministic quality and final filters."]
    if raw_items == 0:
        recall_notes.append("- No raw items were collected in this run; verify collector availability and query coverage.")
    elif final_count == 0:
        recall_notes.append("- Zero final opportunities is acceptable when no explicit China workflow demand is present.")
    else:
        recall_notes.append("- The pipeline found final candidate opportunities after deterministic filtering. Validate each candidate manually before acting.")
    recall_notes.append("- Suggested next action: expand demand-oriented queries or add stronger demand-oriented sources.")
    if any((st or {}).get("status") != "ok" for st in (source_statuses or {}).values()):
        recall_notes.append("- Some sources reported failures or degraded status; interpret recall with source health caveats.")

    lines.extend(["", "## Recall Notes", "", *recall_notes])
    telem = telemetry or {}
    src_t = telem.get("source_telemetry", {}) if isinstance(telem, Mapping) else {}
    lines.extend(["", "## Source Telemetry", "", "| Source | Status | Queries | Collected | Deduped Raw | Quality Input | Qualified Raw | Rejected Raw | Analyzed | Final Qualified | Final Rejected |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for source, bucket in src_t.items():
        lines.append(f"| {_table_text(source)} | {_table_text(bucket.get('status', 'unknown'))} | {_table_text(bucket.get('query_count', 0))} | {_table_text(bucket.get('collected_count', 0))} | {_table_text(bucket.get('deduped_raw_count', 0))} | {_table_text(bucket.get('quality_gate_input_count', 0))} | {_table_text(bucket.get('qualified_raw_count', 0))} | {_table_text(bucket.get('rejected_raw_count', 0))} | {_table_text(bucket.get('analyzed_candidate_count', 0))} | {_table_text(bucket.get('final_qualified_count', 0))} | {_table_text(bucket.get('final_rejected_count', 0))} |")
    cat_t = sorted((telem.get("category_telemetry", {}) if isinstance(telem, Mapping) else {}).values(), key=lambda b: b.get("collected_count", 0), reverse=True)
    lines.extend(["", "## Category Telemetry", "", "| Category | Sources | Queries | Collected | Qualified Raw | Rejected Raw | Final Qualified | Final Rejected | Top Rejection Reason |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"])
    for bucket in cat_t[:20]:
        rr = bucket.get("rejection_reason_counts", {}) or {}
        top = next(iter(sorted(rr.items(), key=lambda x: x[1], reverse=True)), ("none", 0))[0]
        lines.append(f"| {_table_text(bucket.get('category', 'uncategorized'))} | {_table_text(len(bucket.get('sources', [])))} | {_table_text(bucket.get('query_count', 0))} | {_table_text(bucket.get('collected_count', 0))} | {_table_text(bucket.get('qualified_raw_count', 0))} | {_table_text(bucket.get('rejected_raw_count', 0))} | {_table_text(bucket.get('final_qualified_count', 0))} | {_table_text(bucket.get('final_rejected_count', 0))} | {_table_text(top)} |")
    lines.append("Count semantics: Collected = before cross-source dedupe; Deduped Raw = retained after dedupe; Qualified Raw = accepted by quality gate; Final Qualified = survived final opportunity filter.")

    rows = _source_recall_rows(telemetry)
    lines.extend(["", "## Source Recall Diagnostics", "", "| Source | Role | Query count | Site count | Collected | Qualified | Final | Top rejection reason | Diagnostic |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |"])
    if rows:
        for row in rows:
            lines.append(f"| {_table_text(row['source'])} | {_table_text(row['role'])} | {_table_text(row['query_count'])} | {_table_text(row['site_count'])} | {_table_text(row['collected'])} | {_table_text(row['qualified'])} | {_table_text(row['final'])} | {_table_text(row['top_rejection_reason'])} | {_table_text(row['diagnostic'])} |")
    else:
        lines.append("| none | n/a | 0 | 0 | 0 | 0 | 0 | none | no telemetry available |")

    recs = (recall_diagnostics or {}).get("source_recommendations", []) + (recall_diagnostics or {}).get("category_recommendations", [])
    recs = sorted(recs, key=lambda r: (_severity_rank(r.get("severity", "low")), r.get("scope", ""), r.get("name", ""), r.get("problem_type", "")))
    lines.extend(["", "## Recall Optimization Recommendations", "", "| Scope | Name | Problem | Severity | Recommended action | Rationale |", "| --- | --- | --- | --- | --- | --- |"])
    if recs:
        for rec in recs[:10]:
            lines.append(f"| {_table_text(rec.get('scope', 'n/a'))} | {_table_text(rec.get('name', 'n/a'))} | {_table_text(rec.get('problem_type', 'n/a'))} | {_table_text(rec.get('severity', 'n/a'))} | {_table_text(rec.get('recommended_action', 'n/a'))} | {_table_text(rec.get('rationale', 'n/a'))} |")
    else:
        lines.append("| none | n/a | n/a | n/a | n/a | n/a |")



    proposals = sorted((query_adjustment_proposals or []), key=lambda r: (_severity_rank(r.get("risk_level", "low")), r.get("scope", ""), r.get("name", ""), r.get("problem_type", "")))
    lines.extend(["", "## Query/Profile Adjustment Proposals", "", "| Scope | Name | Problem | Action | Risk | Proposed additions | Proposed removals | Rationale |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    if proposals:
        for proposal in proposals[:10]:
            lines.append(f"| {_table_text(proposal.get('scope', 'n/a'))} | {_table_text(proposal.get('name', 'n/a'))} | {_table_text(proposal.get('problem_type', 'n/a'))} | {_table_text(proposal.get('proposed_action', 'n/a'))} | {_table_text(proposal.get('risk_level', 'n/a'))} | {_table_text(', '.join(proposal.get('proposed_query_additions', [])))} | {_table_text(', '.join(proposal.get('proposed_query_removals', [])))} | {_table_text(proposal.get('rationale', 'n/a'))} |")
    else:
        lines.append("| none | n/a | n/a | n/a | n/a | n/a | n/a | no query/profile adjustment proposals generated. |")
    if ai_triage_summary is not None:
        ai = dict(ai_triage_summary)
        coarse = dict(ai.get("deepseek_coarse_status", {}))
        final = dict(ai.get("openai_final_status", {}))
        lines.extend([
            "",
            "## AI Triage Summary",
            "",
            f"- Enabled: {ai.get('enabled', False)}",
            f"- Deterministic filters authoritative: {not ai.get('allow_ai_to_bypass_final_filter', False)}",
            f"- Coarse input/kept/dropped/failed: {ai.get('ai_coarse_input_count', 0)}/{ai.get('ai_coarse_kept_count', 0)}/{ai.get('ai_coarse_dropped_count', 0)}/{ai.get('ai_coarse_failed_count', 0)}",
            f"- Final input/scored/failed: {ai.get('ai_final_input_count', 0)}/{ai.get('ai_final_scored_count', 0)}/{ai.get('ai_final_failed_count', 0)}",
            "",
            "### DeepSeek Coarse Triage Summary",
            "",
            f"- Status: {coarse.get('status', 'disabled')}",
            f"- Provider/model: {coarse.get('provider', 'none')}/{coarse.get('model', '')}",
            f"- DeepSeek coarse model: {coarse.get('model', '') or 'n/a'}",
            f"- Context window intent: {coarse.get('context_window', 'default') or 'default'}",
            f"- Reasoning effort: {coarse.get('reasoning_effort', '') or 'n/a'}",
            f"- Reason: {coarse.get('reason', 'n/a')}",
            f"- Fallback used: {coarse.get('fallback_used', False)}",
            "",
            "### OpenAI Responses Final Scoring Summary",
            "",
            f"- Status: {final.get('status', 'disabled')}",
            f"- Provider/model: {final.get('provider', 'none')}/{final.get('model', '')}",
            f"- Reason: {final.get('reason', 'n/a')}",
            f"- Fallback used: {final.get('fallback_used', False)}",
            "",
            "### True Codex SDK / Local Agent Status",
            "",
            f"- Supported: {ai.get('true_codex_sdk_supported', False)}",
            f"- Enabled: {ai.get('true_codex_sdk_enabled', False)}",
            f"- Note: {ai.get('true_codex_sdk_note', 'Not implemented; current final scoring uses OpenAI Responses API.')}",
        ])
    if delivery_status is not None:
        lines.extend(["", "## Delivery Status", "", *_delivery_status_lines(dict(delivery_status))])

    lines.extend(["", "## Source Status", "", "| Source | Status | Count |", "| --- | --- | ---: |"])
    for source, status in (source_statuses or {}).items():
        lines.append(f"| {_table_text(source)} | {_table_text((status or {}).get('status', 'unknown'))} | {_table_text((status or {}).get('count', 0))} |")

    warnings = [
        f"{s}: {(st or {}).get('status', 'unknown')} count={(st or {}).get('count', 0)}"
        for s, st in (source_statuses or {}).items()
        if (st or {}).get("status") != "ok" or int((st or {}).get("count", 0)) == 0
    ]
    lines.extend(["", "## Warnings", ""])
    lines.extend((f"- {w}" for w in warnings),)
    if not warnings:
        lines.append("- none")

    lines.extend(["", "## Timing Diagnostics", "", "| Stage | Started at | Finished at | Duration seconds | Status |", "| --- | --- | --- | ---: | --- |"])
    for row in _timing_rows(timing_diagnostics):
        lines.append(
            f"| {_table_text(row['stage'])} | {_table_text(_fmt_timing_value(row['started_at']))} | {_table_text(_fmt_timing_value(row['finished_at']))} | {_table_text(_fmt_timing_value(row['duration_seconds']))} | {_table_text(row['status'])} |"
        )
    lines.append("Delivery timing may complete after Markdown generation; final send/SMTP timing is authoritative in reports/daily-delivery-status.json when delivery is attempted.")

    lines.extend(["", "## Opportunity Details", ""])

    for index, opportunity in enumerate(records, start=1):
        title = opportunity.get("title", "Untitled opportunity")
        priority = opportunity.get("priority", "unknown")
        score = opportunity.get("opportunity_score", opportunity.get("score", "unknown"))
        urls = _evidence_urls(opportunity)
        quotes = _evidence_quotes(opportunity)
        risk_notes = opportunity.get("risk_notes", "Not provided")
        next_validation_step = opportunity.get("next_validation_step", "Not provided")

        lines.extend(
            [
                f"### {index}. {title}",
                "",
                f"- Priority: {priority}",
                f"- Opportunity score: {_display_score(score)}",
                f"- Weighted score: {_display_score(opportunity.get('weighted_score', 'n/a'))}",
                f"- Cluster/source/evidence counts: cluster_size={opportunity.get('cluster_size', 1)}, source_count={opportunity.get('source_count', 1)}, evidence_count={opportunity.get('evidence_count', len(urls) + len(quotes))}",
                f"- Historical status: {opportunity.get('history_status', 'n/a')}",
                f"- Quality flags: {', '.join(opportunity.get('quality_flags', [])) if opportunity.get('quality_flags') else 'none'}",
                "- Score breakdown:",
                f"  - Market intensity: {opportunity.get('market_intensity_score', 'n/a')}",
                f"  - China relevance: {opportunity.get('china_relevance_score', 'n/a')}",
                f"  - Monetization clarity: {opportunity.get('monetization_clarity_score', 'n/a')}",
                f"  - Implementation difficulty: {opportunity.get('implementation_difficulty_score', 'n/a')}",
                f"- Customer type: {opportunity.get('customer_type', 'Not provided')}",
                f"- Pain point: {opportunity.get('pain_point', 'Not provided')}",
                f"- Possible solution: {opportunity.get('possible_solution', 'Not provided')}",
                f"- Monetization model: {opportunity.get('monetization_model', 'Not provided')}",
                f"- AI final score: {_display_score(opportunity.get('ai_final_score', 'n/a'))}",
                f"- AI feasibility/urgency/confidence: {_display_score(opportunity.get('feasibility_score', 'n/a'))}/{_display_score(opportunity.get('urgency_score', 'n/a'))}/{_display_score(opportunity.get('confidence_score', 'n/a'))}",
                f"- AI commercial summary: {opportunity.get('commercial_summary', 'n/a')}",
                f"- AI recommended next step: {opportunity.get('recommended_next_step', 'n/a') if opportunity.get('ai_final_analysis') else 'n/a'}",
                "- Evidence URLs:",
            ]
        )
        if urls:
            lines.extend(f"  - {url}" for url in urls)
        else:
            lines.append("  - none")

        lines.append("- Evidence quotes:")
        if quotes:
            lines.extend(f"  - {quote}" for quote in quotes)
        else:
            lines.append("  - none")

        lines.extend(
            [
                f"- Risk notes: {risk_notes}",
                f"- Next validation step: {next_validation_step}",
                "",
            ]
        )
    lines.extend(["## Next Validation Actions", "", "- Validate top 3 product opportunities with at least 5 fresh external demand signals each.", "- Manually review quick service leads in their public source context; do not auto-contact, infer identity, or bypass platform/compliance rules.", ""])

    path.write_text("\n".join(lines), encoding="utf-8")
    return path



def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return sorted(_json_safe(v) for v in value)
    return value

def generate_json_summary(opportunities: list[Any], output_path: str | Path, telemetry: Mapping[str, Any] | None = None, source_statuses: Mapping[str, Any] | None = None, analyzer_mode: str = "rule_based", quality_summary: Mapping[str, Any] | None = None, final_filter_summary: Mapping[str, Any] | None = None, recall_diagnostics: Mapping[str, Any] | None = None, query_adjustment_proposals: list[dict[str, Any]] | None = None, ai_triage_summary: Mapping[str, Any] | None = None, delivery_status: Mapping[str, Any] | None = None, timing_diagnostics: Mapping[str, Any] | None = None, quick_service_leads: list[Any] | None = None, blocked_quick_service_items: list[dict[str, Any]] | None = None) -> Path:
    """Write a compact JSON summary of sorted opportunities for deterministic auditing."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    records = _sorted_records(opportunities)
    leads = _sorted_leads(quick_service_leads or [])
    blocked_leads = list(blocked_quick_service_items or [])
    counts = _priority_counts(records)
    product_records = [dict(record, track="product_opportunity", product_opportunity_score=record.get("opportunity_score", record.get("score", 0)), repeated_demand_score=record.get("market_intensity_score", 0), market_signal_score=record.get("weighted_score", record.get("opportunity_score", 0)), source_evidence_count=record.get("evidence_count", len(record.get("evidence_urls", []) or [])), supporting_sources=record.get("evidence_urls", []), risks=record.get("risk_notes", ""), suggested_validation_next_step=record.get("next_validation_step", "Validate with repeated source-primary demand evidence.")) for record in records]
    payload = {
        "generated_at": _generated_at(),
        "analyzer_mode": analyzer_mode,
        "source_statuses": dict(source_statuses or {}),
        "quality_gate_summary": dict(quality_summary or {}),
        "final_filter_summary": dict(final_filter_summary or {}),
        "source_telemetry": (telemetry or {}).get("source_telemetry", {}),
        "category_telemetry": (telemetry or {}).get("category_telemetry", {}),
        "recall_diagnostics": dict(recall_diagnostics or {}),
        "query_adjustment_proposals": list(query_adjustment_proposals or []),
        "source_recall_diagnostics": _source_recall_rows(telemetry),
        "ai_triage_summary": dict(ai_triage_summary or {}),
        "delivery_status": dict(delivery_status or {}),
        "timing_diagnostics": dict(timing_diagnostics or {}),
        "quick_service_leads": leads,
        "blocked_quick_service_items": blocked_leads,
        "quick_service_lead_summary": summarize_quick_service_leads(leads, blocked_leads),
        "product_opportunities": product_records,
        "product_opportunity_summary": {"total": len(records), "high_priority": counts["high"], "medium_priority": counts["medium"], "low_priority": counts["low"]},
        "requester_attribution_summary": summarize_requester_attribution(leads),
        "compliance_summary": summarize_compliance(leads, blocked_leads),
        "total_opportunities": len(records),
        "priority_counts": counts,
        "opportunities": [
            {
                "track": "product_opportunity",
                "title": opportunity.get("title", "Untitled opportunity"),
                "priority": opportunity.get("priority", "unknown"),
                "opportunity_score": opportunity.get("opportunity_score", opportunity.get("score", 0)),
                "customer_type": opportunity.get("customer_type", "n/a"),
                "evidence_urls": _evidence_urls(opportunity),
                "ai_final_analysis": opportunity.get("ai_final_analysis", {}),
                "ai_final_score": opportunity.get("ai_final_score"),
                "feasibility_score": opportunity.get("feasibility_score"),
                "urgency_score": opportunity.get("urgency_score"),
                "confidence_score": opportunity.get("confidence_score"),
            }
            for opportunity in records
        ],
    }
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
