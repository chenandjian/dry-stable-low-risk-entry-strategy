from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from analyzer.dry_stable import analyze_dry_stable
from scanner.pattern_detector import CupHandleResult, detect_cup_handle
from scanner.scorer import score_cup_handle_advanced


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
        if not result.found:
            failed = diagnose_cup_handle(data_until_date, self.pattern_cfg).failed_rules
            return StrategyEvaluation(
                False,
                CupHandleResult(found=False, code=code, name=name),
                None,
                self.strategy_version,
                self.config_hash,
                failed_rules=failed,
                data=data_until_date,
            )

        result.code = code
        result.name = name
        result.score = score_cup_handle_advanced(
            result,
            data_until_date,
            self.scoring_cfg,
        )
        dry_stable = analyze_dry_stable(result, data_until_date, market_data=market_data, config=self.config)
        passed_rules, failed_rules = self._candidate_rules(result, dry_stable)
        return StrategyEvaluation(
            not failed_rules,
            result,
            dry_stable,
            self.strategy_version,
            self.config_hash,
            passed_rules,
            failed_rules,
            data_until_date,
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
    ) -> tuple[list[RuleDiagnostic], list[RuleDiagnostic]]:
        passed: list[RuleDiagnostic] = []
        failed: list[RuleDiagnostic] = []
        threshold = self.scoring_cfg.get("medium_threshold", 70) - 10
        reject_keys = {"REJECT", "不建议买入"}
        candidate_keys = {"BUY_LOW", "WATCH_BREAKOUT", "WAIT_ENTRY"}

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
        if verdict_key and verdict_key in candidate_keys:
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
            if verdict_key in reject_keys:
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

        return passed, failed


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
