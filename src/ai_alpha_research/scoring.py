"""Versioned, auditable scoring primitives for the public research dashboard."""
from __future__ import annotations

from typing import Mapping, Optional


FUNDAMENTAL_SCORE_VERSION = "fundamental_v2"
FUNDAMENTAL_WEIGHTS = {
    "growth": 0.30,
    "acceleration": 0.25,
    "cash_quality": 0.25,
    "expectations": 0.20,
}
MARKET_SCORE_VERSION = "market_v2"
MARKET_WEIGHTS = {"excess_20d": 0.60, "excess_60d": 0.40}
MIN_SCORE_COVERAGE = 0.70
STRONG_FUNDAMENTAL_THRESHOLD = 0.60
STRONG_MARKET_THRESHOLD = 0.50


def weighted_score(
    components: Mapping[str, Optional[float]],
    weights: Mapping[str, float],
) -> dict:
    """Combine 0-1 components without treating missing observations as zero.

    Available weights are re-normalized to one.  Coverage records how much of
    the intended model was observed, so consumers can reject thin scores.
    """
    total_weight = sum(weights.values())
    available = {
        name: value
        for name, value in components.items()
        if name in weights and value is not None
    }
    available_weight = sum(weights[name] for name in available)
    if not available or available_weight <= 0 or total_weight <= 0:
        return {"score": None, "coverage": 0.0, "effective_weights": {}}
    effective = {name: weights[name] / available_weight for name in available}
    return {
        "score": sum(available[name] * effective[name] for name in available),
        "coverage": available_weight / total_weight,
        "effective_weights": effective,
    }


def classify_signal(
    fundamental_score: Optional[float],
    market_score: Optional[float],
    coverage: float,
) -> tuple[str, str]:
    """Map auditable score thresholds to a research setup, not a trade call."""
    if coverage < MIN_SCORE_COVERAGE or fundamental_score is None or market_score is None:
        return "Data gap", "多维基本面或20D/60D市场分数覆盖不足，暂不生成错位信号。"
    if fundamental_score >= STRONG_FUNDAMENTAL_THRESHOLD and market_score < STRONG_MARKET_THRESHOLD:
        return "Fundamental dislocation", "增长、加速、现金流与预期综合得分较强，但20D/60D同层价格表现偏弱。"
    if fundamental_score >= STRONG_FUNDAMENTAL_THRESHOLD and market_score >= STRONG_MARKET_THRESHOLD:
        return "Momentum", "多维基本面得分与20D/60D同层价格表现同时较强。"
    if fundamental_score < STRONG_FUNDAMENTAL_THRESHOLD and market_score >= STRONG_MARKET_THRESHOLD:
        return "Expectation risk", "20D/60D同层价格表现领先，但多维基本面得分尚未达到强势阈值。"
    return "Deteriorating", "多维基本面和20D/60D同层价格表现均偏弱。"
