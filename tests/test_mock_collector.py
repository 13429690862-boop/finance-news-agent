from agent.models import RawItem
from agent.sources.mock import MockCollector


def test_mock_collector_returns_raw_items_from_fixture():
    collector = MockCollector()

    items = collector.collect(queries=["Alibaba alternative"], max_items=3)

    assert len(items) == 3
    assert all(isinstance(item, RawItem) for item in items)
    assert items[0].title == "Looking for an Alibaba alternative with vetted factories"


def test_mock_collector_is_deterministic_and_supports_max_items():
    collector = MockCollector()

    first = collector.collect(queries=["one"], max_items=2)
    second = collector.collect(queries=["two"], max_items=2)

    assert [item.url for item in first] == [item.url for item in second]
    assert len(first) == 2


def test_mock_collector_returns_empty_list_for_non_positive_max_items():
    assert MockCollector().collect(queries=["anything"], max_items=0) == []
