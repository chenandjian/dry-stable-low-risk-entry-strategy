from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from analyzer.dry_stable import analyze_dry_stable
from scanner.pattern_detector import CupHandleResult, detect_cup_handle
from scanner.scorer import score_cup_handle_advanced

# ── 统一策略窗口配置 ────────────────────────────────────────────────

WINDOW_DEFAULT = 250
WINDOW_MIN = 30


@dataclass(frozen=True)
class StrategyWindows:
    """Frozen, validated strategy window configuration.

    All fields are positive ints >= WINDOW_MIN.
    scan_window_days <= min_listing_days is enforced.
    """
    min_listing_days: int
    scan_window_days: int
    backtest_window_days: int


def resolve_strategy_windows(config: dict) -> StrategyWindows:
    """Parse and validate strategy window config from a raw config dict.

    Rules:
    - Missing values → fixed default 250 (never cascade to min_listing_days).
    - All values must be int >= 30.
    - scan_window_days <= min_listing_days.
    - Never uses ``value or 250`` to avoid swallowing 0.
    """
    data_cfg = config.get("data", {}) if isinstance(config, dict) else {}
    liquidity_cfg = config.get("liquidity", {}) if isinstance(config, dict) else {}

    raw_min = liquidity_cfg.get("min_listing_days")
    raw_scan = data_cfg.get("scan_window_days")
    raw_backtest = data_cfg.get("backtest_window_days")

    def _int_or_default(value, default: int, label: str) -> int:
        if value is None:
            return default
        # RECHECK-002: strict int only — reject bool, float, str
        if type(value) is not int:
            raise ValueError(f"{label} must be an integer, got {type(value).__name__} ({value!r})")
        if value < WINDOW_MIN:
            raise ValueError(f"{label} must be >= {WINDOW_MIN}, got {value}")
        return value

    min_listing_days = _int_or_default(raw_min, WINDOW_DEFAULT, "min_listing_days")
    scan_window_days = _int_or_default(raw_scan, WINDOW_DEFAULT, "scan_window_days")
    backtest_window_days = _int_or_default(raw_backtest, WINDOW_DEFAULT, "backtest_window_days")

    if scan_window_days > min_listing_days:
        raise ValueError(
            f"scan_window_days ({scan_window_days}) must not exceed "
            f"min_listing_days ({min_listing_days})"
        )

    return StrategyWindows(
        min_listing_days=min_listing_days,
        scan_window_days=scan_window_days,
        backtest_window_days=backtest_window_days,
    )


# Single source of truth for which verdict_keys qualify as candidates
CANDIDATE_KEYS = frozenset({"BUY_LOW", "WATCH_BREAKOUT", "WAIT_ENTRY"})
REJECT_KEYS = frozenset({"REJECT", "不建议买入"})
HIGH_DRAWDOWN_LOOKBACK_DAYS = 120
HIGH_DRAWDOWN_HARD_REJECT_PCT = 35.0
HIGH_DRAWDOWN_WEAK_REJECT_PCT = 30.0


@dataclass
class RuleDiagnostic:
    ruleName: str
    requiredValue: str
    actualValue: str
    severity: str
    explanation: str

    def to_dict(self) -> dict:
        return {
            "ruleName": self.ruleName,
            "requiredValue": self.requiredValue,
            "actualValue": self.actualValue,
            "severity": self.severity,
            "explanation": self.explanation,
        }


@dataclass
class StrategyEvaluation:
    passed: bool
    result: CupHandleResult
    dry_stable: dict | None
    strategy_version: str
    config_hash: str
    passed_rules: list[RuleDiagnostic] = field(default_factory=list)
    failed_rules: list[RuleDiagnostic] = field(default_factory=list)
    data: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return serialize_evaluation(self)


@dataclass
class HandleDiagnosis:
    start_date: str
    end_date: str
    passed: bool
    matched_pattern_id: str | None
    passed_rules: list[RuleDiagnostic] = field(default_factory=list)
    failed_rules: list[RuleDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "startDate": self.start_date,
            "endDate": self.end_date,
            "passed": self.passed,
            "matchedPatternId": self.matched_pattern_id,
            "passedRules": [rule.to_dict() for rule in self.passed_rules],
            "failedRules": [rule.to_dict() for rule in self.failed_rules],
        }


def build_pattern_config(config: dict) -> dict:
    cup_cfg = config.get("cup", {})
    handle_cfg = config.get("handle", {})
    breakout_cfg = config.get("breakout", {})
    handle_prefixed = {f"handle_{key}": value for key, value in handle_cfg.items()}
    return {**cup_cfg, **handle_prefixed, **breakout_cfg}


def compute_config_hash(config: dict) -> str:
    canonical = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class CupHandleStrategyEngine:
    strategy_version = "cuphandle-v1"

    def __init__(self, config: dict):
        self.config = config
        self.pattern_cfg = build_pattern_config(config)
        self.scoring_cfg = config.get("scoring", {})
        self.config_hash = compute_config_hash(config)

    def evaluate_at(
        self,
        data_until_date: list[dict],
        *,
        code: str = "",
        name: str = "",
        market_data: list[dict] | None = None,
    ) -> StrategyEvaluation:
        result = detect_cup_handle(data_until_date, self.pattern_cfg)
        result.code = code
        result.name = name

        if result.found:
            result.score = score_cup_handle_advanced(result, data_until_date, self.scoring_cfg)
            dry_stable = analyze_dry_stable(result, data_until_date, market_data=market_data, config=self.config)
            passed_rules, failed_rules = self._candidate_rules(result, dry_stable, data_until_date)
            return StrategyEvaluation(
                not failed_rules, result, dry_stable,
                self.strategy_version, self.config_hash,
                passed_rules, failed_rules, data_until_date,
            )

        # Cup handle not found — try VCP-only
        result.pattern_kind = "vcp"
        dry_stable = analyze_dry_stable(result, data_until_date, market_data=market_data, config=self.config)
        pat20 = dry_stable.get("pattern_score", {}).get("score", 0)
        key_type = dry_stable.get("pattern_score", {}).get("key_pattern_type", "")
        if key_type == "vcp" and pat20 >= 13:
            result.score = min(100, pat20 * 5)
            passed_rules, failed_rules = self._candidate_rules(result, dry_stable, data_until_date)
            return StrategyEvaluation(
                not failed_rules, result, dry_stable,
                self.strategy_version, self.config_hash,
                passed_rules, failed_rules, data_until_date,
            )

        # Neither cup handle nor valid VCP
        failed = diagnose_cup_handle(data_until_date, self.pattern_cfg).failed_rules
        return StrategyEvaluation(
            False, CupHandleResult(found=False, code=code, name=name), dry_stable,
            self.strategy_version, self.config_hash,
            failed_rules=failed, data=data_until_date,
        )

    def diagnose_handle(
        self,
        data_until_handle_end: list[dict],
        handle_start_date: str,
        handle_end_date: str,
        *,
        code: str = "",
        name: str = "",
        market_data: list[dict] | None = None,
    ) -> HandleDiagnosis:
        evaluation = self.evaluate_at(
            data_until_handle_end,
            code=code,
            name=name,
            market_data=market_data,
        )
        passed_rules = list(evaluation.passed_rules)
        failed_rules = list(evaluation.failed_rules)
        matched_pattern_id = None

        if evaluation.result.found:
            actual_start = _handle_start_date(data_until_handle_end, evaluation.result)
            actual_end = data_until_handle_end[-1]["date"] if data_until_handle_end else ""
            if actual_start == handle_start_date and actual_end == handle_end_date:
                passed_rules.append(
                    RuleDiagnostic(
                        "指定柄区间匹配",
                        "用户输入柄区间应与策略识别柄区间一致",
                        f"{actual_start} ~ {actual_end}",
                        "info",
                        "你标注的柄区间与当前杯柄策略识别出的柄部区间一致。",
                    )
                )
                matched_pattern_id = _pattern_id(
                    code,
                    actual_start,
                    actual_end,
                    evaluation.result.handle_low_date,
                )
            else:
                failed_rules.append(
                    RuleDiagnostic(
                        "指定柄区间匹配",
                        "用户输入柄区间应与策略识别柄区间一致",
                        f"策略识别柄区间为 {actual_start} ~ {actual_end}",
                        "high",
                        "你标注的区间没有被当前策略识别为完整杯柄结构中的柄部，因此不能进入策略结果。",
                    )
                )
        else:
            failed_rules.append(
                RuleDiagnostic(
                    "完整杯柄结构",
                    "必须识别到左杯口、杯底、右杯口和有效柄部",
                    "未识别到完整杯柄结构",
                    "high",
                    "截至指定柄结束日，当前策略没有识别到完整杯柄结构。",
                )
            )

        return HandleDiagnosis(
            handle_start_date,
            handle_end_date,
            evaluation.passed and not failed_rules,
            matched_pattern_id,
            passed_rules,
            failed_rules,
        )

    def _candidate_rules(
        self,
        result: CupHandleResult,
        dry_stable: dict | None,
        data_until_date: list[dict] | None = None,
    ) -> tuple[list[RuleDiagnostic], list[RuleDiagnostic]]:
        passed: list[RuleDiagnostic] = []
        failed: list[RuleDiagnostic] = []

        # 突破状态排除：已突破的形态不应再作为候选
        if not result.is_breakout:
            passed.append(
                RuleDiagnostic(
                    "突破状态排除",
                    "形态未被突破",
                    "未突破",
                    "info",
                    "该形态尚未完成突破，属于候选观察。",
                )
            )
        else:
            failed.append(
                RuleDiagnostic(
                    "突破状态排除",
                    "形态未被突破",
                    "已突破",
                    "high",
                    "该形态已完成突破，按规则排除。",
                )
            )

        threshold = self.scoring_cfg.get("medium_threshold", 70) - 10
        if result.score >= threshold:
            passed.append(
                RuleDiagnostic(
                    "形态评分门槛",
                    f">= {threshold}",
                    str(result.score),
                    "info",
                    "形态评分达到当前策略候选门槛。",
                )
            )
        else:
            failed.append(
                RuleDiagnostic(
                    "形态评分门槛",
                    f">= {threshold}",
                    str(result.score),
                    "medium",
                    "形态评分低于当前策略候选门槛。",
                )
            )

        key_pattern_type = dry_stable.get("pattern_score", {}).get("key_pattern_type") if dry_stable else None
        if key_pattern_type in ("cup_handle", "vcp"):
            passed.append(
                RuleDiagnostic(
                    "关键形态类型",
                    "cup_handle / vcp",
                    key_pattern_type,
                    "info",
                    "干稳分析当前仍以杯柄或VCP作为主导形态。",
                )
            )
        else:
            actual_value = str(key_pattern_type) if key_pattern_type is not None else "缺失"
            explanation = (
                "干稳分析缺少 key_pattern_type，不能确认杯柄/VCP仍是主导形态。"
                if key_pattern_type is None
                else "干稳分析当前主导形态不是杯柄/VCP，不能按杯柄/VCP策略结果晋级。"
            )
            failed.append(
                RuleDiagnostic(
                    "关键形态类型",
                    "cup_handle / vcp",
                    actual_value,
                    "high",
                    explanation,
                )
            )

        verdict = dry_stable.get("decision", {}).get("verdict") if dry_stable else None
        verdict_key = dry_stable.get("decision", {}).get("verdict_key", "") if dry_stable else ""
        if verdict_key and verdict_key in CANDIDATE_KEYS:
            passed.append(
                RuleDiagnostic(
                    "最终策略结论",
                    "观察 / 可低吸 / 突破确认",
                    verdict,
                    "info",
                    "干稳低吸决策允许该杯柄结果继续保留为候选。",
                )
            )
        else:
            actual_value = str(verdict or verdict_key) if (verdict or verdict_key) else "缺失"
            if verdict_key in REJECT_KEYS:
                explanation = "干稳低吸决策认为该结构暂不适合买入。"
            elif not verdict_key:
                explanation = "干稳分析缺少最终 verdict，候选结果必须按失败处理。"
            else:
                explanation = "干稳分析返回了未知 verdict，候选结果必须按失败处理。"
            failed.append(
                RuleDiagnostic(
                    "最终策略结论",
                    "非 REJECT / 不建议买入",
                    actual_value,
                    "high",
                    explanation,
                )
            )

        weak_trade_value_rule = _weak_trade_value_rule(dry_stable)
        if weak_trade_value_rule:
            failed.append(weak_trade_value_rule)

        if not _is_vcp_candidate(result, dry_stable):
            high_drawdown_rule = _high_drawdown_weakness_rule(data_until_date or [], dry_stable)
            if high_drawdown_rule:
                failed.append(high_drawdown_rule)

            handle_support_rule = _handle_support_breakdown_rule(result, data_until_date or [])
            if handle_support_rule:
                failed.append(handle_support_rule)

        return passed, failed


def _is_vcp_candidate(result: CupHandleResult, dry_stable: dict | None) -> bool:
    key_pattern_type = dry_stable.get("pattern_score", {}).get("key_pattern_type") if dry_stable else None
    return getattr(result, "pattern_kind", "") == "vcp" or key_pattern_type == "vcp"


def _handle_support_breakdown_rule(
    result: CupHandleResult,
    data_until_date: list[dict],
) -> RuleDiagnostic | None:
    handle_support = float(getattr(result, "handle_low_price", 0) or 0)
    if handle_support <= 0 or len(data_until_date) < 2:
        return None

    closes = [float(row.get("close") or 0) for row in data_until_date]
    latest_close = closes[-1]
    if latest_close <= 0:
        return None

    break_pct = (handle_support - latest_close) / handle_support * 100
    consecutive_break = closes[-1] < handle_support and closes[-2] < handle_support
    hard_break = latest_close < handle_support * 0.98

    if not hard_break and not consecutive_break:
        return None

    reason = (
        "当前收盘价跌破柄部支撑超过2%，柄部结构已失效。"
        if hard_break
        else "连续两日收盘跌破柄部支撑，柄部支撑确认失效。"
    )
    return RuleDiagnostic(
        "柄部支撑破位过滤",
        "当前收盘不低于柄部支撑2%以上，且未连续两日收盘跌破柄部支撑",
        f"handle_support={handle_support:.2f}, latest_close={latest_close:.2f}, break={break_pct:.1f}%",
        "high",
        reason,
    )


def _weak_trade_value_rule(dry_stable: dict | None) -> RuleDiagnostic | None:
    if not dry_stable:
        return None

    rr1 = _number_from_path(dry_stable, "risk_reward", "rr1")
    position_advice = str((dry_stable.get("risk_reward") or {}).get("position_advice") or "")
    reject_reasons = _collect_dry_stable_reject_reasons(dry_stable)

    reasons: list[str] = []
    if position_advice == "0%" and rr1 is not None and rr1 < 1:
        reasons.append(f"仓位建议0%且RR1={rr1:g}<1")
    if any("跌破关键支撑" in reason for reason in reject_reasons):
        reasons.append("已跌破关键支撑")

    if not reasons:
        return None

    actual_parts = []
    actual_parts.append(f"RR1={rr1:g}" if rr1 is not None else "RR1=缺失")
    actual_parts.append(f"仓位建议{position_advice or '缺失'}")
    if reject_reasons:
        actual_parts.append(f"拒绝原因: {'; '.join(reject_reasons)}")

    return RuleDiagnostic(
        "弱交易价值过滤",
        "RR1>=1 且仓位建议非0%，且未跌破关键支撑",
        "；".join(actual_parts),
        "high",
        f"候选虽为观察状态，但当前交易价值过低: {', '.join(reasons)}。",
    )


def _high_drawdown_weakness_rule(
    data_until_date: list[dict],
    dry_stable: dict | None,
) -> RuleDiagnostic | None:
    if not data_until_date or len(data_until_date) < HIGH_DRAWDOWN_LOOKBACK_DAYS:
        return None

    window = data_until_date[-HIGH_DRAWDOWN_LOOKBACK_DAYS:]
    highs = [float(row.get("high") or 0) for row in window]
    recent_high = max(highs) if highs else 0
    latest_close = float(window[-1].get("close") or 0)
    if recent_high <= 0 or latest_close <= 0:
        return None

    drawdown_pct = (recent_high - latest_close) / recent_high * 100
    weakness_reasons = _high_drawdown_weakness_reasons(dry_stable)

    if drawdown_pct >= HIGH_DRAWDOWN_HARD_REJECT_PCT:
        reason = "近120日高点回撤过深，容易把深跌后的局部修复误判为高质量杯柄。"
    elif drawdown_pct >= HIGH_DRAWDOWN_WEAK_REJECT_PCT and weakness_reasons:
        reason = "近120日高点回撤较深，且当前量价/风报状态出现弱势共振。"
    else:
        return None

    if weakness_reasons:
        reason = f"{reason} 弱势特征: {', '.join(weakness_reasons)}。"

    return RuleDiagnostic(
        "高位深跌弱势过滤",
        (
            f"120日高点回撤 < {HIGH_DRAWDOWN_HARD_REJECT_PCT:.0f}%，"
            f"或 < {HIGH_DRAWDOWN_WEAK_REJECT_PCT:.0f}% 且无弱势共振"
        ),
        f"120日高点回撤 {drawdown_pct:.1f}% (high={recent_high:.2f}, close={latest_close:.2f})",
        "high",
        reason,
    )


def _high_drawdown_weakness_reasons(dry_stable: dict | None) -> list[str]:
    if not dry_stable:
        return []

    reasons: list[str] = []
    price_stable_score = _number_from_path(dry_stable, "price_stable", "score")
    if price_stable_score is not None and price_stable_score <= 5:
        reasons.append(f"价稳评分{price_stable_score:g}<=5")

    rr1 = _number_from_path(dry_stable, "risk_reward", "rr1")
    if rr1 is not None and rr1 < 1:
        reasons.append(f"RR1={rr1:g}<1")

    position_advice = str((dry_stable.get("risk_reward") or {}).get("position_advice") or "")
    if position_advice == "0%":
        reasons.append("仓位建议0%")

    warnings = _collect_dry_stable_warnings(dry_stable)
    if any(("弱势阴跌" in warning or "缩量位置偏低" in warning) for warning in warnings):
        reasons.append("存在弱势阴跌/缩量位置偏低警告")

    return reasons


def _number_from_path(source: dict, section: str, key: str) -> float | None:
    value = (source.get(section) or {}).get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_dry_stable_warnings(dry_stable: dict) -> list[str]:
    warnings: list[str] = []
    for section in ("decision", "risk_reward", "volume_dry", "price_stable"):
        section_value = dry_stable.get(section) or {}
        raw = section_value.get("warnings")
        if isinstance(raw, list):
            warnings.extend(str(item) for item in raw)
    raw_top = dry_stable.get("warnings")
    if isinstance(raw_top, list):
        warnings.extend(str(item) for item in raw_top)
    return warnings


def _collect_dry_stable_reject_reasons(dry_stable: dict) -> list[str]:
    reasons: list[str] = []
    for section in ("decision", "risk_reward", "volume_dry", "price_stable"):
        section_value = dry_stable.get(section) or {}
        raw = section_value.get("reject_reasons")
        if isinstance(raw, list):
            reasons.extend(str(item) for item in raw)
    raw_top = dry_stable.get("reject_reasons")
    if isinstance(raw_top, list):
        reasons.extend(str(item) for item in raw_top)
    return reasons


def select_strategy_window(
    data: list[dict],
    window_days: int,
) -> list[dict] | None:
    """截取最近 window_days 个交易日的数据窗口。

    数据不足固定窗口时返回 None，强制调用方显式处理。
    不接受非正整数窗口。
    """
    if window_days <= 0:
        raise ValueError("window_days must be a positive integer")
    if len(data) < window_days:
        return None
    return data[-window_days:]


def select_market_window(
    market_data: list[dict] | None,
    decision_date: str,
) -> list[dict]:
    """Return market rows available on or before the stock decision date.

    All strategy entry points must use this function to prevent
    future market data from leaking into the strategy engine.
    """
    if not market_data:
        return []
    return [
        row for row in market_data
        if row.get("date") and row["date"] <= decision_date
    ]


def diagnose_cup_handle(
    data: list[dict],
    pattern_cfg: dict,
    specified_handle: dict | None = None,
):
    del pattern_cfg, specified_handle
    passed_rules: list[RuleDiagnostic] = []
    failed_rules: list[RuleDiagnostic] = []
    min_len = 120
    actual_len = len(data)

    if actual_len >= min_len:
        passed_rules.append(
            RuleDiagnostic(
                "数据长度",
                f">= {min_len} 根K线",
                f"{actual_len} 根K线",
                "info",
                "K线数量满足杯柄检测的最低要求。",
            )
        )
    else:
        failed_rules.append(
            RuleDiagnostic(
                "数据长度",
                f">= {min_len} 根K线",
                f"{actual_len} 根K线",
                "high",
                "K线数量不足，无法可靠识别杯柄结构。",
            )
        )

    return type(
        "RuleDiagnostics",
        (),
        {"passed_rules": passed_rules, "failed_rules": failed_rules},
    )()


def serialize_evaluation(evaluation: StrategyEvaluation) -> dict:
    result = evaluation.result
    pattern = _serialize_pattern(result, evaluation.data) if result.found else None
    return {
        "passed": evaluation.passed,
        "strategyVersion": evaluation.strategy_version,
        "configHash": evaluation.config_hash,
        "score": result.score,
        "pattern": pattern,
        "dryStable": evaluation.dry_stable,
        "passedRules": [rule.to_dict() for rule in evaluation.passed_rules],
        "failedRules": [rule.to_dict() for rule in evaluation.failed_rules],
    }


def _serialize_pattern(result: CupHandleResult, data: list[dict]) -> dict:
    return {
        "leftHighDate": result.left_high_date,
        "cupLowDate": result.cup_low_date,
        "rightHighDate": result.right_high_date,
        "handleStartDate": _handle_start_date(data, result) if data else "",
        "handleEndDate": data[-1]["date"] if data else "",
        "handleLowDate": result.handle_low_date,
        "cupDepthPct": result.cup_depth_pct,
        "cupDuration": result.cup_duration,
        "handleDepthPct": result.handle_depth_pct,
        "handleDuration": result.handle_duration,
        "lipDeviationPct": result.lip_deviation_pct,
        "isBreakout": result.is_breakout,
        "isVolumeBreakout": result.is_volume_breakout,
        "volMultiplier": result.vol_multiplier,
        "patternKind": result.pattern_kind,
    }


def serialize_pattern_for_backtest(result: CupHandleResult, data: list[dict]) -> dict:
    return _serialize_pattern(result, data)


def _handle_start_date(data: list[dict], result: CupHandleResult) -> str:
    idx = result.right_high_idx + 1
    if 0 <= idx < len(data):
        return data[idx]["date"]
    return ""


def _pattern_id(code: str, handle_start: str, handle_end: str, handle_low: str) -> str:
    return f"{code}-{handle_start}-{handle_end}-{handle_low}"
