"""Complete price-cycle detection shared by Strategy6 VCP callers."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VcpRound:
    peak_index: int
    low_index: int
    recovery_peak_index: int
    peak_date: str
    low_date: str
    recovery_peak_date: str
    peak_close: float
    low_close: float
    recovery_peak_close: float
    amplitude: float
    rebound: float
    decline_avg_volume: float
    rebound_avg_volume: float
    breakout_confirmed: bool = False

    @property
    def pivot_close(self) -> float:
        return self.peak_close if self.breakout_confirmed else self.recovery_peak_close

    @property
    def pivot_date(self) -> str:
        return self.peak_date if self.breakout_confirmed else self.recovery_peak_date


@dataclass(frozen=True)
class VcpFormingRound:
    peak_index: int
    low_index: int
    recovery_peak_index: int | None
    peak_date: str
    low_date: str
    recovery_peak_date: str
    peak_close: float
    low_close: float
    recovery_peak_close: float
    amplitude: float
    rebound: float
    decline_avg_volume: float
    rebound_avg_volume: float
    phase: str


@dataclass
class VcpRoundDetection:
    completed_rounds: list[VcpRound] = field(default_factory=list)
    forming_round: VcpFormingRound | None = None
    risk_tags: list[str] = field(default_factory=list)

    @property
    def confirmed(self) -> bool:
        return len(self.completed_rounds) >= 2

    @property
    def early_observation(self) -> bool:
        return len(self.completed_rounds) == 1 and self.forming_round is not None


def detect_vcp_rounds(rows: list[dict], config: dict) -> VcpRoundDetection:
    """Return the strongest complete VCP chain visible in ``rows``.

    A complete round is peak -> final low -> confirmed recovery peak. Local
    bounces that do not meet the recovery floor are skipped, allowing a later
    lower low to remain part of the same decline.
    """
    if len(rows) < 5:
        return VcpRoundDetection()

    best = VcpRoundDetection()
    for start in _local_peak_indexes(rows):
        candidate = _build_chain(rows, start, config)
        if _detection_rank(candidate) > _detection_rank(best):
            best = candidate
    return best


def _build_chain(rows: list[dict], start: int, config: dict) -> VcpRoundDetection:
    completed: list[VcpRound] = []
    peak_index = start
    while True:
        round_ = _find_next_round(
            rows,
            peak_index,
            config,
            previous=completed[-1] if completed else None,
        )
        if round_ is None:
            break
        completed.append(round_)
        peak_index = round_.recovery_peak_index
        if round_.breakout_confirmed:
            break

    forming = None
    if completed and not completed[-1].breakout_confirmed:
        forming = _forming_round(rows, peak_index)
    risks = _chain_risks(completed, config)
    return VcpRoundDetection(
        completed_rounds=completed,
        forming_round=forming,
        risk_tags=risks,
    )


def _find_next_round(
    rows: list[dict],
    peak_index: int,
    config: dict,
    *,
    previous: VcpRound | None,
) -> VcpRound | None:
    closes = [_number(row, "close") for row in rows]
    peak_close = closes[peak_index]
    if peak_close <= 0:
        return None

    rebound_floor = float(config.get("vcp_rebound_min_pct", 0.03))
    confirm_days = int(config.get("vcp_rebound_confirm_days", 2))
    for recovery_index in range(peak_index + 2, len(rows)):
        low_index = min(
            range(peak_index + 1, recovery_index),
            key=lambda index: closes[index],
        )
        low_close = closes[low_index]
        if low_close <= 0 or low_close >= peak_close:
            continue
        recovery_close = closes[recovery_index]
        rebound = recovery_close / low_close - 1.0
        direct_breakout = (
            recovery_close > peak_close
            and _breakout_confirmed(rows, recovery_index)
        )
        ordinary_recovery = (
            rebound >= rebound_floor
            and _is_local_peak(rows, recovery_index)
            and _ordinary_recovery_confirmed(
                rows,
                low_index=low_index,
                recovery_index=recovery_index,
                confirm_days=confirm_days,
            )
        )
        if not (direct_breakout or ordinary_recovery):
            continue

        round_ = _make_round(
            rows,
            peak_index,
            low_index,
            recovery_index,
            breakout_confirmed=direct_breakout,
        )
        if _round_allowed(round_, previous, config):
            return round_
    return None


def _round_allowed(
    round_: VcpRound,
    previous: VcpRound | None,
    config: dict,
) -> bool:
    if previous is None:
        return (
            float(config.get("vcp_min_first_range", 0.08))
            <= round_.amplitude
            <= float(config.get("vcp_first_contraction_max_range", 0.32))
        )
    return (
        round_.amplitude
        < previous.amplitude * float(config.get("vcp_contraction_range_ratio", 0.90))
        and round_.decline_avg_volume
        < previous.decline_avg_volume * float(config.get("vcp_contraction_volume_ratio", 0.90))
        and round_.low_close >= previous.low_close * 0.97
    )


def _ordinary_recovery_confirmed(
    rows: list[dict],
    *,
    low_index: int,
    recovery_index: int,
    confirm_days: int,
) -> bool:
    confirmation_index = max(recovery_index, low_index + confirm_days)
    if recovery_index + 1 >= len(rows) or confirmation_index >= len(rows):
        return False
    low_close = _number(rows[low_index], "close")
    return all(
        _number(rows[index], "close") >= low_close
        for index in range(low_index + 1, confirmation_index + 1)
    )


def _breakout_confirmed(rows: list[dict], index: int) -> bool:
    if index < 1:
        return False
    previous_close = _number(rows[index - 1], "close")
    close = _number(rows[index], "close")
    daily_return = close / previous_close - 1.0 if previous_close > 0 else 0.0
    return daily_return >= 0.05 or _volume_ratio_against_prior(rows, index) >= 1.20


def _volume_ratio_against_prior(rows: list[dict], index: int) -> float:
    prior = [
        _number(row, "volume")
        for row in rows[max(0, index - 20):index]
        if _number(row, "volume") > 0
    ]
    average = sum(prior) / len(prior) if prior else 0.0
    return _number(rows[index], "volume") / average if average > 0 else 0.0


def _make_round(
    rows: list[dict],
    peak_index: int,
    low_index: int,
    recovery_index: int,
    *,
    breakout_confirmed: bool,
) -> VcpRound:
    peak_close = _number(rows[peak_index], "close")
    low_close = _number(rows[low_index], "close")
    recovery_close = _number(rows[recovery_index], "close")
    return VcpRound(
        peak_index=peak_index,
        low_index=low_index,
        recovery_peak_index=recovery_index,
        peak_date=_date(rows[peak_index]),
        low_date=_date(rows[low_index]),
        recovery_peak_date=_date(rows[recovery_index]),
        peak_close=peak_close,
        low_close=low_close,
        recovery_peak_close=recovery_close,
        amplitude=(peak_close - low_close) / peak_close,
        rebound=recovery_close / low_close - 1.0,
        decline_avg_volume=_mean_volume(rows[peak_index + 1:low_index + 1]),
        rebound_avg_volume=_mean_volume(rows[low_index + 1:recovery_index + 1]),
        breakout_confirmed=breakout_confirmed,
    )


def _forming_round(rows: list[dict], peak_index: int) -> VcpFormingRound | None:
    if peak_index + 1 >= len(rows):
        return None
    closes = [_number(row, "close") for row in rows]
    low_index = min(range(peak_index + 1, len(rows)), key=lambda index: closes[index])
    peak_close = closes[peak_index]
    low_close = closes[low_index]
    if peak_close <= 0 or low_close >= peak_close:
        return None
    recovery_index = None
    if low_index + 1 < len(rows):
        recovery_index = max(
            range(low_index + 1, len(rows)),
            key=lambda index: closes[index],
        )
    recovery_close = closes[recovery_index] if recovery_index is not None else 0.0
    return VcpFormingRound(
        peak_index=peak_index,
        low_index=low_index,
        recovery_peak_index=recovery_index,
        peak_date=_date(rows[peak_index]),
        low_date=_date(rows[low_index]),
        recovery_peak_date=_date(rows[recovery_index]) if recovery_index is not None else "",
        peak_close=peak_close,
        low_close=low_close,
        recovery_peak_close=recovery_close,
        amplitude=(peak_close - low_close) / peak_close,
        rebound=recovery_close / low_close - 1.0 if recovery_close > 0 and low_close > 0 else 0.0,
        decline_avg_volume=_mean_volume(rows[peak_index + 1:low_index + 1]),
        rebound_avg_volume=_mean_volume(rows[low_index + 1:(recovery_index + 1) if recovery_index is not None else low_index + 1]),
        phase="REBOUNDING" if recovery_index is not None else "DECLINING",
    )


def _chain_risks(rounds: list[VcpRound], config: dict) -> list[str]:
    warning_ratio = float(config.get("vcp_low_warning_ratio", 0.99))
    risks: list[str] = []
    for previous, current in zip(rounds, rounds[1:]):
        if current.low_close < previous.low_close * warning_ratio:
            risks.append("VCP_LOW_SLIGHTLY_LOWER")
    if rounds and rounds[-1].amplitude < 0.01:
        risks.append("VCP_MICRO_CONTRACTION_NOISE")
    return list(dict.fromkeys(risks))


def _local_peak_indexes(rows: list[dict]) -> list[int]:
    return [index for index in range(1, len(rows) - 1) if _is_local_peak(rows, index)]


def _is_local_peak(rows: list[dict], index: int) -> bool:
    if index <= 0 or index + 1 >= len(rows):
        return False
    close = _number(rows[index], "close")
    return (
        close >= _number(rows[index - 1], "close")
        and close > _number(rows[index + 1], "close")
    )


def _detection_rank(result: VcpRoundDetection) -> tuple[int, int, int, int]:
    last_index = result.completed_rounds[-1].recovery_peak_index if result.completed_rounds else -1
    first_index = result.completed_rounds[0].peak_index if result.completed_rounds else -1
    return len(result.completed_rounds), int(result.confirmed), last_index, first_index


def _mean_volume(rows: list[dict]) -> float:
    volumes = [_number(row, "volume") for row in rows if _number(row, "volume") > 0]
    return sum(volumes) / len(volumes) if volumes else 0.0


def _number(row: dict, key: str) -> float:
    return float(row.get(key) or 0.0)


def _date(row: dict) -> str:
    return str(row.get("date") or row.get("trade_date") or "")
