import json
from pathlib import Path

from agent.models import RawItem
from agent.opportunity_filter import evaluate_opportunity_sanity
from agent.quality_gate import evaluate_raw_item_quality


def _mk_item(title: str, content: str | None = None) -> RawItem:
    return RawItem(
        source="fixture",
        source_type="forum_post",
        url="https://example.com/item",
        title=title,
        content=content or title,
        author="tester",
        published_at="2026-01-01T00:00:00Z",
        fetched_at="2026-01-01T00:00:00Z",
        query="",
        language="en",
        raw_metadata={},
    )


def test_recall_benchmark_true_demand_passes_quality_and_final_filter():
    data = json.loads(Path("tests/fixtures/recall_benchmark_raw_items.json").read_text(encoding="utf-8"))
    final_pass_count = 0
    for title in data["true_demand"]:
        content = f"I am a small business buyer. {title}. Need workflow help for supplier, logistics, or API integration."
        item = _mk_item(title, content)
        quality = evaluate_raw_item_quality(item)
        assert quality.is_qualified, title
        if evaluate_opportunity_sanity({"title": title}, {"title": content, "content": content}).is_valid:
            final_pass_count += 1
    assert final_pass_count >= 6


def test_recall_benchmark_noise_rejects_quality_gate():
    data = json.loads(Path("tests/fixtures/recall_benchmark_raw_items.json").read_text(encoding="utf-8"))
    for title in data["noise"]:
        item = _mk_item(title)
        quality = evaluate_raw_item_quality(item)
        assert not quality.is_qualified, title
