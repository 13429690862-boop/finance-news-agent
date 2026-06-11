"""Offline fixture analysis pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.analyze import build_analyzer
from agent.cluster import cluster_opportunities, load_history, mark_history, update_history_index
from agent.config import load_quality_gate_config, load_query_optimizer_config, load_scoring_config, load_ai_triage_config, load_delivery_config
from agent.models import DemandOpportunity, RawItem
from agent.demand_classifier import classify_quick_service_leads
from agent.quality_gate import evaluate_raw_item_quality, summarize_quality_results
from agent.report import generate_json_summary, generate_markdown_report
from agent.telemetry import ensure_category, ensure_source, summarize_quality_gate_by_source, summarize_quality_gate_by_category
from agent.opportunity_filter import evaluate_opportunity_sanity
from agent.recall_optimizer import build_recall_diagnostics
from agent.query_optimizer import generate_query_adjustment_proposals
from agent.delivery import deliver_report
from agent.timing import create_pipeline_timing, finish_run, finish_stage, public_timing, skip_stage, start_stage
from agent.ai_triage import apply_openai_final_scoring, apply_deepseek_coarse_triage, ai_provider_dry_run_check, build_ai_triage_summary
import yaml


def _enrich_opportunities(opportunities: list[DemandOpportunity], scoring_config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = scoring_config or {}
    confidence = cfg.get("source_confidence", {}) if isinstance(cfg, dict) else {}
    default_conf = float(confidence.get("default", 0.6))
    enriched: list[dict[str, Any]] = []
    for opportunity in opportunities:
        record = opportunity.model_dump()
        source = str(record.get("source", "") or "").lower()
        source_conf = float(confidence.get(source, confidence.get("fixture", default_conf) if source == "" else default_conf))
        record["source_confidence"] = source_conf
        record["weighted_score"] = float(record.get("opportunity_score", 0)) * source_conf
        flags: list[str] = []
        if len(record.get("evidence_quotes", [])) == 0:
            flags.append("weak_evidence")
        if int(record.get("china_relevance_score", 1)) <= 2:
            flags.append("low_china_relevance")
        if int(record.get("implementation_difficulty_score", 1)) >= 4:
            flags.append("high_implementation_risk")
        if len(record.get("evidence_urls", [])) <= 1:
            flags.append("single_source_only")
        if "news" in str(record.get("summary", "")).lower() or str(record.get("source_type", "")).lower()=="news":
            flags.append("possible_news_only")
        strong_signal = {"explicit_demand_in_primary_post", "explicit_customer_or_operator_actor", "explicit_workflow_or_deliverable"}.issubset(set(record.get("final_filter_positive_reasons", [])))
        if (("possible_news_only" in flags and "single_source_only" in flags) or not strong_signal) and record.get("priority")=="high":
            record["priority"] = "medium"
        record["quality_flags"] = flags
        enriched.append(record)
    return enriched


def _apply_final_sanity_filter(opportunities: list[DemandOpportunity], raw_items: list[RawItem]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_by_url = {item.url: item for item in raw_items}
    qualified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for opportunity in opportunities:
        raw = raw_by_url.get(opportunity.raw_url)
        sanity = evaluate_opportunity_sanity(opportunity, raw)
        record = opportunity.model_dump()
        record["final_filter_positive_reasons"] = sanity.positive_reasons
        if sanity.is_valid:
            qualified.append(record)
        else:
            record["final_filter_rejection_reasons"] = sanity.rejection_reasons
            rejected.append(record)
    return qualified, rejected

def _load_raw_items_jsonl(path: Path) -> list[RawItem]:
    items: list[RawItem] = []
    if not path.exists():
        raise FileNotFoundError(path)

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc
        items.append(RawItem(**record))
    return items


def run_fixture_pipeline(
    raw_items_path: str | Path = "data/raw_items.jsonl",
    markdown_report_path: str | Path = "reports/fixture-opportunities-report.md",
    json_summary_path: str | Path | None = None,
    scoring_config_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> list[DemandOpportunity]:
    """Read raw fixture JSONL, analyze it, write reports, and return opportunities."""
    raw_path = Path(raw_items_path)
    markdown_path = Path(report_path if report_path is not None else markdown_report_path)
    scoring_config = load_scoring_config(scoring_config_path) if scoring_config_path is not None else None

    items = _load_raw_items_jsonl(raw_path)
    quality_config = load_quality_gate_config("configs/quality_gate.yaml")
    quality_results = [(item, evaluate_raw_item_quality(item, quality_config)) for item in items]
    qualified_items = [item for item, result in quality_results if result.is_qualified]
    quality_summary = summarize_quality_results(quality_results)
    ai_triage_config = load_ai_triage_config("configs/ai_triage.yaml")
    triaged_items, coarse_status = apply_deepseek_coarse_triage(qualified_items, ai_triage_config)
    quick_service_leads, blocked_quick_service_items = classify_quick_service_leads(triaged_items)
    analyzer = build_analyzer(scoring_config=scoring_config, ai_triage_config={})
    opportunities = analyzer.analyze_items(triaged_items)
    qualified_opps, rejected_opps = _apply_final_sanity_filter(opportunities, triaged_items)
    enriched = _enrich_opportunities([DemandOpportunity(**o) for o in qualified_opps], scoring_config)
    enriched, final_status = apply_openai_final_scoring(enriched, ai_triage_config)
    triage_payload = build_ai_triage_summary(ai_triage_config, coarse_status, final_status)
    clustered = cluster_opportunities(enriched)
    final_filter_summary = {"analyzed_before_final_filter": len(opportunities), "final_qualified_opportunities": len(qualified_opps), "final_rejected_opportunities": len(rejected_opps), "final_rejection_reasons": {}}
    for r in rejected_opps:
        for reason in r.get("final_filter_rejection_reasons", []):
            final_filter_summary["final_rejection_reasons"][reason] = final_filter_summary["final_rejection_reasons"].get(reason, 0) + 1
    generate_markdown_report(clustered, markdown_path, source_statuses={"fixture": {"status": "ok", "count": len(items)}}, quality_summary={"total_raw_items": len(items), "qualified_raw_items": len(qualified_items), "rejected_raw_items": len(items)-len(qualified_items), **quality_summary}, final_filter_summary=final_filter_summary, ai_triage_summary=triage_payload, quick_service_leads=quick_service_leads, blocked_quick_service_items=blocked_quick_service_items)

    if json_summary_path is not None:
        generate_json_summary(clustered, json_summary_path, ai_triage_summary=triage_payload, quick_service_leads=quick_service_leads, blocked_quick_service_items=blocked_quick_service_items)

    return opportunities


from datetime import UTC, datetime
from agent.collect import run_real_collection


def run_daily_pipeline(
    queries_path: str | Path = "configs/queries.yaml",
    sources_path: str | Path = "configs/sources.yaml",
    raw_items_path: str | Path = "data/raw_items.jsonl",
    markdown_report_path: str | Path | None = None,
    json_summary_path: str | Path | None = None,
    delivery_expected_after_report_generation: bool = False,
) -> dict[str, Any]:
    timing = create_pipeline_timing()
    try:
        start_stage(timing, "collect")
        summary = run_real_collection(queries_path=queries_path, sources_path=sources_path, output_path=raw_items_path)
        items = _load_raw_items_jsonl(Path(raw_items_path)) if Path(raw_items_path).exists() else []
        finish_stage(timing, "collect")

        start_stage(timing, "quality_gate")
        quality_config = load_quality_gate_config("configs/quality_gate.yaml")
        quality_results = [(item, evaluate_raw_item_quality(item, quality_config)) for item in items]
        qualified_items = [item for item, result in quality_results if result.is_qualified]
        quality_summary = summarize_quality_results(quality_results)
        finish_stage(timing, "quality_gate")

        try:
            scoring_config = load_scoring_config("configs/scoring.yaml")
        except FileNotFoundError:
            scoring_config = None
        ai_triage_config = load_ai_triage_config("configs/ai_triage.yaml")

        start_stage(timing, "deepseek_coarse")
        triaged_items, coarse_status = apply_deepseek_coarse_triage(qualified_items, ai_triage_config)
        finish_stage(timing, "deepseek_coarse", str(coarse_status.get("status", "ok") or "ok"))

        start_stage(timing, "quick_service_classifier")
        quick_service_leads, blocked_quick_service_items = classify_quick_service_leads(triaged_items)
        finish_stage(timing, "quick_service_classifier")

        start_stage(timing, "analyzer")
        analyzer = build_analyzer(scoring_config=scoring_config, ai_triage_config={})
        opportunities = analyzer.analyze_items(triaged_items)
        finish_stage(timing, "analyzer")

        start_stage(timing, "final_filter")
        qualified_opps, rejected_opps = _apply_final_sanity_filter(opportunities, triaged_items)
        enriched = _enrich_opportunities([DemandOpportunity(**o) for o in qualified_opps], scoring_config)
        enriched, final_status = apply_openai_final_scoring(enriched, ai_triage_config)
        clustered = cluster_opportunities(enriched)
        history_path = Path("data/opportunity_index.jsonl")
        history = load_history(history_path)
        mark_history(clustered, history)
        update_history_index(clustered, history_path)
        finish_stage(timing, "final_filter")

        triage_payload = build_ai_triage_summary(ai_triage_config, coarse_status, final_status)
        date_label = datetime.now(UTC).date().isoformat()
        report_path = Path(markdown_report_path or f"reports/{date_label}-demand-report.md")
        analyzer_mode = getattr(analyzer, "analyzer_mode", "rule_based")
        final_filter_summary = {"analyzed_before_final_filter": len(opportunities), "final_qualified_opportunities": len(qualified_opps), "final_rejected_opportunities": len(rejected_opps), "final_rejection_reasons": {}}
        for r in rejected_opps:
            for reason in r.get("final_filter_rejection_reasons", []):
                final_filter_summary["final_rejection_reasons"][reason] = final_filter_summary["final_rejection_reasons"].get(reason, 0) + 1
        telemetry = summary.get("telemetry", {"source_telemetry": {}, "category_telemetry": {}})
        q_by_source=summarize_quality_gate_by_source(quality_results); q_by_category=summarize_quality_gate_by_category(quality_results)
        for src,b in q_by_source.items():
            ensure_source(telemetry, src).update(b)
        for cat,b in q_by_category.items():
            ensure_category(telemetry, cat).update(b)
        raw_by_url={i.url:i for i in triaged_items}
        for o in opportunities:
            raw=raw_by_url.get(o.raw_url)
            if raw is None: continue
            src=raw.source; cat=raw.query_category or "uncategorized"
            ensure_source(telemetry, src, raw.source_type)["analyzed_candidate_count"] += 1
            ensure_category(telemetry, cat)["analyzed_candidate_count"] += 1
        for o in qualified_opps:
            raw=raw_by_url.get(o.get("raw_url"));
            if raw is None: continue
            ensure_source(telemetry, raw.source, raw.source_type)["final_qualified_count"] += 1
            ensure_category(telemetry, raw.query_category or "uncategorized")["final_qualified_count"] += 1
        for o in rejected_opps:
            raw=raw_by_url.get(o.get("raw_url"));
            if raw is None: continue
            srcb=ensure_source(telemetry, raw.source, raw.source_type); catb=ensure_category(telemetry, raw.query_category or "uncategorized")
            srcb["final_rejected_count"] += 1; catb["final_rejected_count"] += 1
        recall_diagnostics = build_recall_diagnostics(telemetry)
        query_optimizer_config = load_query_optimizer_config("configs/query_optimizer.yaml")
        query_adjustment_proposals = generate_query_adjustment_proposals(recall_diagnostics, query_optimizer_config)
        delivery_config = load_delivery_config("configs/delivery.yaml")
        delivery_status = {"enabled": False, "status": "not_attempted"}
        if delivery_expected_after_report_generation:
            delivery_status = {
                "enabled": True,
                "status": "pending_send",
                "channel": "email",
                "recipient_mode": "test",
                "delivery_expected_after_report_generation": True,
            }
        triage_payload["provider_check"] = ai_provider_dry_run_check(ai_triage_config)

        start_stage(timing, "report_generation")
        generate_markdown_report(clustered, report_path, source_statuses=summary["sources"], analyzer_mode=analyzer_mode, quality_summary={"total_raw_items": len(items), "qualified_raw_items": len(qualified_items), "rejected_raw_items": len(items)-len(qualified_items), **quality_summary}, final_filter_summary=final_filter_summary, telemetry=telemetry, recall_diagnostics=recall_diagnostics, query_adjustment_proposals=query_adjustment_proposals, ai_triage_summary=triage_payload, delivery_status=delivery_status, timing_diagnostics=public_timing(timing), quick_service_leads=quick_service_leads, blocked_quick_service_items=blocked_quick_service_items)

        resolved_json = json_summary_path
        if resolved_json is not None:
            generate_json_summary(clustered, resolved_json, telemetry=telemetry, source_statuses=summary["sources"], analyzer_mode=analyzer_mode, quality_summary={"total_raw_items": len(items), "qualified_raw_items": len(qualified_items), "rejected_raw_items": len(items)-len(qualified_items), **quality_summary}, final_filter_summary=final_filter_summary, recall_diagnostics=recall_diagnostics, query_adjustment_proposals=query_adjustment_proposals, ai_triage_summary=triage_payload, delivery_status=delivery_status, timing_diagnostics=public_timing(timing), quick_service_leads=quick_service_leads, blocked_quick_service_items=blocked_quick_service_items)
        finish_stage(timing, "report_generation")
        generate_markdown_report(clustered, report_path, source_statuses=summary["sources"], analyzer_mode=analyzer_mode, quality_summary={"total_raw_items": len(items), "qualified_raw_items": len(qualified_items), "rejected_raw_items": len(items)-len(qualified_items), **quality_summary}, final_filter_summary=final_filter_summary, telemetry=telemetry, recall_diagnostics=recall_diagnostics, query_adjustment_proposals=query_adjustment_proposals, ai_triage_summary=triage_payload, delivery_status=delivery_status, timing_diagnostics=public_timing(timing), quick_service_leads=quick_service_leads, blocked_quick_service_items=blocked_quick_service_items)

        start_stage(timing, "delivery_send")
        delivery_status = deliver_report(report_path, Path(resolved_json) if resolved_json is not None else None, len(clustered), delivery_config, summary_counts={"raw": len(items), "qualified": len(qualified_items), "quick_service_leads": len(quick_service_leads), "product_opportunities": len(clustered), "final": len(clustered)})
        timing["smtp_duration_seconds"] = delivery_status.get("smtp_duration_seconds")
        finish_stage(timing, "delivery_send", "sent" if delivery_status.get("status") == "sent" else ("not_attempted" if delivery_status.get("status") == "disabled" else str(delivery_status.get("status", "skipped"))))

        priority_counts = {
            "high": sum(1 for o in clustered if o.get("priority") == "high"),
            "medium": sum(1 for o in clustered if o.get("priority") == "medium"),
            "low": sum(1 for o in clustered if o.get("priority") == "low"),
        }

        finish_run(timing)
        if resolved_json is not None:
            generate_json_summary(clustered, resolved_json, telemetry=telemetry, source_statuses=summary["sources"], analyzer_mode=analyzer_mode, quality_summary={"total_raw_items": len(items), "qualified_raw_items": len(qualified_items), "rejected_raw_items": len(items)-len(qualified_items), **quality_summary}, final_filter_summary=final_filter_summary, recall_diagnostics=recall_diagnostics, query_adjustment_proposals=query_adjustment_proposals, ai_triage_summary=triage_payload, delivery_status=delivery_status, timing_diagnostics=public_timing(timing), quick_service_leads=quick_service_leads, blocked_quick_service_items=blocked_quick_service_items)

        pipeline_summary = {
            "raw_items_collected": len(items),
            "qualified_raw_items": len(qualified_items),
            "ai_triaged_raw_items": len(triaged_items),
            "rejected_raw_items": len(items)-len(qualified_items),
            "quick_service_leads_generated": len(quick_service_leads),
            "blocked_quick_service_items": len(blocked_quick_service_items),
            "product_opportunities_generated": len(clustered),
            "opportunities_generated": len(clustered),
            "priority_counts": priority_counts,
            "report_path": str(report_path),
            "source_statuses": summary["sources"],
            "analyzer_mode": analyzer_mode,
            "telemetry": telemetry,
            "query_adjustment_proposals": query_adjustment_proposals,
            "delivery_status": delivery_status,
            "ai_triage_summary": triage_payload,
            "timing_diagnostics": public_timing(timing),
        }

        print(f"Raw items collected: {pipeline_summary['raw_items_collected']}")
        print(f"Quick service leads generated: {pipeline_summary['quick_service_leads_generated']}")
        print(f"Product opportunities generated: {pipeline_summary['product_opportunities_generated']}")
        print(f"Opportunities generated: {pipeline_summary['opportunities_generated']}")
        print(
            "Priority counts: "
            f"high={priority_counts['high']}, medium={priority_counts['medium']}, low={priority_counts['low']}"
        )
        print(f"Report path: {report_path}")
        print(f"Source statuses: {summary['sources']}")
        if resolved_json is not None:
            print(f"JSON summary path: {resolved_json}")

        return pipeline_summary
    except Exception:
        finish_run(timing)
        raise
