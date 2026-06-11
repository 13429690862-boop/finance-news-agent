import json

from agent.pipeline import run_fixture_pipeline


def _record(title, content, url="https://example.com/item"):
    return {
        "source": "mock_forum",
        "source_type": "forum_post",
        "url": url,
        "title": title,
        "content": content,
        "author": "fixture_user",
        "published_at": "2026-01-01T00:00:00Z",
        "fetched_at": "2026-05-18T00:00:00Z",
        "query": "China supplier quality control",
        "language": "en",
        "raw_metadata": {"fixture": True},
    }


def test_analyze_fixture_pipeline_generates_report(tmp_path):
    raw_items_path = tmp_path / "raw_items.jsonl"
    report_path = tmp_path / "fixture-opportunities-report.md"
    records = [
        _record("Need China supplier QC", "Looking for help with supplier quality control."),
        _record("Generic China market facts", "A neutral article without a request.", "https://example.com/generic"),
    ]
    raw_items_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    opportunities = run_fixture_pipeline(raw_items_path=raw_items_path, markdown_report_path=report_path)

    assert len(opportunities) == 1
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "## Executive Summary" in content
    assert "Total opportunities: 1" in content
    assert "Risk notes:" in content
    assert "Next validation step:" in content


def test_analyze_fixture_pipeline_can_write_json_summary(tmp_path):
    raw_items_path = tmp_path / "raw_items.jsonl"
    report_path = tmp_path / "fixture-opportunities-report.md"
    json_summary_path = tmp_path / "fixture-opportunities-summary.json"
    record = _record("Need China supplier QC", "Looking for help with supplier quality control.")
    raw_items_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    opportunities = run_fixture_pipeline(
        raw_items_path=raw_items_path,
        markdown_report_path=report_path,
        json_summary_path=json_summary_path,
        scoring_config_path="configs/scoring.yaml",
    )

    assert len(opportunities) == 1
    assert report_path.exists()
    assert json_summary_path.exists()
    payload = json.loads(json_summary_path.read_text(encoding="utf-8"))
    assert payload["total_opportunities"] == 1
    assert payload["opportunities"][0]["title"].startswith("Rule-based demand")


def test_fixture_pipeline_loads_quality_gate_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "quality_gate.yaml").write_text(
        "minimum_positive_groups: 3\n"
        "demand_intent_keywords:\n  - need\n"
        "actor_keywords:\n  - buyer\n"
        "workflow_keywords:\n  - logistics\n"
        "negative_topic_keywords:\n  - politics\n",
        encoding="utf-8",
    )

    raw_items_path = tmp_path / "raw_items.jsonl"
    report_path = tmp_path / "fixture-opportunities-report.md"
    record = _record("Need supplier", "Need supplier help")
    raw_items_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    opportunities = run_fixture_pipeline(raw_items_path=raw_items_path, markdown_report_path=report_path)
    assert len(opportunities) == 0
    assert "No qualified opportunities found today." in report_path.read_text(encoding="utf-8")


def test_pipeline_final_filter_removes_false_positive(tmp_path):
    raw_items_path = tmp_path / "raw_items.jsonl"
    report_path = tmp_path / "fixture-opportunities-report.md"
    records = [_record("Ask HN: Why is HN predominated by pro-ChineseCommunistParty people?", "Need help understanding this debate.")]
    raw_items_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    run_fixture_pipeline(raw_items_path=raw_items_path, markdown_report_path=report_path)
    content = report_path.read_text(encoding="utf-8")
    assert "No qualified opportunities found today." in content
    assert "## Final Opportunity Filter Summary" in content
