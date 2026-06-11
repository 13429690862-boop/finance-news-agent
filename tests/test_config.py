from pathlib import Path

import pytest

from agent.config import flatten_queries, load_queries, load_scoring_config, queries_for_source


FORBIDDEN_BROAD_TERMS = {
    "China politics",
    "Chinese Communist Party",
    "China censorship",
    "Tiananmen",
    "China economy",
    "China news",
    "Chinese culture",
}


def test_flatten_queries_deduplicates_and_preserves_order():
    config = {"queries": {"first": ["1688 agent", "1688 agent"], "second": ["China freight forwarder"]}}

    assert flatten_queries(config) == [
        "1688 agent",
        "China freight forwarder",
    ]


def test_repository_query_config_is_demand_oriented_and_non_empty():
    config = load_queries(Path("configs/queries.yaml"))
    assert isinstance(config.get("queries"), dict)
    for category, values in config["queries"].items():
        assert isinstance(values, list), category
        assert values, category


def test_no_duplicates_after_flattening():
    config = load_queries(Path("configs/queries.yaml"))
    flattened = flatten_queries(config)
    assert len(flattened) == len(set(flattened))


def test_source_profiles_reference_existing_categories():
    config = load_queries(Path("configs/queries.yaml"))
    categories = set(config["queries"])
    for source_name, profile in config.get("source_profiles", {}).items():
        for category in profile.get("include_categories", []):
            assert category in categories, f"{source_name} references missing category {category}"


def test_source_routing_fallback_and_specific_selection():
    config = load_queries(Path("configs/queries.yaml"))
    hn_queries = queries_for_source(config, "hn_algolia")
    gdelt_queries = queries_for_source(config, "gdelt")
    fallback_queries = queries_for_source(config, "unknown_source")

    assert hn_queries
    assert gdelt_queries
    assert fallback_queries == flatten_queries(config)
    assert "WeChat Pay API integration help" in hn_queries
    assert "WeChat Pay API integration help" not in gdelt_queries


def test_daily_active_queries_exclude_broad_forbidden_terms():
    config = load_queries(Path("configs/queries.yaml"))
    for source_name in ("hn_algolia", "stackexchange", "gdelt"):
        routed = "\n".join(queries_for_source(config, source_name)).lower()
        for term in FORBIDDEN_BROAD_TERMS:
            assert term.lower() not in routed


def test_gdelt_profile_is_not_broad_news_politics():
    config = load_queries(Path("configs/queries.yaml"))
    gdelt_queries = "\n".join(queries_for_source(config, "gdelt")).lower()
    for banned in ("politics", "censorship", "culture", "news"):
        assert banned not in gdelt_queries


def test_scoring_config_loads_required_sections():
    config = load_scoring_config(Path("configs/scoring.yaml"))

    assert "demand_intent_keywords" in config
    assert "customer_type_rules" in config
    assert "solution_rules" in config


def test_scoring_config_missing_required_key_has_clear_error(tmp_path):
    invalid_path = tmp_path / "scoring.yaml"
    invalid_path.write_text("demand_intent_keywords:\n  - need\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required sections"):
        load_scoring_config(invalid_path)

from agent.config import load_quality_gate_config


def test_load_quality_gate_config_missing_file_uses_defaults(tmp_path):
    cfg = load_quality_gate_config(tmp_path / "missing.yaml")
    assert "demand_intent_keywords" in cfg
    assert cfg["minimum_positive_groups"] >= 1


def test_load_quality_gate_config_invalid_raises(tmp_path):
    path = tmp_path / "quality_gate.yaml"
    path.write_text("minimum_positive_groups: nope\n", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        load_quality_gate_config(path)
