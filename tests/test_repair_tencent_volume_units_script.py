from scanner import db
from scripts.repair_tencent_volume_units import (
    build_parser,
    find_star_market_codes,
    resolve_suspicious_before,
)


def _row(code: str) -> dict:
    return {
        "date": "2026-07-21",
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1_000_000,
        "turnover": 10_200_000,
    }


def test_repair_selects_all_star_market_stocks_with_existing_ohlc(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_stock_pool(
        [
            {"code": "688981", "name": "中芯国际", "market": "SH"},
            {"code": "689009", "name": "测试科创板", "market": "SH"},
            {"code": "600519", "name": "贵州茅台", "market": "SH"},
            {"code": "688001", "name": "无日线", "market": "SH"},
        ]
    )
    for code in ("688981", "689009", "600519"):
        db.save_ohlc(code, [_row(code)])

    assert find_star_market_codes() == ["688981", "689009"]


def test_tencent_volume_repair_cli_is_safe_by_default():
    args = build_parser().parse_args(["--dry-run"])

    assert args.workers == 3
    assert args.busy_retries == 3
    assert args.limit == 0


def test_resume_preserves_original_suspicious_row_count():
    assert resolve_suspicious_before({"suspicious_before": 19_838}, 11) == 19_838
    assert resolve_suspicious_before({}, 19_838) == 19_838
