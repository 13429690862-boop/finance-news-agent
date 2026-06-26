from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from agent.finance_config import load_portfolio


CN_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class SessionSignal:
    symbol: str
    name: str
    market: str
    asset_type: str
    yahoo_symbol: str
    last_close: float | None
    change_5d: float | None
    change_20d: float | None
    ma5: float | None
    ma20: float | None
    ma60: float | None
    support_20d: float | None
    resistance_20d: float | None
    volatility_20d: float | None
    trend: str
    risk_level: str
    session_view: str


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


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "无数据"
    return f"{value:.2f}"


def _fmt_percent(value: float | None) -> str:
    if value is None:
        return "无数据"
    return f"{value:.2f}%"


def _pct_change(series: pd.Series, days: int) -> float | None:
    if len(series) <= days:
        return None

    latest = series.iloc[-1]
    previous = series.iloc[-days - 1]

    if previous == 0:
        return None

    return float((latest / previous - 1) * 100)


def _build_trend_view(
    *,
    last_close: float | None,
    ma5: float | None,
    ma20: float | None,
    ma60: float | None,
    change_20d: float | None,
    volatility_20d: float | None,
    support: float | None,
    resistance: float | None,
    asset_type: str,
    session: str,
) -> tuple[str, str, str]:
    trend = "unknown"
    risk_level = "medium"
    parts: list[str] = []

    if last_close is None:
        return (
            "unknown",
            "unknown",
            "未能获取有效行情数据，本标的盘面分析标注为 [UNSOURCED]。建议检查股票代码、市场类型或行情源可用性。",
        )

    if ma5 and ma20 and ma60:
        if last_close > ma5 > ma20 > ma60:
            trend = "strong_uptrend"
            parts.append(
                "价格站在5日、20日、60日均线上方，且均线呈多头排列，说明短中期趋势偏强。"
            )
        elif last_close > ma20 and ma20 > ma60:
            trend = "uptrend"
            parts.append(
                "价格位于20日均线上方，中期趋势尚未破坏。通俗理解：当前价格仍高于近一个月平均成本。"
            )
        elif last_close < ma5 < ma20:
            trend = "downtrend"
            risk_level = "high"
            parts.append(
                "价格跌破短期均线，且短线均线向下，说明短线走势偏弱。"
            )
        elif last_close < ma60:
            trend = "weak"
            risk_level = "high"
            parts.append(
                "价格在60日均线下方，中期走势偏弱，优先考虑风险控制。"
            )
        else:
            trend = "neutral"
            parts.append(
                "价格处在均线交织区，说明市场方向暂不明确，适合等待突破或跌破后的确认信号。"
            )
    else:
        parts.append("均线数据不足，趋势判断置信度较低。[UNSOURCED]")

    if change_20d is not None:
        if change_20d >= 15:
            risk_level = "high"
            parts.append(
                f"近20个交易日涨幅约{change_20d:.2f}%，短线涨幅偏大，追高风险上升。"
            )
        elif change_20d <= -15:
            risk_level = "high"
            parts.append(
                f"近20个交易日跌幅约{change_20d:.2f}%，说明近期波动和回撤压力较大。"
            )
        elif abs(change_20d) <= 5:
            if risk_level != "high":
                risk_level = "low"
            parts.append(
                f"近20个交易日涨跌幅约{change_20d:.2f}%，波动相对温和。"
            )

    if volatility_20d is not None:
        if volatility_20d >= 3:
            risk_level = "high"
            parts.append(
                f"近20日波动率约{volatility_20d:.2f}%，波动偏高，仓位管理应更保守。"
            )
        elif volatility_20d <= 1:
            parts.append(
                f"近20日波动率约{volatility_20d:.2f}%，短期波动相对可控。"
            )

    if support and resistance:
        parts.append(
            f"近20日参考支撑位约{support:.2f}，压力位约{resistance:.2f}。"
        )

        if last_close <= support * 1.02:
            parts.append(
                "当前价格接近短期支撑区。通俗理解：这里可能有资金尝试承接，但如果跌破支撑，需要重新评估风险。"
            )
        elif last_close >= resistance * 0.98:
            parts.append(
                "当前价格接近短期压力区。通俗理解：这里容易出现获利盘兑现，除非放量突破，否则不建议盲目追高。"
            )

    if session == "open":
        parts.append(
            "盘前策略：不预测必涨必跌，只制定观察条件。开盘若高开接近压力位，不宜直接追；若低开接近支撑位，先看是否企稳。"
        )
    elif session == "intraday":
        parts.append(
            "盘中策略：重点观察是否突破压力位、跌破支撑位，以及是否明显强于大盘。若没有量能和趋势确认，不建议盘中情绪化操作。"
        )
    elif session == "close":
        parts.append(
            "盘尾策略：重点看收盘是否站上关键均线、是否守住支撑位，以及全天走势是放量上攻还是冲高回落。"
        )

    if asset_type == "stock":
        parts.append(
            "个股波动通常高于宽基基金，建议控制单票仓位，避免因单日涨跌大幅改变计划。"
        )
    elif asset_type == "fund":
        parts.append(
            "基金/ETF更适合结合趋势、估值和组合配置做再平衡，不建议过度短线交易。"
        )

    return trend, risk_level, "".join(parts)


def analyze_one_holding(holding: Any, session: str) -> SessionSignal:
    symbol = str(getattr(holding, "symbol", "")).strip()
    name = str(getattr(holding, "name", symbol)).strip()
    market = str(getattr(holding, "market", "")).strip()
    asset_type = str(getattr(holding, "asset_type", "")).strip()

    yahoo_symbol = to_yahoo_symbol(symbol, market)

    try:
        data = yf.download(
            yahoo_symbol,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
    except Exception:
        data = pd.DataFrame()

    if data.empty or "Close" not in data.columns:
        return SessionSignal(
            symbol=symbol,
            name=name,
            market=market,
            asset_type=asset_type,
            yahoo_symbol=yahoo_symbol,
            last_close=None,
            change_5d=None,
            change_20d=None,
            ma5=None,
            ma20=None,
            ma60=None,
            support_20d=None,
            resistance_20d=None,
            volatility_20d=None,
            trend="unknown",
            risk_level="unknown",
            session_view="未能获取有效行情数据，盘面分析标注为 [UNSOURCED]。不建议在数据缺失时给出强结论。",
        )

    close = data["Close"].dropna()

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    ma5_series = close.rolling(5).mean()
    ma20_series = close.rolling(20).mean()
    ma60_series = close.rolling(60).mean()

    last_close = _safe_float(close.iloc[-1])
    ma5 = _safe_float(ma5_series.iloc[-1])
    ma20 = _safe_float(ma20_series.iloc[-1])
    ma60 = _safe_float(ma60_series.iloc[-1])

    change_5d = _pct_change(close, 5)
    change_20d = _pct_change(close, 20)

    recent_20 = close.tail(20)
    support_20d = _safe_float(recent_20.min())
    resistance_20d = _safe_float(recent_20.max())

    daily_returns = close.pct_change().dropna()
    volatility_20d = None
    if len(daily_returns) >= 20:
        volatility_20d = float(daily_returns.tail(20).std() * 100)

    trend, risk_level, session_view = _build_trend_view(
        last_close=last_close,
        ma5=ma5,
        ma20=ma20,
        ma60=ma60,
        change_20d=change_20d,
        volatility_20d=volatility_20d,
        support=support_20d,
        resistance=resistance_20d,
        asset_type=asset_type,
        session=session,
    )

    return SessionSignal(
        symbol=symbol,
        name=name,
        market=market,
        asset_type=asset_type,
        yahoo_symbol=yahoo_symbol,
        last_close=last_close,
        change_5d=change_5d,
        change_20d=change_20d,
        ma5=ma5,
        ma20=ma20,
        ma60=ma60,
        support_20d=support_20d,
        resistance_20d=resistance_20d,
        volatility_20d=volatility_20d,
        trend=trend,
        risk_level=risk_level,
        session_view=session_view,
    )


def infer_session(now: datetime | None = None) -> str:
    now = now or datetime.now(CN_TZ)
    hour = now.hour
    minute = now.minute

    current_minutes = hour * 60 + minute

    if current_minutes < 9 * 60 + 30:
        return "open"

    if current_minutes < 15 * 60:
        return "intraday"

    return "close"


def session_title(session: str) -> str:
    if session == "open":
        return "盘前分析"
    if session == "intraday":
        return "盘中分析"
    if session == "close":
        return "盘尾复盘"
    return "盘面分析"


def build_report(session: str, signals: list[SessionSignal]) -> str:
    now = datetime.now(CN_TZ).replace(microsecond=0)

    lines: list[str] = [
        f"# {session_title(session)}报告",
        "",
        f"- 生成时间：{now.isoformat()}",
        "- 角色设定：你是一位经验丰富的理财顾问/基金分析师，需要用通俗语言解释专业概念。",
        "- 反幻觉规则：趋势必须量化；没有可靠数据时标注 [UNSOURCED]；本报告不构成收益承诺或强制买卖指令。",
        "",
        "## 总览",
        "",
        "| 标的 | 市场 | 最新收盘 | 5日涨跌幅 | 20日涨跌幅 | 趋势 | 风险 |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]

    for signal in signals:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{signal.name}（{signal.symbol}）",
                    signal.market,
                    _fmt_number(signal.last_close),
                    _fmt_percent(signal.change_5d),
                    _fmt_percent(signal.change_20d),
                    signal.trend,
                    signal.risk_level,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 逐项分析",
            "",
        ]
    )

    for signal in signals:
        lines.extend(
            [
                f"### {signal.name}（{signal.symbol}）",
                "",
                f"- 数据代码：{signal.yahoo_symbol}",
                f"- 最新收盘价：{_fmt_number(signal.last_close)}",
                f"- MA5 / MA20 / MA60：{_fmt_number(signal.ma5)} / {_fmt_number(signal.ma20)} / {_fmt_number(signal.ma60)}",
                f"- 近20日支撑位 / 压力位：{_fmt_number(signal.support_20d)} / {_fmt_number(signal.resistance_20d)}",
                f"- 近20日波动率：{_fmt_percent(signal.volatility_20d)}",
                f"- 趋势判断：{signal.trend}",
                f"- 风险等级：{signal.risk_level}",
                f"- 分析师视角：{signal.session_view}",
                "",
            ]
        )

    lines.extend(
        [
            "## 风险提示",
            "",
            "- 行情数据来自自动化数据源，可能存在延迟或缺失。",
            "- 盘前、盘中、盘尾分析只用于辅助复盘和观察，不构成直接买卖建议。",
            "- 如果行情、公告、新闻之间出现矛盾，应优先以交易所公告、基金公司公告和券商交易软件实时行情为准。",
        ]
    )

    return "\n".join(lines)


def write_report(report_text: str, session: str) -> Path:
    output_dir = Path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / f"market-{session}-report.md"
    path.write_text(report_text, encoding="utf-8")

    latest_path = output_dir / "market-session-report.md"
    latest_path.write_text(report_text, encoding="utf-8")

    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--session",
        choices=["auto", "open", "intraday", "close"],
        default="auto",
    )
    parser.add_argument(
        "--portfolio",
        default="configs/portfolio.yaml",
    )
    args = parser.parse_args()

    session = infer_session() if args.session == "auto" else args.session

    holdings = load_portfolio(args.portfolio)
    signals = [analyze_one_holding(holding, session) for holding in holdings]

    report_text = build_report(session, signals)
    report_path = write_report(report_text, session)

    print(f"session={session}")
    print(f"report_path={report_path}")


if __name__ == "__main__":
    main()
