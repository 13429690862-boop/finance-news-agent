"""Configuration loading helpers for source-ingestion queries and scoring rules."""

from __future__ import annotations

from importlib.util import find_spec
import os
import re
from pathlib import Path
from typing import Any



ALLOWED_SOURCE_NAMES = ("hn_algolia", "gdelt", "stackexchange")
_SOURCE_ENV_ENABLED = {
    "hn_algolia": "SOURCE_HN_ENABLED",
    "gdelt": "SOURCE_GDELT_ENABLED",
    "stackexchange": "SOURCE_STACKEXCHANGE_ENABLED",
}
_ALLOWED_REASONING_EFFORTS = {"none", "low", "medium", "high", "max"}
_ALLOWED_COARSE_CONTEXT_WINDOWS = {"default", "1m"}
_CLAUDE_CODE_CONTEXT_SUFFIX_WARNING = "AI_COARSE_MODEL contains Claude Code [1m] suffix; use AI_COARSE_MODEL=deepseek-v4-pro and AI_COARSE_CONTEXT_WINDOW=1m"
_CLAUDE_CODE_CONTEXT_SUFFIX_ERROR = "Use AI_COARSE_MODEL=deepseek-v4-pro and AI_COARSE_CONTEXT_WINDOW=1m; [1m] suffix is reserved for Claude Code / Anthropic alias configuration."
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")


def _env_bool(name: str, default: bool | None = None) -> bool | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _env_int(name: str, default: Any) -> Any:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: Any) -> Any:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _env_str(name: str, default: Any = None) -> Any:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _validate_model_name(value: Any, field_name: str) -> str:
    model = str(value or "").strip()
    if not model:
        raise ValueError(f"{field_name} must be a non-empty model name")
    if field_name == "coarse_stage.model" and model.endswith("[1m]"):
        raise ValueError(_CLAUDE_CODE_CONTEXT_SUFFIX_ERROR)
    if not _MODEL_NAME_RE.fullmatch(model) or any(ch in model for ch in "[]{}()\x1b"):
        raise ValueError(
            f"{field_name} contains unsupported formatting artifacts or characters; "
            "use a plain model id such as deepseek-v4-pro"
        )
    return model


def _validate_coarse_context_window(value: Any) -> str:
    context_window = str(value or "default").strip().lower() or "default"
    if context_window not in _ALLOWED_COARSE_CONTEXT_WINDOWS:
        raise ValueError("coarse_stage.context_window must be one of 1m, default")
    return context_window


def load_sources_config(path: str | Path = "configs/sources.yaml") -> dict[str, Any]:
    """Load safe operator-facing source configuration with env/GitHub Variable overrides."""
    defaults: dict[str, Any] = {
        "hn_algolia": {"enabled": True, "source_type": "discussion", "role": "developer_demand", "max_results": 20, "timeout_seconds": 15},
        "gdelt": {"enabled": True, "source_type": "news", "role": "market_signal", "max_results": 20, "timeout_seconds": 15},
        "stackexchange": {
            "enabled": True,
            "source_type": "discussion",
            "role": "technical_demand",
            "max_results": 20,
            "timeout_seconds": 15,
            "site": "stackoverflow",
            "sites": ["stackoverflow", "webmasters", "softwareengineering", "magento", "wordpress", "salesforce"],
        },
    }
    cfg = {name: dict(value) for name, value in defaults.items()}
    config_path = Path(path)
    if config_path.exists():
        if find_spec("yaml") is None:
            raise RuntimeError("PyYAML is required to load source configuration")
        import yaml
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("source configuration must be a mapping")
        unknown = sorted(str(name) for name in loaded if name not in ALLOWED_SOURCE_NAMES)
        if unknown:
            raise ValueError(f"unknown source configuration name(s): {', '.join(unknown)}")
        for name, value in loaded.items():
            if value is None:
                continue
            if not isinstance(value, dict):
                raise ValueError(f"source configuration '{name}' must be a mapping")
            merged = dict(cfg[name])
            merged.update(value)
            if "max_items" in merged and "max_results" not in value:
                merged["max_results"] = merged["max_items"]
            cfg[name] = merged

    for source_name, env_name in _SOURCE_ENV_ENABLED.items():
        override = _env_bool(env_name)
        if override is not None:
            cfg[source_name]["enabled"] = override

    _validate_sources_config(cfg)
    return cfg


def _validate_sources_config(config: dict[str, Any]) -> None:
    for name in config:
        if name not in ALLOWED_SOURCE_NAMES:
            raise ValueError(f"unknown source configuration name: {name}")
    for name in ALLOWED_SOURCE_NAMES:
        source = config.get(name, {})
        if not isinstance(source, dict):
            raise ValueError(f"source configuration '{name}' must be a mapping")
        if not isinstance(source.get("enabled"), bool):
            raise ValueError(f"source configuration '{name}.enabled' must be bool")
        for text_key in ("source_type", "role"):
            if not isinstance(source.get(text_key), str) or not source.get(text_key, "").strip():
                raise ValueError(f"source configuration '{name}.{text_key}' must be a non-empty string")
        for numeric_key in ("max_results", "timeout_seconds"):
            try:
                if int(source.get(numeric_key, 0)) < 0:
                    raise ValueError
            except Exception as exc:
                raise ValueError(f"source configuration '{name}.{numeric_key}' must be a non-negative integer") from exc
        include = source.get("include_categories")
        if include is not None and (not isinstance(include, list) or not all(isinstance(v, str) and v.strip() for v in include)):
            raise ValueError(f"source configuration '{name}.include_categories' must be a list of strings")
    sites = config.get("stackexchange", {}).get("sites")
    if sites is not None and (not isinstance(sites, list) or not all(isinstance(site, str) and site.strip() for site in sites)):
        raise ValueError("source configuration 'stackexchange.sites' must be a list of strings")


REQUIRED_SCORING_SECTIONS = (
    "demand_intent_keywords",
    "china_relevance_keywords",
    "market_intensity_high_keywords",
    "market_intensity_medium_keywords",
    "implementation_difficulty_high_keywords",
    "implementation_difficulty_medium_keywords",
    "monetization_clarity_high_keywords",
    "monetization_clarity_medium_keywords",
    "customer_type_rules",
    "risk_note_rules",
    "solution_rules",
)

_LIST_SCORING_SECTIONS = tuple(
    section for section in REQUIRED_SCORING_SECTIONS if section != "risk_note_rules"
)




REQUIRED_QUALITY_GATE_SECTIONS = (
    "minimum_positive_groups",
    "demand_intent_keywords",
    "actor_keywords",
    "workflow_keywords",
    "negative_topic_keywords",
)


def load_quality_gate_config(path: str | Path = "configs/quality_gate.yaml") -> dict[str, Any]:
    """Load and validate quality-gate configuration from YAML.

    Raises ValueError for invalid structure and falls back only when the file is missing.
    """
    from agent.quality_gate import DEFAULT_QUALITY_GATE_CONFIG

    config_path = Path(path)
    if not config_path.exists():
        return dict(DEFAULT_QUALITY_GATE_CONFIG)
    if find_spec("yaml") is None:
        raise RuntimeError("PyYAML is required to load quality gate configuration")

    import yaml

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("quality gate configuration must be a mapping")

    cfg = dict(DEFAULT_QUALITY_GATE_CONFIG)
    cfg.update(loaded)
    _validate_quality_gate_config(cfg, config_path)
    return cfg


def _validate_quality_gate_config(config: dict[str, Any], path: Path) -> None:
    missing = [section for section in REQUIRED_QUALITY_GATE_SECTIONS if section not in config]
    if missing:
        raise ValueError(f"quality gate configuration {path} is missing required sections: {', '.join(missing)}")

    mpg = config.get("minimum_positive_groups")
    if not isinstance(mpg, int) or mpg < 1 or mpg > 3:
        raise ValueError("quality gate configuration minimum_positive_groups must be an integer between 1 and 3")

    for section in ("demand_intent_keywords", "actor_keywords", "workflow_keywords", "negative_topic_keywords"):
        value = config.get(section)
        if not isinstance(value, list):
            raise ValueError(f"quality gate configuration section '{section}' must be a list")
        if not all(isinstance(k, str) and k.strip() for k in value):
            raise ValueError(f"quality gate configuration section '{section}' must contain non-empty strings")
def load_queries(path: str | Path = "configs/queries.yaml") -> dict[str, Any]:
    """Load query configuration from YAML."""
    config_path = Path(path)
    if find_spec("yaml") is None:
        return _load_queries_without_pyyaml(config_path)

    import yaml

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("query configuration must be a mapping")
    return loaded


def flatten_queries(config: dict[str, Any]) -> list[str]:
    """Flatten configured query categories into a deterministic de-duplicated list."""
    flattened: list[str] = []
    seen: set[str] = set()
    categories = config.get("queries", {})

    if isinstance(categories, dict):
        iterable = categories.values()
    elif isinstance(categories, list):
        iterable = [categories]
    else:
        raise ValueError("queries must be a mapping or list")

    for values in iterable:
        if values is None:
            continue
        if not isinstance(values, list):
            raise ValueError("each query category must contain a list")
        for query in values:
            if not isinstance(query, str):
                raise ValueError("queries must be strings")
            normalized = query.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                flattened.append(normalized)

    return flattened


def queries_for_source(config: dict[str, Any], source_name: str) -> list[str]:
    """Return source-specific queries, falling back to flattened queries."""
    return [record["query"] for record in query_records_for_source(config, source_name)]


def query_records_for_source(config: dict[str, Any], source_name: str) -> list[dict[str, str | None]]:
    """Return query records with source/category provenance."""
    categories = config.get("queries", {})
    profiles = config.get("source_profiles", {})
    profile = profiles.get(source_name, {}) if isinstance(profiles, dict) else {}
    profile_name = source_name if isinstance(profile, dict) and profile else None
    include_categories = profile.get("include_categories", []) if isinstance(profile, dict) else []

    if not isinstance(include_categories, list) or not include_categories:
        include_categories = list(categories.keys()) if isinstance(categories, dict) else []

    records: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for category in include_categories:
        values = categories.get(category, []) if isinstance(categories, dict) else []
        if not isinstance(values, list):
            raise ValueError(f"query category '{category}' must be a list")
        for query in values:
            if not isinstance(query, str):
                raise ValueError("queries must be strings")
            normalized = query.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                records.append({"query": normalized, "category": str(category), "source_profile": profile_name})
    if not records:
        for query in flatten_queries(config):
            records.append({"query": query, "category": "uncategorized", "source_profile": None})
    return records


def load_scoring_config(path: str | Path = "configs/scoring.yaml") -> dict[str, Any]:
    """Load and validate deterministic scoring-rule configuration from YAML."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"scoring configuration not found: {config_path}")
    if find_spec("yaml") is None:
        raise RuntimeError("PyYAML is required to load scoring configuration")

    import yaml

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("scoring configuration must be a mapping")

    _validate_scoring_config(loaded, config_path)
    return loaded


def _validate_scoring_config(config: dict[str, Any], path: Path) -> None:
    missing = [section for section in REQUIRED_SCORING_SECTIONS if section not in config]
    if missing:
        raise ValueError(f"scoring configuration {path} is missing required sections: {', '.join(missing)}")

    for section in _LIST_SCORING_SECTIONS:
        value = config[section]
        if not isinstance(value, list):
            raise ValueError(f"scoring configuration section '{section}' must be a list")
        if not value:
            raise ValueError(f"scoring configuration section '{section}' must not be empty")

    for section in (
        "demand_intent_keywords",
        "china_relevance_keywords",
        "market_intensity_high_keywords",
        "market_intensity_medium_keywords",
        "implementation_difficulty_high_keywords",
        "implementation_difficulty_medium_keywords",
        "monetization_clarity_high_keywords",
        "monetization_clarity_medium_keywords",
    ):
        if not all(isinstance(keyword, str) and keyword.strip() for keyword in config[section]):
            raise ValueError(f"scoring configuration section '{section}' must contain non-empty strings")

    for index, rule in enumerate(config["customer_type_rules"], start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"customer_type_rules item {index} must be a mapping")
        _validate_keyword_rule(rule, "customer_type", f"customer_type_rules item {index}")

    risk_note_rules = config["risk_note_rules"]
    if not isinstance(risk_note_rules, dict):
        raise ValueError("scoring configuration section 'risk_note_rules' must be a mapping")
    default_risk_note = risk_note_rules.get("default")
    if not isinstance(default_risk_note, str) or not default_risk_note.strip():
        raise ValueError("risk_note_rules.default must be a non-empty string")

    for index, rule in enumerate(config["solution_rules"], start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"solution_rules item {index} must be a mapping")
        _validate_keyword_rule(rule, "possible_solution", f"solution_rules item {index}")
        monetization_model = rule.get("monetization_model")
        if not isinstance(monetization_model, str) or not monetization_model.strip():
            raise ValueError(f"solution_rules item {index}.monetization_model must be a non-empty string")


def _validate_keyword_rule(rule: dict[str, Any], text_field: str, label: str) -> None:
    keywords = rule.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        raise ValueError(f"{label}.keywords must be a non-empty list")
    if not all(isinstance(keyword, str) and keyword.strip() for keyword in keywords):
        raise ValueError(f"{label}.keywords must contain non-empty strings")
    text_value = rule.get(text_field)
    if not isinstance(text_value, str) or not text_value.strip():
        raise ValueError(f"{label}.{text_field} must be a non-empty string")




def load_query_optimizer_config(path: str | Path = "configs/query_optimizer.yaml") -> dict[str, Any]:
    config_path = Path(path)
    defaults = {
        "enabled": True,
        "dry_run": True,
        "apply_changes": False,
        "max_additions_per_category": 3,
        "max_removals_per_category": 3,
        "allow_production_config_mutation": False,
    }
    if not config_path.exists():
        return defaults
    if find_spec("yaml") is None:
        return defaults
    import yaml

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("query optimizer configuration must be a mapping")
    cfg = dict(defaults)
    cfg.update(loaded)
    return cfg
def _load_queries_without_pyyaml(path: Path) -> dict[str, Any]:
    """Parse the small repository query YAML shape without external dependencies."""
    result: dict[str, Any] = {"queries": {}}
    current_category: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line == "queries:":
            continue
        if line.startswith("  ") and line.endswith(":"):
            current_category = line.strip()[:-1]
            result["queries"][current_category] = []
            continue
        if line.startswith("    - ") and current_category is not None:
            result["queries"][current_category].append(line.strip()[2:].strip('"\''))

    return result


def load_ai_triage_config(path: str | Path = "configs/ai_triage.yaml") -> dict[str, Any]:
    """Load the optional two-stage AI configuration with no-secret-safe defaults."""
    defaults: dict[str, Any] = {
        "enabled": False,
        "dry_run": True,
        "allow_ai_to_bypass_final_filter": False,
        "provider_check_sample_limit": 3,
        "fail_on_provider_check_error": False,
        "coarse_stage": {
            "enabled": False,
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "reasoning_effort": "max",
            "context_window": "default",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "timeout_seconds": 30,
            "batch_size": 10,
            "sample_limit": 50,
            "dry_run": True,
        },
        "final_stage": {
            "enabled": False,
            "provider": "none",
            "model": "gpt-5.3-codex",
            "base_url": "",
            "api_key_env": "OPENAI_API_KEY",
            "timeout_seconds": 60,
            "batch_size": 5,
            "sample_limit": 20,
            "dry_run": True,
        },
    }
    config_path = Path(path)
    loaded: dict[str, Any] = {}
    if config_path.exists():
        if find_spec("yaml") is None:
            raise RuntimeError("PyYAML is required to load ai triage configuration")
        import yaml

        parsed = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(parsed, dict):
            raise ValueError("ai triage config must be a mapping")
        loaded = parsed
    cfg = dict(defaults)
    for key, value in loaded.items():
        if key in {"coarse_stage", "final_stage"} and isinstance(value, dict):
            stage = dict(defaults[key])  # type: ignore[index]
            stage.update(value)
            cfg[key] = stage
        elif key in {"coarse_provider", "coarse_model", "final_provider", "final_model"}:
            # Backward-compatible migration from the previous flat mock-only config.
            continue
        else:
            cfg[key] = value
    if "coarse_provider" in loaded:
        cfg["coarse_stage"]["provider"] = "mock" if loaded.get("coarse_provider") == "mock_coarse" else loaded.get("coarse_provider")
    if "final_provider" in loaded:
        cfg["final_stage"]["provider"] = "mock" if loaded.get("final_provider") == "mock_final" else loaded.get("final_provider")
    if "coarse_model" in loaded:
        cfg["coarse_stage"]["model"] = loaded.get("coarse_model") or cfg["coarse_stage"]["model"]
    if "final_model" in loaded:
        cfg["final_stage"]["model"] = loaded.get("final_model") or cfg["final_stage"]["model"]

    enabled = _env_bool("AI_TRIAGE_ENABLED")
    if enabled is not None:
        cfg["enabled"] = enabled
    bypass = _env_bool("AI_ALLOW_BYPASS_FINAL_FILTER")
    if bypass is not None:
        cfg["allow_ai_to_bypass_final_filter"] = bypass
    default_profile = _env_str("AI_DEFAULT_PROFILE")
    if default_profile:
        cfg["default_profile"] = default_profile

    coarse = dict(cfg.get("coarse_stage", {}) or {})
    final = dict(cfg.get("final_stage", {}) or {})
    for key, env_name in (
        ("enabled", "AI_COARSE_ENABLED"),
    ):
        val = _env_bool(env_name)
        if val is not None:
            coarse[key] = val
    for key, env_name in (
        ("provider", "AI_COARSE_PROVIDER"),
        ("model", "AI_COARSE_MODEL"),
        ("base_url", "AI_COARSE_BASE_URL"),
        ("reasoning_effort", "AI_COARSE_REASONING_EFFORT"),
    ):
        raw = _env_str(env_name)
        if raw is not None:
            coarse[key] = raw
    coarse["timeout_seconds"] = _env_int("AI_COARSE_TIMEOUT_SECONDS", coarse.get("timeout_seconds"))
    coarse["batch_size"] = _env_int("AI_COARSE_BATCH_SIZE", coarse.get("batch_size"))
    coarse["sample_limit"] = _env_int("AI_COARSE_SAMPLE_LIMIT", coarse.get("sample_limit"))
    raw_context_window = _env_str("AI_COARSE_CONTEXT_WINDOW")
    if raw_context_window is not None:
        coarse["context_window"] = raw_context_window
    enable_1m_context = _env_bool("AI_COARSE_ENABLE_1M_CONTEXT")
    if enable_1m_context is not None:
        coarse["context_window"] = "1m" if enable_1m_context else "default"
    if os.getenv("AI_COARSE_TEMPERATURE", "").strip():
        coarse["temperature"] = _env_float("AI_COARSE_TEMPERATURE", coarse.get("temperature", 0))
    if os.getenv("AI_COARSE_MAX_OUTPUT_TOKENS", "").strip():
        coarse["max_output_tokens"] = _env_int("AI_COARSE_MAX_OUTPUT_TOKENS", coarse.get("max_output_tokens", 0))

    val = _env_bool("AI_FINAL_ENABLED")
    if val is not None:
        final["enabled"] = val
    for key, env_name in (
        ("provider", "AI_FINAL_PROVIDER"),
        ("model", "AI_FINAL_MODEL"),
        ("base_url", "AI_FINAL_BASE_URL"),
    ):
        raw = _env_str(env_name)
        if raw is not None:
            final[key] = raw
    final["timeout_seconds"] = _env_int("AI_FINAL_TIMEOUT_SECONDS", final.get("timeout_seconds"))
    final["sample_limit"] = _env_int("AI_FINAL_SAMPLE_LIMIT", final.get("sample_limit"))
    cfg["coarse_stage"] = coarse
    cfg["final_stage"] = final

    if not isinstance(cfg.get("enabled"), bool):
        raise ValueError("ai triage enabled must be bool")
    if not isinstance(cfg.get("dry_run"), bool):
        raise ValueError("ai triage dry_run must be bool")
    if bool(cfg.get("allow_ai_to_bypass_final_filter", False)):
        raise ValueError("allow_ai_to_bypass_final_filter must remain false")

    allowed = {"coarse_stage": {"none", "mock", "deepseek"}, "final_stage": {"none", "mock", "openai_responses"}}
    for stage_name, providers in allowed.items():
        stage = cfg.get(stage_name)
        if not isinstance(stage, dict):
            raise ValueError(f"{stage_name} must be a mapping")
        if not isinstance(stage.get("enabled"), bool):
            raise ValueError(f"{stage_name}.enabled must be bool")
        provider = str(stage.get("provider", "none"))
        if provider not in providers:
            raise ValueError(f"{stage_name}.provider must be one of {', '.join(sorted(providers))}")
        stage_is_active = bool(cfg.get("enabled", False) and stage.get("enabled", False))
        if provider != "none" or bool(stage.get("enabled", False)):
            raw_stage_model = str(stage.get("model", "")).strip()
            try:
                stage["model"] = _validate_model_name(raw_stage_model, f"{stage_name}.model")
            except ValueError as exc:
                if stage_is_active:
                    raise
                default_stage = defaults.get(stage_name, {})
                stage["model"] = str(default_stage.get("model", ""))
                if stage_name == "coarse_stage" and raw_stage_model.endswith("[1m]"):
                    cfg.setdefault("validation_warnings", []).append(_CLAUDE_CODE_CONTEXT_SUFFIX_WARNING)
                    stage["context_window"] = "1m"
                else:
                    cfg.setdefault("validation_warnings", []).append(str(exc))
        if stage_name == "coarse_stage":
            effort = str(stage.get("reasoning_effort", "max")).strip()
            if effort not in _ALLOWED_REASONING_EFFORTS:
                raise ValueError("coarse_stage.reasoning_effort must be one of high, low, max, medium, none")
            stage["context_window"] = _validate_coarse_context_window(stage.get("context_window", "default"))
        for numeric in ("timeout_seconds", "batch_size", "sample_limit"):
            try:
                if float(stage.get(numeric, 0)) < 0:
                    raise ValueError
            except Exception as exc:
                raise ValueError(f"{stage_name}.{numeric} must be non-negative") from exc
    return cfg


def load_delivery_config(path: str | Path = "configs/delivery.yaml") -> dict[str, Any]:
    defaults = {"enabled": False, "channel": "none", "test_recipient_mode": True, "allow_non_test_recipient": False, "send_empty_report": True, "attach_markdown": True, "attach_json_summary": True, "fail_on_delivery_error": False, "dry_run_delivery_check": False}
    config_path = Path(path)
    cfg = dict(defaults)
    if config_path.exists():
        if find_spec("yaml") is None:
            raise RuntimeError("PyYAML is required to load delivery configuration")
        import yaml
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("delivery config must be a mapping")
        cfg.update(loaded)

    for key, env_name in (
        ("enabled", "SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT"),
        ("test_recipient_mode", "DELIVERY_TEST_RECIPIENT_MODE"),
        ("allow_non_test_recipient", "DELIVERY_ALLOW_NON_TEST_RECIPIENT"),
        ("send_empty_report", "DELIVERY_SEND_EMPTY_REPORT"),
        ("attach_markdown", "DELIVERY_ATTACH_MARKDOWN"),
        ("attach_json_summary", "DELIVERY_ATTACH_JSON"),
    ):
        val = _env_bool(env_name)
        if val is not None:
            cfg[key] = val
    if str(cfg.get("channel")) not in {"none", "email"}:
        raise ValueError("delivery channel must be none or email")
    for key in ("enabled", "test_recipient_mode", "allow_non_test_recipient", "send_empty_report", "attach_markdown", "attach_json_summary"):
        if not isinstance(cfg.get(key), bool):
            raise ValueError(f"delivery {key} must be bool")
    if bool(cfg.get("allow_non_test_recipient", False)):
        raise ValueError("delivery allow_non_test_recipient must remain false")
    return cfg
