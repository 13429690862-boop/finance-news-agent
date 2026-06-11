from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml, os
from agent.config import load_queries, load_quality_gate_config, load_query_optimizer_config, load_ai_triage_config, load_delivery_config
from agent.ai_triage import DEEPSEEK_API_KEY_ENV, OPENAI_API_KEY_ENV, ai_provider_dry_run_check
from agent.delivery import REQUIRED_SMTP

EXPECTED_REQUIREMENTS=["httpx","PyYAML","pytest","pydantic","openai"]
PROFILES={"no_secret_default","ai_provider_dry_run","deepseek_coarse_dry_run","delivery_test_recipient","full_test_dry_run"}

def run_production_audit(profile: str = "no_secret_default") -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    checks=[]
    def add(name, ok, detail=""): checks.append({"check":name,"ok":ok,"detail":detail})
    req=Path("requirements.txt").read_text(encoding="utf-8").strip().splitlines(); add("requirements_utf8_exact", req==EXPECTED_REQUIREMENTS, str(req))
    for p in ["configs/queries.yaml","configs/sources.yaml","configs/quality_gate.yaml","configs/query_optimizer.yaml","configs/ai_triage.yaml","configs/delivery.yaml"]:
        pp=Path(p); ok=pp.exists()
        if ok:
            try: yaml.safe_load(pp.read_text(encoding='utf-8'))
            except Exception as e: ok=False; add(f"{p}_parse",False,str(e)); continue
        add(f"{p}_exists_parse", ok, "")
    q=load_queries(); add("queries_load", True, f"sources={len(q.get('sources',[]))}")
    load_quality_gate_config("configs/quality_gate.yaml"); add("quality_gate_load", True, "")
    load_query_optimizer_config("configs/query_optimizer.yaml"); add("query_optimizer_load", True, "")
    add("workflow_exists", Path('.github/workflows/daily.yml').exists(), "")
    gi=Path('.gitignore').read_text(encoding='utf-8') if Path('.gitignore').exists() else ''
    add("gitignore_pyc",("*.pyc" in gi) or ("*.py[codz]" in gi), "")
    for pat in [".pytest_cache/","reports/*.md","reports/*.json","data/*.jsonl"]: add(f"gitignore_{pat}", pat in gi, "")

    ai = load_ai_triage_config("configs/ai_triage.yaml")
    if profile == "deepseek_coarse_dry_run":
        ai = dict(ai)
        ai["enabled"] = True
        ai["dry_run"] = False
        ai["dry_run_provider_check"] = True
        ai["provider_check_sample_limit"] = 1
        coarse = dict(ai.get("coarse_stage", {}))
        coarse.update({"enabled": True, "provider": "deepseek", "sample_limit": 3, "dry_run": False})
        final = dict(ai.get("final_stage", {}))
        final.update({"enabled": False, "provider": "none", "dry_run": True})
        ai["coarse_stage"] = coarse
        ai["final_stage"] = final
        ai["allow_ai_to_bypass_final_filter"] = False
    delivery = load_delivery_config("configs/delivery.yaml")
    ai_readiness = ai_provider_dry_run_check(ai)
    ai_check_enabled = profile in {"ai_provider_dry_run","deepseek_coarse_dry_run","full_test_dry_run"} or bool(ai.get("enabled", False))
    delivery_check_enabled = profile in {"delivery_test_recipient","full_test_dry_run"} or bool(delivery.get("enabled", False) and delivery.get("dry_run_delivery_check", False))
    missing_ai = list(ai_readiness.get("missing_secrets", [])) if ai_check_enabled else []
    delivery_test_mode = profile in {"delivery_test_recipient", "full_test_dry_run"} or bool(delivery.get("test_recipient_mode", True))
    recipient = os.getenv("REPORT_TEST_RECIPIENT_EMAIL", "").strip() if delivery_test_mode else os.getenv("REPORT_RECIPIENT_EMAIL", "").strip()
    missing_delivery = [k for k in REQUIRED_SMTP if not os.getenv(k, "").strip()] if delivery_check_enabled else []
    if delivery_check_enabled and not recipient: missing_delivery.append("REPORT_TEST_RECIPIENT_EMAIL" if delivery_test_mode else "REPORT_RECIPIENT_EMAIL")
    secrets_required = ai_check_enabled or delivery_check_enabled
    ai_ready = not ai_check_enabled or len(missing_ai)==0
    delivery_ready = not delivery_check_enabled or len(missing_delivery)==0
    add("ai_no_secret_safe", (not ai.get("enabled", False)) or not ai_check_enabled or ai_ready, "")
    add("deepseek_coarse_stage_observable", "coarse_stage" in ai and ai.get("coarse_stage", {}).get("provider") in {"none", "mock", "deepseek"}, "")
    add("openai_final_stage_observable", "final_stage" in ai and ai.get("final_stage", {}).get("provider") in {"none", "mock", "openai_responses"}, "")
    add("ai_final_filter_bypass_forbidden", not bool(ai.get("allow_ai_to_bypass_final_filter", False)), "")
    add("delivery_no_secret_safe", (not delivery.get("enabled", False)) or delivery_ready, "")
    add("test_recipient_mode_default_safe", bool(delivery.get("test_recipient_mode", True)), "")
    ok=all(c['ok'] for c in checks)
    return {"ok":ok,"checks":checks,"profile":profile,"secrets_required":secrets_required,"ai_secrets_ready":ai_ready,"delivery_secrets_ready":delivery_ready,"missing_ai_secrets":missing_ai,"missing_delivery_secrets":sorted(set(missing_delivery)),"no_secret_safe": (not secrets_required) or (not ai_check_enabled and not delivery_check_enabled),"deepseek_secrets_required": bool(ai.get("enabled", False) and ai.get("coarse_stage", {}).get("enabled", False) and ai.get("coarse_stage", {}).get("provider") == "deepseek"),"deepseek_secrets_ready": DEEPSEEK_API_KEY_ENV not in missing_ai,"openai_final_secrets_required": bool(ai.get("enabled", False) and ai.get("final_stage", {}).get("enabled", False) and ai.get("final_stage", {}).get("provider") == "openai_responses"),"openai_final_secrets_ready": OPENAI_API_KEY_ENV not in missing_ai,"coarse_stage_enabled": bool(ai.get("enabled", False) and ai.get("coarse_stage", {}).get("enabled", False)),"final_stage_enabled": bool(ai.get("enabled", False) and ai.get("final_stage", {}).get("enabled", False)),"deepseek_coarse_supported": ai_readiness.get("deepseek_coarse_supported", True),"deepseek_coarse_enabled": ai_readiness.get("deepseek_coarse_enabled", False),"deepseek_coarse_ready": ai_readiness.get("deepseek_coarse_ready", False),"openai_final_supported": ai_readiness.get("openai_final_supported", True),"openai_final_enabled": ai_readiness.get("openai_final_enabled", False),"openai_final_ready": ai_readiness.get("openai_final_ready", False),"true_codex_sdk_supported": ai_readiness.get("true_codex_sdk_supported", False),"true_codex_sdk_enabled": ai_readiness.get("true_codex_sdk_enabled", False),"true_codex_sdk_note": ai_readiness.get("true_codex_sdk_note", "Not implemented; current final scoring uses OpenAI Responses API."),"ai_provider_readiness": ai_readiness}
