import json
from agent.config import load_queries, query_records_for_source
from agent.report import generate_markdown_report, generate_json_summary


def test_query_records_for_source_maps_categories():
    cfg = load_queries("configs/queries.yaml")
    recs = query_records_for_source(cfg, "stackexchange")
    assert recs
    assert all("category" in r for r in recs)


def test_report_contains_telemetry_sections(tmp_path):
    path = tmp_path / "r.md"
    telemetry = {
        "source_telemetry": {"hn_algolia": {"status": "ok", "query_count": 1, "collected_count": 2, "deduped_raw_count": 1, "quality_gate_input_count": 1, "qualified_raw_count": 1, "rejected_raw_count": 0, "analyzed_candidate_count": 1, "final_qualified_count": 0, "final_rejected_count": 1}},
        "category_telemetry": {"china_payment_api": {"category": "china_payment_api", "sources": ["hn_algolia"], "query_count": 1, "collected_count": 2, "qualified_raw_count": 1, "rejected_raw_count": 1, "final_qualified_count": 0, "final_rejected_count": 1, "rejection_reason_counts": {"x": 1}}},
    }
    generate_markdown_report([], path, telemetry=telemetry)
    content = path.read_text(encoding="utf-8")
    assert "## Source Telemetry" in content
    assert "## Category Telemetry" in content


def test_json_summary_includes_telemetry(tmp_path):
    p = tmp_path / "s.json"
    generate_json_summary([], p, telemetry={"source_telemetry": {}, "category_telemetry": {}}, source_statuses={"hn": {"status": "ok", "count": 0}})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "source_telemetry" in data
    assert "category_telemetry" in data
