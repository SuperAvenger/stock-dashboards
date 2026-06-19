"""Explain technical scores and disclose research-data limitations."""

from __future__ import annotations

import math


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def build_score_assessment(df, current_price: float, market_source: str, fundamental_source: str) -> dict:
    """Return a score with factor-level explanations and confidence metadata."""
    ma10 = float(df["close"].rolling(10).mean().iloc[-1])
    ma30 = float(df["close"].rolling(30).mean().iloc[-1])

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = float((100 - (100 / (1 + rs))).iloc[-1])

    fast = df["close"].ewm(span=12, adjust=False).mean()
    slow = df["close"].ewm(span=26, adjust=False).mean()
    macd = fast - slow
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_value = float(macd.iloc[-1])
    signal_value = float(signal.iloc[-1])

    score = 50
    factors = []
    if current_price > ma10 > ma30:
        trend_impact = 20
        trend_text = "价格位于 10 日与 30 日均线上方，短中期趋势偏强"
    elif current_price < ma10 < ma30:
        trend_impact = -20
        trend_text = "价格位于 10 日与 30 日均线下方，短中期趋势偏弱"
    else:
        trend_impact = 0
        trend_text = "均线关系未形成明确趋势"
    score += trend_impact
    factors.append({"factor": "均线趋势", "impact": trend_impact, "observation": trend_text})

    if rsi < 30:
        rsi_impact = 15
        rsi_text = f"RSI {rsi:.1f}，处于超卖区间"
    elif rsi > 70:
        rsi_impact = -15
        rsi_text = f"RSI {rsi:.1f}，处于超买区间"
    else:
        rsi_impact = 0
        rsi_text = f"RSI {rsi:.1f}，处于中性区间"
    score += rsi_impact
    factors.append({"factor": "RSI", "impact": rsi_impact, "observation": rsi_text})

    macd_impact = 10 if macd_value > signal_value else 0
    score += macd_impact
    factors.append(
        {
            "factor": "MACD",
            "impact": macd_impact,
            "observation": "MACD 位于信号线上方" if macd_impact else "MACD 未高于信号线",
        }
    )

    risk_flags = []
    if market_source != "longport":
        risk_flags.append("simulated_market_data")
    if fundamental_source != "longport":
        risk_flags.append("simulated_fundamentals")
    if len(df) < 120:
        risk_flags.append("limited_price_history")
    if not all(_finite(value) for value in (ma10, ma30, rsi, macd_value, signal_value)):
        risk_flags.append("invalid_indicator_value")

    confidence = "high" if not risk_flags else "medium" if len(risk_flags) == 1 else "low"
    return {
        "score": max(0, min(100, score)),
        "factors": factors,
        "confidence": confidence,
        "risk_flags": risk_flags,
        "sources": {"market": market_source, "fundamentals": fundamental_source},
    }


def research_priority(score: float) -> str:
    if score >= 70:
        return "重点研究"
    if score >= 50:
        return "持续观察"
    return "谨慎跟踪"
