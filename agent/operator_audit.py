from __future__ import annotations

import os
from typing import Any

from agent.config import load_ai_triage_config, load_delivery_config, load_queries, load_sources_config

DELIVERY_SECRET_NAMES = [
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "REPORT_SENDER_EMAIL",
    "REPORT_TEST_RECIPIENT_EMAIL",
]
DEEPSEEK_SECRET_NAMES = ["DEEPSEEK_API_KEY"]
OPENAI_FINAL_SECRET_NAMES = ["OPENAI_API_KEY"]
OPTIONAL_VARIABLE_NAMES = [
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "AI_COARSE_MODEL",
    "AI_COARSE_CONTEXT_WINDOW",
    "AI_COARSE_ENABLE_1M_CONTEXT",
    "AI_COARSE_REASONING_EFFORT",
    "SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT",
    "SOURCE_HN_ENABLED",
    "SOURCE_GDELT_ENABLED",
    "SOURCE_STACKEXCHANGE_ENABLED",
]
UNUSED_OR_DELETE_CANDIDATES = [
    "REPORT_RECIPIENT_EMAIL",
    "COARSE_AI_API_KEY",
    "COARSE_AI_MODEL",
    "FINAL_AI_API_KEY",
    "FINAL_AI_MODEL",
    "CODEX_MODEL",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
]


def _presence(names: list[str]) -> dict[str, str]:
    return {name: "present" if os.getenv(name, "").strip() else "missing" for name in names}


def build_config_audit() -> dict[str, Any]:
    sources = load_sources_config("configs/sources.yaml")
    queries = load_queries("configs/queries.yaml")
    ai = load_ai_triage_config("configs/ai_triage.yaml")
    delivery = load_delivery_config("configs/delivery.yaml")
    categories = queries.get("queries", {})
    enabled_sources = [name for name, cfg in sources.items() if cfg.get("enabled")]
    disabled_sources = [name for name, cfg in sources.items() if not cfg.get("enabled")]
    source_details = {
        name: {
            "enabled": bool(cfg.get("enabled")),
            "source_type": cfg.get("source_type"),
            "role": cfg.get("role"),
            "max_results": int(cfg.get("max_results", cfg.get("max_items", 0))),
            "timeout_seconds": int(cfg.get("timeout_seconds", 0)),
            "include_categories": cfg.get("include_categories"),
        }
        for name, cfg in sources.items()
    }
    se_sites = list(sources.get("stackexchange", {}).get("sites") or [])
    coarse = dict(ai.get("coarse_stage", {}) or {})
    final = dict(ai.get("final_stage", {}) or {})
    return {
        "enabled_sources": enabled_sources,
        "disabled_sources": disabled_sources,
        "source_roles": {name: cfg.get("role") for name, cfg in sources.items()},
        "source_max_results": {name: int(cfg.get("max_results", cfg.get("max_items", 0))) for name, cfg in sources.items()},
        "source_details": source_details,
        "stackexchange": {"site_count": len(se_sites), "sites": se_sites},
        "query_category_count": len(categories) if isinstance(categories, dict) else 0,
        "ai_enabled": bool(ai.get("enabled", False)),
        "coarse_enabled": bool(ai.get("enabled", False) and coarse.get("enabled", False)),
        "coarse_provider": coarse.get("provider"),
        "coarse_model": coarse.get("model"),
        "coarse_base_url": coarse.get("base_url"),
        "coarse_reasoning_effort": coarse.get("reasoning_effort"),
        "coarse_context_window": coarse.get("context_window", "default"),
        "final_enabled": bool(ai.get("enabled", False) and final.get("enabled", False)),
        "final_provider": final.get("provider"),
        "final_model": final.get("model"),
        "true_codex_sdk_supported": False,
        "true_codex_sdk_enabled": False,
        "allow_ai_to_bypass_final_filter": False,
        "validation_warnings": [str(w) for w in ai.get("validation_warnings", [])],
        "scheduled_send_report_to_test_recipient": bool(delivery.get("enabled", False)),
        "delivery_test_recipient_mode": bool(delivery.get("test_recipient_mode", True)),
        "delivery_allow_non_test_recipient": bool(delivery.get("allow_non_test_recipient", False)),
        "delivery_attach_markdown": bool(delivery.get("attach_markdown", True)),
        "delivery_attach_json": bool(delivery.get("attach_json_summary", True)),
    }


def build_env_inventory() -> dict[str, Any]:
    ai = load_ai_triage_config("configs/ai_triage.yaml")
    delivery = load_delivery_config("configs/delivery.yaml")
    coarse = dict(ai.get("coarse_stage", {}) or {})
    final = dict(ai.get("final_stage", {}) or {})
    required_now: list[str] = []
    if bool(delivery.get("enabled", False)):
        required_now.extend(DELIVERY_SECRET_NAMES)
    if bool(ai.get("enabled", False) and coarse.get("enabled", False) and coarse.get("provider") == "deepseek"):
        required_now.extend(DEEPSEEK_SECRET_NAMES)
    if bool(ai.get("enabled", False) and final.get("enabled", False) and final.get("provider") == "openai_responses"):
        required_now.extend(OPENAI_FINAL_SECRET_NAMES)
    required_now = sorted(dict.fromkeys(required_now))
    deepseek_required = bool(ai.get("enabled", False) and coarse.get("enabled", False) and coarse.get("provider") == "deepseek")
    openai_final_required = bool(ai.get("enabled", False) and final.get("enabled", False) and final.get("provider") == "openai_responses")
    inventory = {
        "required_now": required_now,
        "required_for_deepseek": DEEPSEEK_SECRET_NAMES if deepseek_required else [],
        "required_for_delivery": DELIVERY_SECRET_NAMES,
        "required_for_openai_final": OPENAI_FINAL_SECRET_NAMES if openai_final_required else [],
        "optional": OPTIONAL_VARIABLE_NAMES,
        "unused_or_delete_candidates": UNUSED_OR_DELETE_CANDIDATES,
        "presence": {
            "required_now": _presence(required_now),
            "required_for_deepseek": _presence(DEEPSEEK_SECRET_NAMES if deepseek_required else []),
            "required_for_delivery": _presence(DELIVERY_SECRET_NAMES),
            "required_for_openai_final": _presence(OPENAI_FINAL_SECRET_NAMES if openai_final_required else []),
            "optional": _presence(OPTIONAL_VARIABLE_NAMES),
            "unused_or_delete_candidates": _presence(UNUSED_OR_DELETE_CANDIDATES),
        },
        "notes": [
            "Names only are reported; secret values and prefixes are never printed.",
            "GitHub secret inventory cannot be read directly unless names are present in this process environment.",
            "REPORT_RECIPIENT_EMAIL is a delete candidate for current test-recipient-only delivery.",
        ],
    }
    return inventory
