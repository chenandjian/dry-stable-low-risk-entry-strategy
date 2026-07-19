from scanner.kline_repair import RepairResult
from scripts.repair_sina_adjustment import (
    _load_requested_days,
    _repair_with_busy_retries,
    _update_resume_state,
    build_parser,
)


def test_repair_window_uses_largest_configured_kline_requirement(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "liquidity:\n  min_listing_days: 800\n"
        "strategy5:\n  kline_days: 1100\n"
        "strategy6:\n  kline_days: 1000\n",
        encoding="utf-8",
    )

    assert _load_requested_days(config) == 1100


def test_repair_cli_defaults_to_three_workers():
    args = build_parser().parse_args(["--dry-run"])
    assert args.workers == 3
    assert args.busy_retries == 3


def test_repair_with_busy_retries_requeues_when_any_source_was_busy():
    calls = []

    def repair_once():
        calls.append(1)
        if len(calls) == 1:
            return RepairResult(
                code="000006",
                status="failed",
                source_errors={"tencent": "busy", "baidu": "empty response"},
            )
        return RepairResult(code="000006", status="would_repair", source="tencent")

    result = _repair_with_busy_retries(repair_once, max_busy_retries=3, sleep_fn=lambda _seconds: None)

    assert len(calls) == 2
    assert result.status == "would_repair"
    assert result.source == "tencent"


def test_update_resume_state_only_completes_success_and_replaces_retry_result():
    state = {"completed": [], "results": []}

    _update_resume_state(state, {"code": "002396", "status": "failed"})
    assert state["completed"] == []
    assert state["results"] == [{"code": "002396", "status": "failed"}]

    _update_resume_state(
        state,
        {"code": "002396", "status": "repaired", "source": "tencent"},
    )
    assert state["completed"] == ["002396"]
    assert state["results"] == [
        {"code": "002396", "status": "repaired", "source": "tencent"}
    ]
