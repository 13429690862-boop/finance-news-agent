import json

from agent.recall_optimizer import FORBIDDEN_BROAD_TERMS, build_recall_diagnostics
from agent.report import generate_json_summary, generate_markdown_report


def _telemetry():
    return {
        "source_telemetry": {
            "gdelt": {"source_type": "news", "query_count": 5, "collected_count": 10, "qualified_raw_count": 0, "final_qualified_count": 0},
            "stackexchange": {"source_type": "forum_post", "query_count": 4, "collected_count": 0, "qualified_raw_count": 0, "final_qualified_count": 0},
            "hn_algolia": {"source_type": "forum_post", "query_count": 6, "collected_count": 8, "qualified_raw_count": 3, "final_qualified_count": 0},
        },
        "category_telemetry": {
            "china_sourcing_agents": {"query_count": 4, "collected_count": 5, "qualified_raw_count": 2, "final_qualified_count": 0, "rejection_reason_counts": {"no_explicit_demand_intent": 2}},
            "software_api_workflows": {"query_count": 3, "collected_count": 0, "qualified_raw_count": 0, "final_qualified_count": 0, "rejection_reason_counts": {}},
        },
    }


def test_recall_rules_and_sorting():
    diag = build_recall_diagnostics(_telemetry())
    src = diag["source_recommendations"]
    cat = diag["category_recommendations"]
    assert any(r["problem_type"] == "source_all_rejected" and r["name"] == "gdelt" for r in src)
    assert any(r["problem_type"] == "source_zero_return" and r["name"] == "stackexchange" for r in src)
    assert any(r["problem_type"] == "high_qualified_low_final" and r["name"] == "hn_algolia" for r in src)
    assert any(r["problem_type"] == "category_too_broad" for r in cat)
    severities = [r["severity"] for r in cat]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}.get(s, 9))


def test_query_suggestions_demand_oriented_and_safe():
    diag = build_recall_diagnostics(_telemetry())
    all_queries = [q.lower() for row in diag["query_suggestions"] for q in row["suggested_queries"]]
    assert any("need" in q or "looking for" in q or "integration" in q for q in all_queries)
    assert not any(term in q for q in all_queries for term in FORBIDDEN_BROAD_TERMS)


def test_report_and_json_include_recall_diagnostics(tmp_path):
    diag = build_recall_diagnostics(_telemetry())
    md = tmp_path / "r.md"
    js = tmp_path / "s.json"
    generate_markdown_report([], md, telemetry=_telemetry(), recall_diagnostics=diag)
    content = md.read_text(encoding="utf-8")
    assert "## Recall Optimization Recommendations" in content
    assert "Source Telemetry" in content and "Category Telemetry" in content
    generate_json_summary([], js, telemetry=_telemetry(), recall_diagnostics=diag)
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert "recall_diagnostics" in payload
