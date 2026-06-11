import json

from agent.main import run_collect_fixture


def test_collect_fixture_writes_jsonl_output(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "configs" / "queries.yaml").write_text(
        "queries:\n  sourcing:\n    - Alibaba alternative\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "fixtures" / "sample_raw_items.json").write_text(
        json.dumps(
            [
                {
                    "source": "mock_forum",
                    "source_type": "forum_post",
                    "url": "https://example.com/item",
                    "title": "Alibaba alternative",
                    "content": "Need a vetted supplier search option.",
                    "author": "fixture_user",
                    "published_at": "2026-01-01T00:00:00Z",
                    "fetched_at": "2026-05-18T00:00:00Z",
                    "query": "Alibaba alternative",
                    "language": "en",
                    "raw_metadata": {"fixture": True},
                }
            ]
        ),
        encoding="utf-8",
    )

    output_path = run_collect_fixture()

    assert output_path.exists()
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["title"] == "Alibaba alternative"
