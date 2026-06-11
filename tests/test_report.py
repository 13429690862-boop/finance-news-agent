import json

from agent.report import generate_json_summary, generate_markdown_report


def test_generate_markdown_report_writes_polished_content(tmp_path):
    output_path = tmp_path / "report.md"
    opportunities = [
        {
            "title": "China supplier verification",
            "priority": "high",
            "opportunity_score": 50,
            "customer_type": "SMB buyers sourcing from China",
            "pain_point": "Supplier trust is unclear.",
            "possible_solution": "Verification checklist.",
            "monetization_model": "Service fee.",
            "evidence_urls": ["https://example.com/opportunity"],
            "evidence_quotes": ["Need a China supplier verification checklist."],
            "risk_notes": "Offline fixture only.",
            "next_validation_step": "Interview buyers.",
            "market_intensity_score": 5,
            "china_relevance_score": 5,
            "monetization_clarity_score": 4,
            "implementation_difficulty_score": 2,
        }
    ]

    generated_path = generate_markdown_report(opportunities, output_path)

    assert generated_path == output_path
    content = output_path.read_text(encoding="utf-8")
    assert "# China Demand Opportunities Report" in content
    assert "Generated at:" in content
    assert "## Executive Summary" in content
    assert "Total opportunities: 1" in content
    assert "High priority: 1" in content
    assert "Medium priority: 0" in content
    assert "Low priority: 0" in content
    assert "## Top Opportunities" in content
    assert "### 1. China supplier verification" in content
    assert "- Priority: high" in content
    assert "- Opportunity score: 50" in content
    assert "- Score breakdown:" in content
    assert "- Customer type: SMB buyers sourcing from China" in content
    assert "- Pain point: Supplier trust is unclear." in content
    assert "- Possible solution: Verification checklist." in content
    assert "- Monetization model: Service fee." in content
    assert "- Evidence URLs:" in content
    assert "  - https://example.com/opportunity" in content
    assert "- Evidence quotes:" in content
    assert "  - Need a China supplier verification checklist." in content
    assert "- Risk notes: Offline fixture only." in content
    assert "- Next validation step: Interview buyers." in content


def test_generate_markdown_report_sorts_by_opportunity_score(tmp_path):
    output_path = tmp_path / "sorted-report.md"
    opportunities = [
        {"title": "Low score", "priority": "low", "opportunity_score": 5, "evidence_urls": ["https://example.com/low"]},
        {"title": "High score", "priority": "high", "opportunity_score": 30, "evidence_urls": ["https://example.com/high"]},
    ]

    generate_markdown_report(opportunities, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert content.index("### 1. High score") < content.index("### 2. Low score")
    assert "High priority: 1" in content
    assert "Medium priority: 0" in content
    assert "Low priority: 1" in content


def test_generate_json_summary_writes_sorted_summary(tmp_path):
    output_path = tmp_path / "summary.json"
    opportunities = [
        {"title": "Low score", "priority": "low", "opportunity_score": 5, "evidence_urls": ["https://example.com/low"]},
        {"title": "High score", "priority": "high", "opportunity_score": 30, "evidence_urls": ["https://example.com/high"]},
    ]

    generate_json_summary(opportunities, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert '"total_opportunities": 2' in content
    assert content.index('"title": "High score"') < content.index('"title": "Low score"')


def test_recall_notes_with_final_opportunities_use_validation_note(tmp_path):
    output_path = tmp_path / "report.md"
    opportunities = [{"title": "Need QC inspection before shipping from China", "priority": "high", "opportunity_score": 10}]
    generate_markdown_report(
        opportunities,
        output_path,
        source_statuses={"hn": {"status": "ok", "count": 1}},
        quality_summary={"total_raw_items": 4},
    )
    content = output_path.read_text(encoding="utf-8")
    assert "final candidate opportunities" in content
    assert "Zero final opportunities is acceptable" not in content


def test_recall_notes_with_zero_final_opportunities_keep_zero_final_note(tmp_path):
    output_path = tmp_path / "report.md"
    generate_markdown_report(
        [],
        output_path,
        source_statuses={"hn": {"status": "ok", "count": 2}},
        quality_summary={"total_raw_items": 2},
    )
    content = output_path.read_text(encoding="utf-8")
    assert "Zero final opportunities is acceptable when no explicit China workflow demand is present." in content


def test_recall_notes_with_no_raw_items_keep_no_raw_note(tmp_path):
    output_path = tmp_path / "report.md"
    generate_markdown_report(
        [],
        output_path,
        source_statuses={"hn": {"status": "ok", "count": 0}},
        quality_summary={"total_raw_items": 0},
    )
    content = output_path.read_text(encoding="utf-8")
    assert "No raw items were collected in this run; verify collector availability and query coverage." in content


def test_zero_final_opportunities_report_keeps_telemetry_and_recall_sections(tmp_path):
    output_path = tmp_path / "report.md"
    generate_markdown_report(
        [],
        output_path,
        source_statuses={"hn": {"status": "ok", "count": 2}},
        quality_summary={"total_raw_items": 2},
        telemetry={
            "source_telemetry": {"hn": {"status": "ok", "query_count": 1, "collected_count": 2}},
            "category_telemetry": {"china_sourcing_agents": {"category": "china_sourcing_agents", "sources": ["hn"], "query_count": 1, "collected_count": 2}},
        },
        recall_diagnostics={
            "source_recommendations": [{"scope": "source", "name": "hn", "problem_type": "low_recall", "severity": "low", "recommended_action": "expand", "rationale": "diagnostic"}],
            "category_recommendations": [],
        },
    )
    content = output_path.read_text(encoding="utf-8")
    assert "No qualified opportunities found today." in content
    assert "## Source Telemetry" in content
    assert "## Category Telemetry" in content
    assert "## Recall Optimization Recommendations" in content
    assert "## Recall Notes" in content
    assert "## Opportunity Details" in content


def test_source_recall_diagnostics_section_and_json(tmp_path):
    md = tmp_path / "report.md"
    js = tmp_path / "summary.json"
    telemetry = {"source_telemetry": {"stackexchange": {"status": "ok", "query_count": 19, "site_count": 6, "collected_count": 0, "qualified_raw_count": 0, "final_qualified_count": 0}, "gdelt": {"status": "ok", "query_count": 8, "collected_count": 3, "qualified_raw_count": 0, "final_qualified_count": 0, "source_type": "news"}}}
    generate_markdown_report([], md, telemetry=telemetry)
    text = md.read_text(encoding="utf-8")
    assert "## Source Recall Diagnostics" in text
    assert "stackexchange" in text
    generate_json_summary([], js, telemetry=telemetry)
    payload = __import__("json").loads(js.read_text(encoding="utf-8"))
    assert "source_recall_diagnostics" in payload
    assert any(row["source"] == "stackexchange" for row in payload["source_recall_diagnostics"])


def test_stackexchange_collected_but_zero_qualified_not_healthy(tmp_path):
    md = tmp_path / "report.md"
    telemetry = {"source_telemetry": {"stackexchange": {"status": "ok", "query_count": 19, "site_count": 6, "collected_count": 18, "qualified_raw_count": 0, "final_qualified_count": 0, "rejection_reason_counts": {"no_explicit_demand_intent": 7}}}}
    generate_markdown_report([], md, telemetry=telemetry)
    text = md.read_text(encoding="utf-8")
    assert "query precision low" in text
    assert "healthy" not in text


def test_json_summary_includes_timing_diagnostics(tmp_path):
    output_path = tmp_path / "summary.json"
    timing = {
        "run_started_at": "2026-05-29T00:00:00+00:00",
        "run_finished_at": "2026-05-29T00:00:01+00:00",
        "total_runtime_seconds": 1.0,
        "stage_statuses": {"deepseek_coarse": "disabled"},
    }
    generate_json_summary([], output_path, timing_diagnostics=timing)

    content = output_path.read_text(encoding="utf-8")
    assert '"timing_diagnostics"' in content
    assert '"total_runtime_seconds": 1.0' in content
    assert '"deepseek_coarse": "disabled"' in content


def test_markdown_report_includes_timing_diagnostics_section(tmp_path):
    output_path = tmp_path / "report.md"
    generate_markdown_report(
        [],
        output_path,
        timing_diagnostics={
            "collect_started_at": "2026-05-29T00:00:00+00:00",
            "collect_finished_at": "2026-05-29T00:00:01+00:00",
            "collect_duration_seconds": 1.0,
            "ai_coarse_duration_seconds": None,
            "stage_statuses": {"collect": "ok", "deepseek_coarse": "disabled", "delivery_send": "not_attempted"},
        },
    )

    content = output_path.read_text(encoding="utf-8")
    assert "## Timing Diagnostics" in content
    assert "| collect | 2026-05-29T00:00:00+00:00 | 2026-05-29T00:00:01+00:00 | 1 | ok |" in content
    assert "| deepseek_coarse |" in content
    assert "| delivery_send |" in content
    assert "reports/daily-delivery-status.json" in content


def test_production_report_copy_does_not_claim_offline_fixture_mode_by_default(tmp_path):
    output_path = tmp_path / "report.md"
    generate_markdown_report(
        [],
        output_path,
        source_statuses={"hn_algolia": {"status": "ok", "count": 1}},
        quality_summary={"total_raw_items": 1},
    )
    content = output_path.read_text(encoding="utf-8")
    assert "This report ranks deterministic demand opportunities generated from collected source items." in content
    assert "This offline report" not in content
    assert "fixture raw items" not in content


def test_markdown_delivery_status_pending_send_is_not_misleading_not_attempted_json(tmp_path):
    output_path = tmp_path / "report.md"
    generate_markdown_report(
        [],
        output_path,
        delivery_status={
            "enabled": True,
            "status": "pending_send",
            "channel": "email",
            "recipient_mode": "test",
            "delivery_expected_after_report_generation": True,
        },
    )

    content = output_path.read_text(encoding="utf-8")
    assert "## Delivery Status" in content
    assert "- Status at report generation: pending_send" in content
    assert "- Channel: email" in content
    assert "- Recipient mode: test" in content
    assert "- Final delivery status: see daily-demand-summary.json / daily-delivery-status.json" in content
    assert '{"enabled": false, "status": "not_attempted"}' not in content


def test_markdown_delivery_status_disabled_is_clear_without_raw_json(tmp_path):
    output_path = tmp_path / "report.md"
    generate_markdown_report([], output_path, delivery_status={"enabled": False, "status": "not_attempted"})

    content = output_path.read_text(encoding="utf-8")
    assert "- Status: not_attempted" in content
    assert "- Reason: delivery disabled" in content
    assert '{"enabled": false, "status": "not_attempted"}' not in content


def test_markdown_delivery_status_final_sent_is_rendered_when_available(tmp_path):
    output_path = tmp_path / "report.md"
    generate_markdown_report(
        [],
        output_path,
        delivery_status={"enabled": True, "status": "sent", "channel": "email", "sent_to_test_recipient": True},
    )

    content = output_path.read_text(encoding="utf-8")
    assert "- Status: sent" in content
    assert "- Channel: email" in content
    assert "- Recipient mode: test" in content
    assert "- Sent to test recipient: True" in content
    assert "JSON remains authoritative for final delivery status." in content


def test_json_summary_delivery_status_remains_authoritative_final_status(tmp_path):
    output_path = tmp_path / "summary.json"
    generate_json_summary([], output_path, delivery_status={"status": "sent", "channel": "email", "sent_to_test_recipient": True})

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["delivery_status"]["status"] == "sent"
    assert payload["delivery_status"]["channel"] == "email"
    assert payload["delivery_status"]["sent_to_test_recipient"] is True
