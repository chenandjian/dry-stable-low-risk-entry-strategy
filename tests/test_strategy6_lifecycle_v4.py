import scanner.db as db
from types import SimpleNamespace

from strategy6.scanner import _strategy6_event_key


def _update(
    code,
    evaluation_date,
    candidate_type="KEY_CANDIDATE",
    event_key="start-a|pattern-a",
    decision_profile="formal_original",
):
    return db.update_strategy6_lifecycle(
        code=code,
        evaluation_date=evaluation_date,
        candidate_type=candidate_type,
        lifecycle_status="READY",
        event_key=event_key,
        reject_reasons=[] if candidate_type != "REJECTED" else ["SUPPORT_FAILED"],
        max_watch_days=10,
        expired_cooldown_days=5,
        failed_cooldown_days=10,
        decision_profile=decision_profile,
    )


def test_lifecycle_resets_when_decision_profile_changes(tmp_path):
    db.init_db(str(tmp_path / "profile-reset.db"))
    _update(
        "000001",
        "2026-07-01",
        decision_profile="research_quality_v2",
    )

    formal = _update(
        "000001",
        "2026-07-15",
        decision_profile="formal_original",
    )

    assert formal["decision_profile"] == "formal_original"
    assert formal["first_seen_date"] == "2026-07-15"
    assert formal["days_in_pool"] == 0
    assert formal["blocked"] is False


def test_candidate_expires_after_ten_trading_days_and_enters_cooldown(tmp_path):
    db.init_db(str(tmp_path / "lifecycle.db"))

    first = _update("000001", "2026-07-01")
    expired = _update("000001", "2026-07-15")

    assert first["first_seen_date"] == "2026-07-01"
    assert expired["days_in_pool"] == 10
    assert expired["lifecycle_status"] == "EXPIRED"
    assert expired["blocked"] is True
    assert expired["exit_reason"] == "MAX_WATCH_DAYS_REACHED"
    assert expired["cooldown_until_date"] == "2026-07-22"


def test_same_event_cannot_reenter_after_cooldown_but_new_event_can(tmp_path):
    db.init_db(str(tmp_path / "reentry.db"))
    _update("000001", "2026-07-01")
    _update("000001", "2026-07-15")

    same_event = _update("000001", "2026-07-23")
    new_event = _update("000001", "2026-07-23", event_key="start-b|pattern-b")

    assert same_event["blocked"] is True
    assert same_event["lifecycle_status"] == "COOLDOWN"
    assert new_event["blocked"] is False
    assert new_event["reentry_count"] == 1
    assert new_event["first_seen_date"] == "2026-07-23"


def test_active_candidate_failure_enters_ten_day_cooldown(tmp_path):
    db.init_db(str(tmp_path / "failure.db"))
    _update("000001", "2026-07-01")

    failed = _update("000001", "2026-07-02", candidate_type="REJECTED")

    assert failed["lifecycle_status"] == "FAILED"
    assert failed["blocked"] is True
    assert failed["exit_reason"] == "SUPPORT_FAILED"
    assert failed["cooldown_until_date"] == "2026-07-16"


def test_same_pattern_can_reenter_after_cooldown_when_support_recovers(tmp_path):
    db.init_db(str(tmp_path / "support-recovery.db"))
    _update("000001", "2026-07-01")
    _update("000001", "2026-07-02", candidate_type="REJECTED")

    recovered = _update("000001", "2026-07-17", candidate_type="KEY_CANDIDATE")

    assert recovered["blocked"] is False
    assert recovered["lifecycle_status"] == "READY"
    assert recovered["reentry_count"] == 1


def test_natural_phase_expiry_uses_five_day_expired_cooldown(tmp_path):
    db.init_db(str(tmp_path / "natural-expiry.db"))
    _update("000001", "2026-07-01")

    expired = db.update_strategy6_lifecycle(
        code="000001", evaluation_date="2026-07-02", candidate_type="REJECTED",
        lifecycle_status="EXPIRED", event_key="start-a|pattern-a", reject_reasons=["START_TOO_OLD"],
        max_watch_days=10, expired_cooldown_days=5, failed_cooldown_days=10,
    )

    assert expired["lifecycle_status"] == "EXPIRED"
    assert expired["exit_reason"] == "START_TOO_OLD"
    assert expired["cooldown_until_date"] == "2026-07-09"


def test_extended_breakout_keeps_extended_state_without_failed_cooldown(tmp_path):
    db.init_db(str(tmp_path / "extended.db"))
    _update("000001", "2026-07-01")

    extended = db.update_strategy6_lifecycle(
        code="000001", evaluation_date="2026-07-02", candidate_type="REJECTED",
        lifecycle_status="EXTENDED", event_key="start-a|pattern-a",
        reject_reasons=["BREAKOUT_EXTENDED"], max_watch_days=10,
        expired_cooldown_days=5, failed_cooldown_days=10,
    )

    assert extended["lifecycle_status"] == "EXTENDED"
    assert extended["blocked"] is True
    assert extended["exit_reason"] == "BREAKOUT_EXTENDED"
    assert extended["cooldown_until_date"] == ""


def test_expired_same_event_cannot_reenter_after_cooldown(tmp_path):
    db.init_db(str(tmp_path / "expired-same-event.db"))
    _update("000001", "2026-07-01")
    db.update_strategy6_lifecycle(
        code="000001", evaluation_date="2026-07-02", candidate_type="REJECTED",
        lifecycle_status="EXPIRED", event_key="start-a|pattern-a", reject_reasons=["START_TOO_OLD"],
        max_watch_days=10, expired_cooldown_days=5, failed_cooldown_days=10,
    )

    same_event = _update("000001", "2026-07-10")

    assert same_event["blocked"] is True


def _evaluation_event(*, pattern_end="2026-07-08", pivot=12.0, low=10.5, contractions=2, lifecycle="READY", start_grade="A"):
    return SimpleNamespace(
        start=SimpleNamespace(
            start_date="2026-06-20",
            start_type="NORMAL_STRONG_BREAKOUT",
            start_grade=start_grade,
        ),
        pattern=SimpleNamespace(
            pattern_type="VCP",
            pattern_start_date="2026-06-25",
            pattern_end_date=pattern_end,
            contraction_count=contractions,
            pivot_price=pivot,
            pattern_low=low,
        ),
        lifecycle_status=lifecycle,
    )


def test_event_key_ignores_daily_price_drift_but_changes_for_new_structure_event():
    original = _strategy6_event_key(_evaluation_event())
    daily_drift = _strategy6_event_key(_evaluation_event(
        pattern_end="2026-07-09",
        pivot=12.03,
        low=10.52,
    ))
    new_contraction = _strategy6_event_key(_evaluation_event(contractions=3))
    breakout = _strategy6_event_key(_evaluation_event(lifecycle="BREAKOUT_CONFIRMED"))
    rolling_grade = _strategy6_event_key(_evaluation_event(start_grade="S"))
    extended = _strategy6_event_key(_evaluation_event(lifecycle="EXTENDED"))

    assert daily_drift == original
    assert rolling_grade == original
    assert extended == original
    assert new_contraction != original
    assert breakout != original
