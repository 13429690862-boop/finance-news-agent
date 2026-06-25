from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf


@dataclass
class TechnicalSignal:
    symbol: str
    name: str
    yahoo_symbol: str
    last_close: float | None
    change_5d: float | None
    change_20d: float | None
    ma5: float | None
    ma20: float | None
    ma60: float | None
    volatility_20d: float | None
    trend: str
    risk_level: str
    support: float | None
    resistance: float | None
    analyst_view: str


def to_yahoo_symbol(symbol: str, market: str) -> str:
    symbol = str(symbol).strip()

    if market == "CN-A":
        if symbol.startswith(("6", "9")):
            return f"{symbol}.SS"
        return f"{symbol}.SZ"

    if market == "CN-ETF":
        if symbol.startswith(("5", "6")):
            return f"{symbol}.SS"
        return f"{symbol}.SZ"

    if market == "HK":
        return f"{symbol.zfill(4)}.HK"

    if market == "US":
        return symbol.upper()

    return symbol


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _pct_change(series: pd.Series, days: int) -> float | None:
    if len(series) <= days:
        return None

    latest = series.iloc[-1]
    previous = series.iloc[-days - 1]

    if previous == 0:
        return None

    return float((latest / previous - 1) * 100)


def analyze_holding_technical(
    *,
    symbol: str,
    name: str,
    market: str,
    asset_type: str,
    period: str = "6mo",
) -> TechnicalSignal:
    yahoo_symbol = to_yahoo_symbol(symbol, market)

    try:
        data = yf.download(
            yahoo_symbol,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
    except Exception:
        data = pd.DataFrame()

    if data.empty or "Close" not in data.columns:
        return TechnicalSignal(
            symbol=symbol,
            name=name,
            yahoo_symbol=yahoo_symbol,
            last_close=None,
            change_5d=None,
            change_20d=None,
            ma5=None,
            ma20=None,
            ma60=None,
            volatility_20d=None,
            trend="unknown",
            risk_level="unknown",
            support=None,
            resistance=None,
            analyst_view="未能获取有效历史行情，暂不做技术面判断。建议检查代码、市场类型或数据源可用性。",
        )

    close = data["Close"].dropna()

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    last_close = _safe_float(close.iloc[-1])
    last_ma5 = _safe_float(ma5.iloc[-1])
    last_ma20 = _safe_float(ma20.iloc[-1])
    last_ma60 = _safe_float(ma60.iloc[-1])

    change_5d = _pct_change(close, 5)
    change_20d = _pct_change(close, 20)

    daily_returns = close.pct_change().dropna()
    volatility_20d = None
    if len(daily_returns) >= 20:
        volatility_20d = float(daily_returns.tail(20).std() * 100)

    recent_window = close.tail(20)
    support = _safe_float(recent_window.min())
    resistance = _safe_float(recent_window.max())

    trend = "neutral"
    risk_level = "medium"
    advice_parts: list[str] = []

    if last_close and last_ma5 and last_ma20 and last_ma60:
        if last_close > last_ma5 > last_ma20 > last_ma60:
            trend = "strong_uptrend"
            advice_parts.append(
                "价格位于 5 日、20 日、60 日均线上方，且短中期均线呈多头排列，技术面偏强。"
            )
        elif last_close > last_ma20 and last_ma20 > last_ma60:
            trend = "uptrend"
            advice_parts.append(
                "价格位于 20 日均线上方，中期趋势相对健康，但仍需观察成交量和回撤幅度。"
            )
        elif last_close < last_ma5 < last_ma20:
            trend = "downtrend"
            advice_parts.append(
                "价格跌破短中期均线，短线走势偏弱，暂不适合激进加仓。"
            )
        elif last_close < last_ma60:
            trend = "weak"
            advice_parts.append(
                "价格处于 60 日均线下方，中期趋势偏弱，应优先控制仓位风险。"
            )
        else:
            trend = "neutral"
            advice_parts.append(
                "价格处于均线交织区域，趋势信号不明确，更适合等待方向选择。"
            )

    if change_20d is not None:
        if change_20d >= 15:
            risk_level = "high"
            advice_parts.append(
                "近 20 个交易日涨幅较大，短线追高风险上升，建议避免一次性加仓。"
            )
        elif change_20d <= -15:
            risk_level = "high"
            advice_parts.append(
                "近 20 个交易日跌幅较大，说明波动风险较高，应等待企稳信号再评估。"
            )
        elif abs(change_20d) <= 5:
            risk_level = "low"
            advice_parts.append(
                "近 20 个交易日波动相对温和，适合按原计划观察或执行再平衡。"
            )

    if volatility_20d is not None:
        if volatility_20d >= 3:
            risk_level = "high"
            advice_parts.append(
                "近 20 日波动率偏高，仓位管理应更保守。"
            )
        elif volatility_20d <= 1:
            advice_parts.append(
                "近 20 日波动率相对较低，短线风险释放较平稳。"
            )

    if support and resistance and last_close:
        advice_parts.append(
            f"近 20 日参考支撑位约 {support:.2f}，压力位约 {resistance:.2f}。"
        )

        if last_close >= resistance * 0.98:
            advice_parts.append(
                "当前价格接近短期压力区，若没有成交量和基本面配合，不宜盲目追高。"
            )
        elif last_close <= support * 1.02:
            advice_parts.append(
                "当前价格接近短期支撑区，可重点观察是否企稳，但跌破支撑需重新评估风险。"
            )

    if asset_type == "stock":
        advice_parts.append(
            "个股波动通常高于宽基基金，建议设置单票仓位上限，并用分批方式执行。"
        )
    elif asset_type == "fund":
        advice_parts.append(
            "基金或 ETF 更适合结合趋势、估值和组合配置做再平衡，不建议频繁短线交易。"
        )

    analyst_view = " ".join(advice_parts) if advice_parts else "技术面信号不足，建议继续观察。"

    return TechnicalSignal(
        symbol=symbol,
        name=name,
        yahoo_symbol=yahoo_symbol,
        last_close=last_close,
        change_5d=change_5d,
        change_20d=change_20d,
        ma5=last_ma5,
        ma20=last_ma20,
        ma60=last_ma60,
        volatility_20d=volatility_20d,
        trend=trend,
        risk_level=risk_level,
        support=support,
        resistance=resistance,
        analyst_view=analyst_view,
    )
