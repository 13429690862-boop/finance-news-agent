import json

from agent.collect import run_real_collection
from agent.models import RawItem


def _item(source: str, url: str, title: str, content: str = "Need China supplier help") -> RawItem:
    return RawItem(source=source, source_type="forum_post", url=url, title=title, content=content, author="a", published_at="2026-01-01T00:00:00Z", fetched_at="2026-05-18T00:00:00Z", query="china supplier", language="en", raw_metadata={})


def test_collect_real_aggregate_dedupe_and_write(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir(); (tmp_path / "data").mkdir()
    (tmp_path / "configs" / "queries.yaml").write_text("queries:\n  q:\n    - china supplier\n", encoding="utf-8")
    (tmp_path / "configs" / "sources.yaml").write_text("hn_algolia:\n  enabled: true\ngdelt:\n  enabled: true\nstackexchange:\n  enabled: true\n", encoding="utf-8")

    monkeypatch.setattr("agent.collect.HNAlgoliaCollector.collect", lambda self, queries, max_items: [_item("hn","https://a.com","Need supplier")])
    monkeypatch.setattr("agent.collect.GDELTCollector.collect", lambda self, queries, max_items: [_item("gdelt","https://a.com","Need supplier")])
    monkeypatch.setattr("agent.collect.StackExchangeCollector.collect", lambda self, queries, max_items: [_item("se","https://b.com","Need supplier", "Need China supplier help")])

    summary = run_real_collection()
    assert summary["total_before_dedupe"] == 3
    assert summary["total_after_dedupe"] == 1
    assert (tmp_path / "data" / "raw_items.jsonl").exists()


def test_collect_real_one_failure_and_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir(); (tmp_path / "data").mkdir()
    (tmp_path / "configs" / "queries.yaml").write_text("queries:\n  q:\n    - china supplier\n", encoding="utf-8")
    (tmp_path / "configs" / "sources.yaml").write_text("hn_algolia:\n  enabled: false\ngdelt:\n  enabled: true\nstackexchange:\n  enabled: true\n", encoding="utf-8")
    monkeypatch.setattr("agent.collect.GDELTCollector.collect", lambda self, queries, max_items: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr("agent.collect.StackExchangeCollector.collect", lambda self, queries, max_items: [_item("se","https://b.com","Need supplier x")])

    summary = run_real_collection()
    assert summary["sources"]["hn_algolia"]["status"] == "skipped"
    assert summary["sources"]["gdelt"]["status"] == "error"
    assert summary["total_after_dedupe"] == 1
    line = (tmp_path / "data" / "raw_items.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(line)["url"] == "https://b.com"


def test_collect_real_uses_source_specific_queries(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir(); (tmp_path / "data").mkdir()
    (tmp_path / "configs" / "queries.yaml").write_text(
        "queries:\n"
        "  a:\n"
        "    - alpha\n"
        "  b:\n"
        "    - beta\n"
        "source_profiles:\n"
        "  hn_algolia:\n"
        "    include_categories:\n"
        "      - a\n"
        "  gdelt:\n"
        "    include_categories:\n"
        "      - b\n",
        encoding="utf-8",
    )
    (tmp_path / "configs" / "sources.yaml").write_text("hn_algolia:\n  enabled: true\ngdelt:\n  enabled: true\nstackexchange:\n  enabled: false\n", encoding="utf-8")

    seen = {}
    monkeypatch.setattr("agent.collect.HNAlgoliaCollector.collect", lambda self, queries, max_items: seen.setdefault("hn", queries) and [])
    monkeypatch.setattr("agent.collect.GDELTCollector.collect", lambda self, queries, max_items: seen.setdefault("gdelt", queries) and [])

    run_real_collection()
    assert seen["hn"] == ["alpha"]
    assert seen["gdelt"] == ["beta"]
