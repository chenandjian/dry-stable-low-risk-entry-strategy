"""Strategy4 single-leader evaluation entry point."""
from __future__ import annotations

from strategy4.config import resolve_strategy4_config
from strategy4.first_wave import evaluate_first_wave
from strategy4.pullback import evaluate_pullback
from strategy4.risk_reward import evaluate_risk_reward
from strategy4.second_wave import evaluate_second_wave


class HotLeaderSecondWaveEngine:
    """Evaluate a confirmed hot-topic leader for Strategy4 second-wave quality."""

    def __init__(self, config: dict | None = None):
        self.config = resolve_strategy4_config(config or {})

    def evaluate_at(
        self,
        data: list[dict],
        *,
        code: str,
        name: str = "",
        leader_context: dict | None = None,
    ) -> dict:
        leader_context = leader_context or {}
        first_wave = evaluate_first_wave(data, self.config)
        pullback = evaluate_pullback(data, self.config) if first_wave.passed else None
        second_wave = evaluate_second_wave(data) if pullback and pullback.passed else None
        close = float(data[-1]["close"]) if data else 0.0
        support = float(leader_context.get("support_price") or close * 0.92)
        target = float(leader_context.get("target_price") or close * 1.25)
        rr = evaluate_risk_reward(
            current_close=close,
            support_price=support,
            target_price=target,
            config=self.config,
            is_core_leader=bool(leader_context.get("is_core_leader")),
        ) if close > 0 else None

        passed = bool(first_wave.passed and pullback and pullback.passed and second_wave and second_wave.passed and rr and rr.passed)
        return {
            "passed": passed,
            "code": code,
            "name": name,
            "status": "BUYABLE_SECOND_WAVE" if passed else "HOT_TOPIC_NO_BUY_POINT",
            "first_wave": first_wave,
            "pullback": pullback,
            "second_wave": second_wave,
            "risk_reward": rr,
        }
