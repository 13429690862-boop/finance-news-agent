"""Configuration helpers for portfolio monitoring."""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
from typing import Any

from agent.finance_models import Holding


DEFAULT_FINANCE_CONFIG: dict[str, Any] = {
    "lookback_days": 7,
    "max_news_per_holding": 12,
    "max_market_news": 20,
    "language": "zh-CN",
    "country": "CN",
    "risk": {
        "high_negative_count": 3,
        "high_negative_score": -5,
        "positive_review_score": 4,
        "max_single_asset_target_weight": 0.25,
    },
    "sources": {
        "google_news_rss": {"enabled": True, "timeout_seconds": 5},
        "gdelt": {"enabled": False, "timeout_seconds": 5},
    },
    "market_queries": [
        "A股 市场 政策 利好 利空",
        "基金 市场 风险 机会",
        "央行 利率 股市 基金",
        "新能源 消费 科技 金融 股市",
    ],
}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if find_spec("yaml") is None:
        raise RuntimeError("PyYAML is required to load finance configuration")
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return loaded


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_finance_config(path: str | Path = "configs/finance.yaml") -> dict[str, Any]:
    cfg = _deep_merge(DEFAULT_FINANCE_CONFIG, _load_yaml(Path(path)))
    if int(cfg.get("lookback_days", 0)) <= 0:
        raise ValueError("finance lookback_days must be positive")
    if int(cfg.get("max_news_per_holding", 0)) <= 0:
        raise ValueError("finance max_news_per_holding must be positive")
    return cfg


def load_portfolio(path: str | Path = "configs/portfolio.yaml") -> list[Holding]:
    loaded = _load_yaml(Path(path))
    rows = loaded.get("holdings", []) if loaded else []
    if not isinstance(rows, list):
        raise ValueError("portfolio holdings must be a list")
    holdings: list[Holding] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"portfolio holding #{index} must be a mapping")
        symbol = str(row.get("symbol", "")).strip()
        name = str(row.get("name", "")).strip()
        if not symbol and not name:
            raise ValueError(f"portfolio holding #{index} must include symbol or name")
        holdings.append(
            Holding(
                symbol=symbol,
                name=name or symbol,
                asset_type=str(row.get("asset_type", "stock") or "stock").strip(),
                market=str(row.get("market", "unknown") or "unknown").strip(),
                quantity=_optional_float(row.get("quantity")),
                cost_basis=_optional_float(row.get("cost_basis")),
                target_weight=_optional_float(row.get("target_weight")),
                notes=str(row.get("notes", "") or "").strip(),
            )
        )
    return holdings


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected a number, got {value!r}") from exc
