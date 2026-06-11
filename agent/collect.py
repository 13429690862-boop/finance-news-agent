"""Real source collection orchestration and cross-source deduplication."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.config import load_queries, load_sources_config, query_records_for_source
from agent.models import RawItem
from agent.sources.gdelt import GDELTCollector
from agent.sources.hn import HNAlgoliaCollector
from agent.sources.stackexchange import StackExchangeCollector
from agent.telemetry import build_base_telemetry, ensure_category, ensure_source, finalize_telemetry

_SPACE_RE = re.compile(r"\s+")

def _norm_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value.strip().lower())

def _content_key(item: RawItem) -> str:
    base = _norm_text(item.content)[:200]
    return base or f"{_norm_text(item.title)}|{_norm_text(item.author)}"

def _dedupe_raw_items(items: list[RawItem]) -> list[RawItem]:
    seen_urls:set[str]=set(); seen_titles:set[str]=set(); seen_content:set[str]=set(); out=[]
    for item in items:
        url=item.url.strip(); title=_norm_text(item.title); content=_content_key(item)
        if (url and url in seen_urls) or (title and title in seen_titles) or (content and content in seen_content):
            continue
        if url: seen_urls.add(url)
        if title: seen_titles.add(title)
        if content: seen_content.add(content)
        out.append(item)
    return out

def _dump_item(item: RawItem) -> dict[str, Any]:
    return item.model_dump() if hasattr(item, "model_dump") else item.__dict__.copy()

def run_real_collection(queries_path: str | Path = "configs/queries.yaml",sources_path: str | Path = "configs/sources.yaml",output_path: str | Path = "data/raw_items.jsonl") -> dict[str, Any]:
    query_config = load_queries(queries_path); source_config = load_sources_config(sources_path)
    stackexchange_cfg = source_config.get("stackexchange", {})
    collectors={"hn_algolia":(bool(source_config.get("hn_algolia",{}).get("enabled",True)),HNAlgoliaCollector(timeout_seconds=int(source_config.get("hn_algolia",{}).get("timeout_seconds",15)))),"gdelt":(bool(source_config.get("gdelt",{}).get("enabled",True)),GDELTCollector(timeout_seconds=int(source_config.get("gdelt",{}).get("timeout_seconds",15)))),"stackexchange":(bool(stackexchange_cfg.get("enabled",True)),StackExchangeCollector(site=str(stackexchange_cfg.get("site","stackoverflow")),sites=stackexchange_cfg.get("sites"),timeout_seconds=int(stackexchange_cfg.get("timeout_seconds",15))))}
    per_source={}; all_items=[]; success_count=0; telemetry=build_base_telemetry()
    for source_name,(enabled,collector) in collectors.items():
        if not enabled:
            per_source[source_name]={"status":"skipped","count":0,"warning":"source disabled"}
            ensure_source(telemetry,source_name)["status"]="skipped"
            continue
        try:
            source_query_config = dict(query_config)
            if source_config.get(source_name, {}).get("include_categories") is not None:
                profiles = dict(source_query_config.get("source_profiles", {}) or {})
                profile = dict(profiles.get(source_name, {}) or {})
                profile["include_categories"] = source_config[source_name].get("include_categories")
                profiles[source_name] = profile
                source_query_config["source_profiles"] = profiles
            records=query_records_for_source(source_query_config,source_name)
            items=collector.collect(queries=[r["query"] for r in records],max_items=int(source_config.get(source_name,{}).get("max_results", source_config.get(source_name,{}).get("max_items",20))))
            for idx,it in enumerate(items):
                rec=records[idx % max(1,len(records))] if records else {"query":it.query,"category":"uncategorized","source_profile":None}
                it.query_category=rec.get("category")
                it.source_profile=rec.get("source_profile")
            success_count+=1
            per_source[source_name]={"status":"ok","count":len(items),"query_count":len(records)}
            if source_name == "stackexchange":
                per_source[source_name]["site_count"] = len(getattr(collector, "sites", [getattr(collector, "site", "stackoverflow")]))
            sb=ensure_source(telemetry,source_name,getattr(collector,"source_type","unknown")); sb["status"]="ok"; sb["query_count"]=len(records); sb["collected_count"]=len(items)
            if source_name == "stackexchange":
                sb["site_count"] = len(getattr(collector, "sites", [getattr(collector, "site", "stackoverflow")]))
                metrics = getattr(collector, "last_query_metrics", {}) if hasattr(collector, "last_query_metrics") else {}
                sb["strict_query_count"] = int(metrics.get("strict_query_count", len(records) * sb["site_count"]))
                sb["fallback_query_count"] = int(metrics.get("fallback_query_count", 0))
                sb["zero_result_query_count"] = int(metrics.get("zero_result_query_count", 0))
                sb["attempted_query_count"] = sb["strict_query_count"] + sb["fallback_query_count"]
                per_site_counts = dict(metrics.get("site_collected_counts", {}) or {})
                sb["site_collected_counts"] = per_site_counts
                if sb["collected_count"] == 0 and sb["attempted_query_count"] > 0:
                    sb["warning"] = "all stackexchange strict+fallback site/query attempts returned zero items"
            for rec in records:
                cb=ensure_category(telemetry,rec.get("category") or "uncategorized"); cb["queries"].add(rec["query"]); cb["sources"].add(source_name)
            for it in items:
                cb=ensure_category(telemetry,it.query_category or "uncategorized"); cb["collected_count"]+=1; cb["sources"].add(source_name)
            all_items.extend(items)
        except Exception as exc:
            per_source[source_name]={"status":"error","count":0,"error":str(exc)}
            sb=ensure_source(telemetry,source_name); sb["status"]="error"; sb["error"]=str(exc)
    deduped=_dedupe_raw_items(all_items)
    for it in deduped:
        ensure_source(telemetry,it.source,it.source_type)["deduped_raw_count"] += 1
        ensure_category(telemetry,it.query_category or "uncategorized")["deduped_raw_count"] += 1
    path=Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
    lines=[json.dumps(_dump_item(i),ensure_ascii=False,sort_keys=True) for i in deduped]; path.write_text("\n".join(lines)+("\n" if lines else ""),encoding="utf-8")
    summary={"sources":per_source,"total_before_dedupe":len(all_items),"total_after_dedupe":len(deduped),"output_path":str(path),"telemetry":finalize_telemetry(telemetry)}
    return summary
