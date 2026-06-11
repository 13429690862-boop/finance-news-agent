import json

from agent.pipeline import run_daily_pipeline


def test_daily_pipeline_generates_markdown_and_source_summary(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()

    def fake_collect(**kwargs):
        p = tmp_path / "data" / "raw_items.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "source": "mock",
            "source_type": "forum_post",
            "url": "https://x.com",
            "title": "Need China supplier",
            "content": "Looking for China supplier support",
            "author": "a",
            "published_at": "2026-01-01T00:00:00Z",
            "fetched_at": "2026-05-18T00:00:00Z",
            "query": "china supplier",
            "language": "en",
            "raw_metadata": {},
        }
        p.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return {"sources": {"hn_algolia": {"status": "ok", "count": 1}}}

    monkeypatch.setattr("agent.pipeline.run_real_collection", fake_collect)
    summary = run_daily_pipeline(raw_items_path=tmp_path / "data" / "raw_items.jsonl", markdown_report_path=tmp_path / "reports" / "r.md")
    assert summary["opportunities_generated"] == 1
    assert summary["qualified_raw_items"] == 1
    assert "hn_algolia" in summary["source_statuses"]
    assert (tmp_path / "reports" / "r.md").exists()
    assert summary["analyzer_mode"] == "rule_based"
    content = (tmp_path / "reports" / "r.md").read_text(encoding="utf-8")
    assert "Analyzer mode: rule_based" in content
    assert "## Quality Gate Summary" in content


def test_gdelt_news_rule_based_not_high_priority(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()

    def fake_collect(**kwargs):
        p = tmp_path / "data" / "raw_items.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "source": "gdelt",
            "source_type": "news",
            "url": "https://news.example.com/x",
            "title": "Need China supplier logistics help",
            "content": "Importer needs supplier logistics help",
            "author": "a",
            "published_at": "2026-01-01T00:00:00Z",
            "fetched_at": "2026-05-18T00:00:00Z",
            "query": "china supplier",
            "language": "en",
            "raw_metadata": {},
        }
        p.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return {"sources": {"gdelt": {"status": "ok", "count": 1}}}

    monkeypatch.setattr("agent.pipeline.run_real_collection", fake_collect)
    summary = run_daily_pipeline(raw_items_path=tmp_path / "data" / "raw_items.jsonl", markdown_report_path=tmp_path / "reports" / "r.md")
    content = (tmp_path / "reports" / "r.md").read_text(encoding="utf-8")
    assert summary["opportunities_generated"] == 1
    assert "| medium |" in content or "| low |" in content


def test_daily_pipeline_zero_final_opportunities_ok(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()

    def fake_collect(**kwargs):
        p = tmp_path / "data" / "raw_items.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "source": "hn_algolia",
            "source_type": "forum_post",
            "url": "https://x.com",
            "title": "Ask HN: Why is HN predominated by pro-ChineseCommunistParty people?",
            "content": "Need help understanding political comments",
            "author": "a",
            "published_at": "2026-01-01T00:00:00Z",
            "fetched_at": "2026-05-18T00:00:00Z",
            "query": "china",
            "language": "en",
            "raw_metadata": {},
        }
        p.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return {"sources": {"hn_algolia": {"status": "ok", "count": 1}}}

    monkeypatch.setattr("agent.pipeline.run_real_collection", fake_collect)
    summary = run_daily_pipeline(raw_items_path=tmp_path / "data" / "raw_items.jsonl", markdown_report_path=tmp_path / "reports" / "r.md")
    assert summary["opportunities_generated"] == 0
    content = (tmp_path / "reports" / "r.md").read_text(encoding="utf-8")
    assert "No qualified opportunities found today." in content
    assert "## Final Opportunity Filter Summary" in content


def test_deepseek_only_pipeline_receives_only_quality_gate_qualified_items(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()

    def fake_collect(**kwargs):
        p = tmp_path / "data" / "raw_items.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {
                "source": "hn_algolia", "source_type": "forum_post", "url": "https://x.com/qualified",
                "title": "Need China supplier", "content": "Looking for China supplier support and quality control",
                "author": "a", "published_at": "2026-01-01T00:00:00Z", "fetched_at": "2026-05-18T00:00:00Z",
                "query": "china supplier", "language": "en", "raw_metadata": {},
            },
            {
                "source": "hn_algolia", "source_type": "forum_post", "url": "https://x.com/rejected",
                "title": "China", "content": "metadata only",
                "author": "a", "published_at": "2026-01-01T00:00:00Z", "fetched_at": "2026-05-18T00:00:00Z",
                "query": "china supplier", "language": "en", "raw_metadata": {},
            },
        ]
        p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        return {"sources": {"hn_algolia": {"status": "ok", "count": 2}}}

    monkeypatch.setattr("agent.pipeline.run_real_collection", fake_collect)
    monkeypatch.setattr("agent.pipeline.load_ai_triage_config", lambda path: {"enabled": True, "dry_run": True, "allow_ai_to_bypass_final_filter": False, "coarse_stage": {"enabled": True, "provider": "mock", "model": "m", "sample_limit": 10}, "final_stage": {"enabled": False, "provider": "none"}})
    summary = run_daily_pipeline(raw_items_path=tmp_path / "data" / "raw_items.jsonl", markdown_report_path=tmp_path / "reports" / "r.md", json_summary_path=tmp_path / "reports" / "r.json")
    ai = summary["ai_triage_summary"]
    assert summary["qualified_raw_items"] == 1
    assert ai["deepseek_coarse_input_count"] == 1
    assert ai["openai_final_status"]["status"] == "disabled"
    payload = json.loads((tmp_path / "reports" / "r.json").read_text(encoding="utf-8"))
    assert payload["ai_triage_summary"]["deepseek_coarse_input_count"] == 1
    assert payload["ai_triage_summary"]["true_codex_sdk_supported"] is False


def test_openai_final_cannot_override_final_filter(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()

    def fake_collect(**kwargs):
        p = tmp_path / "data" / "raw_items.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "source": "hn_algolia", "source_type": "forum_post", "url": "https://x.com/political",
            "title": "Ask HN: Why is HN predominated by pro-ChineseCommunistParty people?",
            "content": "Need help understanding political comments",
            "author": "a", "published_at": "2026-01-01T00:00:00Z", "fetched_at": "2026-05-18T00:00:00Z",
            "query": "china", "language": "en", "raw_metadata": {},
        }
        p.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return {"sources": {"hn_algolia": {"status": "ok", "count": 1}}}

    monkeypatch.setattr("agent.pipeline.run_real_collection", fake_collect)
    monkeypatch.setattr("agent.pipeline.load_ai_triage_config", lambda path: {"enabled": True, "dry_run": True, "allow_ai_to_bypass_final_filter": False, "coarse_stage": {"enabled": False, "provider": "none"}, "final_stage": {"enabled": True, "provider": "mock", "model": "m", "sample_limit": 10}})
    summary = run_daily_pipeline(raw_items_path=tmp_path / "data" / "raw_items.jsonl", markdown_report_path=tmp_path / "reports" / "r.md")
    assert summary["opportunities_generated"] == 0
    assert summary["ai_triage_summary"]["openai_final_input_count"] == 0
    assert summary["ai_triage_summary"]["openai_final_scored_count"] == 0


def test_daily_pipeline_writes_timing_diagnostics_and_skipped_deepseek(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()

    def fake_collect(**kwargs):
        p = tmp_path / "data" / "raw_items.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
        return {"sources": {"hn_algolia": {"status": "ok", "count": 0}}}

    monkeypatch.setattr("agent.pipeline.run_real_collection", fake_collect)
    monkeypatch.setattr("agent.pipeline.load_ai_triage_config", lambda path: {"enabled": False, "coarse_stage": {"enabled": False}, "final_stage": {"enabled": False}})
    summary = run_daily_pipeline(raw_items_path=tmp_path / "data" / "raw_items.jsonl", markdown_report_path=tmp_path / "reports" / "r.md", json_summary_path=tmp_path / "reports" / "r.json")

    timing = summary["timing_diagnostics"]
    assert timing["run_started_at"]
    assert timing["run_finished_at"]
    assert isinstance(timing["total_runtime_seconds"], (int, float))
    assert timing["stage_statuses"]["deepseek_coarse"] in {"disabled", "skipped"}
    assert "## Timing Diagnostics" in (tmp_path / "reports" / "r.md").read_text(encoding="utf-8")
    payload = json.loads((tmp_path / "reports" / "r.json").read_text(encoding="utf-8"))
    assert "timing_diagnostics" in payload
    assert payload["timing_diagnostics"]["stage_statuses"]["deepseek_coarse"] in {"disabled", "skipped"}
