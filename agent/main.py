"""Command line entry point for the bootstrap agent."""

import argparse
import json
from agent.timing import public_timing
from pathlib import Path
from typing import Any

from agent.collect import run_real_collection
from agent.config import flatten_queries, load_queries, queries_for_source
from agent.pipeline import run_daily_pipeline, run_fixture_pipeline
from agent.finance_pipeline import run_finance_daily_pipeline
from agent.report import generate_markdown_report
from agent.score import calculate_opportunity_score, classify_priority
from agent.sources.gdelt import GDELTCollector
from agent.sources.hn import HNAlgoliaCollector
from agent.sources.mock import MockCollector
from agent.sources.stackexchange import StackExchangeCollector
from agent.production_audit import run_production_audit
from agent.ai_triage import ai_provider_dry_run_check
from agent.delivery import delivery_check_send, delivery_dry_run_check, send_daily_report_to_test_recipient, write_daily_delivery_status
from agent.config import load_ai_triage_config, load_delivery_config
from agent.operator_audit import build_config_audit, build_env_inventory



def _print_json_or_config_error(builder: Any) -> dict[str, Any]:
    try:
        payload = builder()
    except ValueError as exc:
        payload = {"status": "invalid_config", "error": str(exc)}
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return payload


def _ai_config_for_profile(profile: str) -> dict[str, Any]:
    cfg = load_ai_triage_config("configs/ai_triage.yaml")
    if profile == "deepseek_coarse_dry_run":
        cfg = dict(cfg)
        cfg["enabled"] = True
        cfg["dry_run"] = False
        cfg["dry_run_provider_check"] = True
        cfg["provider_check_sample_limit"] = 1
        coarse = dict(cfg.get("coarse_stage", {}))
        coarse.update({"enabled": True, "provider": "deepseek", "sample_limit": 3, "dry_run": False})
        final = dict(cfg.get("final_stage", {}))
        final.update({"enabled": False, "provider": "none", "dry_run": True})
        cfg["coarse_stage"] = coarse
        cfg["final_stage"] = final
        cfg["allow_ai_to_bypass_final_filter"] = False
    return cfg

def _delivery_check_config_for_profile(profile: str) -> dict[str, Any]:
    cfg = load_delivery_config("configs/delivery.yaml")
    if profile in {"delivery_test_recipient", "full_test_dry_run"}:
        cfg = dict(cfg)
        cfg["dry_run_delivery_check"] = True
        cfg["test_recipient_mode"] = True
        cfg["allow_non_test_recipient"] = False
    return cfg

# existing helper functions unchanged

def _build_test_fixture_opportunities() -> list[dict[str, object]]:
    fixture_inputs = [
        {"title": "B2B China supplier verification checklist", "url": "https://example.com/china-supplier-verification", "market_intensity": 5, "china_relevance": 5, "monetization_clarity": 4, "implementation_difficulty": 2},
        {"title": "Mandarin localization QA for ecommerce listings", "url": "https://example.com/mandarin-localization-qa", "market_intensity": 4, "china_relevance": 5, "monetization_clarity": 3, "implementation_difficulty": 3},
        {"title": "China travel payment readiness guide", "url": "https://example.com/china-travel-payments", "market_intensity": 3, "china_relevance": 4, "monetization_clarity": 3, "implementation_difficulty": 3},
    ]
    opportunities = []
    for item in fixture_inputs:
        score = calculate_opportunity_score(item["market_intensity"], item["china_relevance"], item["monetization_clarity"], item["implementation_difficulty"])
        opportunities.append({"title": item["title"], "url": item["url"], "score": score, "priority": classify_priority(score)})
    return opportunities

def run_test_fixture() -> Path:
    return generate_markdown_report(_build_test_fixture_opportunities(), Path("reports/test-fixture-demand-report.md"))

def _model_to_dict(item: Any) -> dict[str, Any]:
    return item.model_dump() if hasattr(item, "model_dump") else item.__dict__.copy()

def run_collect_fixture() -> Path:
    queries = flatten_queries(load_queries())
    items = MockCollector().collect(queries=queries, max_items=100)
    output_path = Path("data/raw_items.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(json.dumps(_model_to_dict(i), ensure_ascii=False, sort_keys=True) for i in items)+"\n", encoding="utf-8")
    print(f"Query count: {len(queries)}\nItem count: {len(items)}\nOutput path: {output_path}")
    return output_path

def run_analyze_fixture(json_summary: bool = False) -> Path:
    raw_items_path = Path("data/raw_items.jsonl")
    report_path = Path("reports/fixture-opportunities-report.md")
    if not raw_items_path.exists():
        print("Missing data/raw_items.jsonl. Run collect-fixture first.")
        return report_path
    opportunities = run_fixture_pipeline(raw_items_path=raw_items_path, markdown_report_path=report_path, json_summary_path=Path("reports/fixture-opportunities-summary.json") if json_summary else None, scoring_config_path=Path("configs/scoring.yaml"))
    print(f"Raw item count: {sum(1 for l in raw_items_path.read_text(encoding='utf-8').splitlines() if l.strip())}")
    print(f"Opportunity count: {len(opportunities)}\nReport path: {report_path}")
    return report_path

def run_collect_hn() -> Path:
    query_config = load_queries()
    items = HNAlgoliaCollector().collect(queries=queries_for_source(query_config, "hn_algolia"), max_items=20)
    p = Path("data/raw_items.jsonl"); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(_model_to_dict(i), ensure_ascii=False, sort_keys=True) for i in items)+("\n" if items else ""), encoding="utf-8")
    print(f"Source: hn_algolia\nRaw item count: {len(items)}\nOutput path: {p}")
    return p

def run_collect_gdelt() -> Path:
    query_config = load_queries()
    items = GDELTCollector().collect(queries=queries_for_source(query_config, "gdelt"), max_items=20)
    p = Path("data/raw_items.jsonl"); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(_model_to_dict(i), ensure_ascii=False, sort_keys=True) for i in items)+("\n" if items else ""), encoding="utf-8")
    print(f"Source: gdelt\nRaw item count: {len(items)}\nOutput path: {p}")
    return p

def run_collect_stackexchange() -> Path:
    query_config = load_queries()
    items = StackExchangeCollector().collect(queries=queries_for_source(query_config, "stackexchange"), max_items=20)
    p = Path("data/raw_items.jsonl"); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(_model_to_dict(i), ensure_ascii=False, sort_keys=True) for i in items)+("\n" if items else ""), encoding="utf-8")
    print(f"Source: stackexchange\nRaw item count: {len(items)}\nOutput path: {p}")
    return p

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["test-fixture","collect-fixture","analyze-fixture","collect-hn","collect-gdelt","collect-stackexchange","collect-real","daily","recall-diagnostics","optimize-queries","production-audit","secrets-audit","ai-provider-check","delivery-check","config-audit","env-inventory","finance-daily"], required=True)
    parser.add_argument("--json-summary", action="store_true")
    parser.add_argument("--send-report-to-test-recipient", action="store_true")
    parser.add_argument("--profile", default="no_secret_default", choices=["no_secret_default","ai_provider_dry_run","deepseek_coarse_dry_run","delivery_test_recipient","full_test_dry_run"])
    parser.add_argument("--provider", default="all", choices=["all", "deepseek", "openai", "openai_responses"])
    parser.add_argument("--portfolio", default="configs/portfolio.yaml")
    parser.add_argument("--finance-config", default="configs/finance.yaml")
    args = parser.parse_args()
    if args.mode == "test-fixture": print(f"Generated report: {run_test_fixture()}")
    elif args.mode == "collect-fixture": run_collect_fixture()
    elif args.mode == "analyze-fixture": run_analyze_fixture(json_summary=args.json_summary)
    elif args.mode == "collect-hn": run_collect_hn()
    elif args.mode == "collect-gdelt": run_collect_gdelt()
    elif args.mode == "collect-stackexchange": run_collect_stackexchange()
    elif args.mode == "collect-real":
        summary = run_real_collection()
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    elif args.mode == "daily":
        report_path = Path("reports/daily-demand-report.md") if args.send_report_to_test_recipient else None
        json_path = Path("reports") / "daily-demand-summary.json" if (args.json_summary or args.send_report_to_test_recipient) else None
        summary = run_daily_pipeline(markdown_report_path=report_path, json_summary_path=json_path, delivery_expected_after_report_generation=args.send_report_to_test_recipient)
        if args.send_report_to_test_recipient:
            counts = {"raw": int(summary.get("raw_items_collected", 0)), "qualified": int(summary.get("qualified_raw_items", 0)), "quick_service_leads": int(summary.get("quick_service_leads_generated", 0)), "product_opportunities": int(summary.get("product_opportunities_generated", summary.get("opportunities_generated", 0))), "final": int(summary.get("opportunities_generated", 0))}
            cfg = load_delivery_config("configs/delivery.yaml")
            summary["delivery_status"] = send_daily_report_to_test_recipient(Path(summary["report_path"]), json_path, counts, cfg)
            timing = dict(summary.get("timing_diagnostics", {}))
            timing["delivery_send_started_at"] = summary["delivery_status"].get("send_started_at")
            timing["delivery_send_finished_at"] = summary["delivery_status"].get("send_finished_at")
            timing["delivery_send_duration_seconds"] = summary["delivery_status"].get("send_duration_seconds")
            timing["smtp_duration_seconds"] = summary["delivery_status"].get("smtp_duration_seconds")
            timing.setdefault("stage_statuses", {})["delivery_send"] = "sent" if summary["delivery_status"].get("status") == "sent" else str(summary["delivery_status"].get("status", "failed"))
            summary["timing_diagnostics"] = public_timing(timing)
            write_daily_delivery_status(Path("reports/daily-delivery-status.json"), summary["delivery_status"])
            if json_path and json_path.exists():
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                payload["delivery_status"] = summary["delivery_status"]
                payload["timing_diagnostics"] = summary["timing_diagnostics"]
                json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    elif args.mode == "recall-diagnostics":
        summary = run_daily_pipeline(json_summary_path=Path("reports") / "daily-demand-summary.json")
        print(json.dumps(summary.get("telemetry", {}), indent=2, ensure_ascii=False, sort_keys=True))

    elif args.mode == "optimize-queries":
        summary = run_daily_pipeline()
        proposals = summary.get("query_adjustment_proposals", [])
        print(f"Query/profile adjustment proposals: {len(proposals)}")
        for row in proposals[:10]:
            print(f"- [{row.get('risk_level','n/a')}] {row.get('scope','n/a')}::{row.get('name','n/a')} -> {row.get('proposed_action','n/a')}")
    elif args.mode == "production-audit":
        summary = run_production_audit(profile=args.profile)
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
        if not summary.get("ok", False):
            raise SystemExit(1)
    elif args.mode == "secrets-audit":
        summary = run_production_audit(profile=args.profile)
        keys = ["profile","secrets_required","ai_secrets_ready","delivery_secrets_ready","missing_ai_secrets","missing_delivery_secrets","no_secret_safe","deepseek_secrets_required","deepseek_secrets_ready","openai_final_secrets_required","openai_final_secrets_ready","coarse_stage_enabled","final_stage_enabled","deepseek_coarse_supported","deepseek_coarse_enabled","deepseek_coarse_ready","openai_final_supported","openai_final_enabled","openai_final_ready","true_codex_sdk_supported","true_codex_sdk_enabled","true_codex_sdk_note"]
        print(json.dumps({k: summary[k] for k in keys}, indent=2, ensure_ascii=False, sort_keys=True))
    elif args.mode == "ai-provider-check":
        _print_json_or_config_error(lambda: ai_provider_dry_run_check(_ai_config_for_profile(args.profile), provider=args.provider))
    elif args.mode == "delivery-check":
        cfg = _delivery_check_config_for_profile(args.profile)
        if args.profile == "delivery_test_recipient":
            report_path = Path("reports/daily-demand-report.md")
            summary_path = Path("reports/daily-demand-summary.json")
            print(json.dumps(delivery_check_send(cfg, report_path, summary_path), indent=2, ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps(delivery_dry_run_check(cfg), indent=2, ensure_ascii=False, sort_keys=True))
    elif args.mode == "finance-daily":
        json_path = Path("reports") / "daily-finance-summary.json" if args.json_summary else None
        summary = run_finance_daily_pipeline(
            portfolio_path=args.portfolio,
            finance_config_path=args.finance_config,
            markdown_report_path=Path("reports/daily-finance-report.md"),
            json_summary_path=json_path,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    elif args.mode == "config-audit":
        _print_json_or_config_error(build_config_audit)
    elif args.mode == "env-inventory":
        _print_json_or_config_error(build_env_inventory)

if __name__ == "__main__":
    main()
