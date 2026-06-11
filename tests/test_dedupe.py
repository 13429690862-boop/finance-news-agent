from agent.dedupe import dedupe_items, normalize_title


def test_normalize_title_lowercases_and_collapses_whitespace():
    assert normalize_title("  China   Demand\nAgent  ") == "china demand agent"


def test_dedupe_items_by_exact_url():
    items = [
        {"title": "First", "url": "https://example.com/a"},
        {"title": "Different title", "url": "https://example.com/a"},
    ]

    assert dedupe_items(items) == [items[0]]


def test_dedupe_items_by_normalized_title():
    items = [
        {"title": "China Demand Agent", "url": "https://example.com/a"},
        {"title": " china   demand agent ", "url": "https://example.com/b"},
    ]

    assert dedupe_items(items) == [items[0]]
