"""Rebuild STAR-market OHLC after correcting Tencent volume units."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner import db  # noqa: E402
from scanner.data_source import DataSourceManager  # noqa: E402
from scanner.kline_repair import RepairResult, repair_stock  # noqa: E402
from scripts.repair_sina_adjustment import (  # noqa: E402
    _backup_database,
    _load_requested_days,
    _read_state,
    _repair_with_busy_retries,
    _update_resume_state,
    _write_state,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--database", default="data/cuphandle.db")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--codes", nargs="*")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--busy-retries", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--resume-file", default="data/tencent-volume-unit-repair-progress.json")
    parser.add_argument(
        "--report",
        default="docs/reviews/2026-07-21-tencent-volume-unit-repair-report.md",
    )
    return parser


def find_star_market_codes() -> list[str]:
    rows = db.get_conn().execute(
        """
        SELECT DISTINCT code
        FROM daily_ohlc
        WHERE code LIKE '688%' OR code LIKE '689%'
        ORDER BY code
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def count_suspicious_rows() -> int:
    return int(
        db.get_conn().execute(
            """
            SELECT COUNT(*) FROM daily_ohlc
            WHERE (code LIKE '688%' OR code LIKE '689%')
              AND volume >= 1000000000
            """
        ).fetchone()[0]
    )


def resolve_suspicious_before(state: dict, current_count: int) -> int:
    """Keep the original pre-repair count across resume runs."""
    return int(state.get("suspicious_before", current_count))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = _resolve(args.database)
    config_path = _resolve(args.config)
    resume_path = _resolve(args.resume_file)
    report_path = _resolve(args.report)
    db.init_db(str(database))

    eligible = find_star_market_codes()
    requested = [str(code).zfill(6) for code in (args.codes or eligible)]
    codes = [code for code in requested if code in set(eligible)]
    if args.limit > 0:
        codes = codes[: args.limit]

    requested_days = _load_requested_days(config_path)
    state = _read_state(resume_path) if args.execute else {}
    suspicious_before = resolve_suspicious_before(state, count_suspicious_rows())
    completed = set(state.get("completed", []))
    results = list(state.get("results", []))
    pending = [code for code in codes if code not in completed]
    run_id = state.get("run_id") or datetime.now().strftime("tencent-volume-repair-%Y%m%d-%H%M%S")
    backup_path = state.get("backup_path")

    if args.execute and not backup_path:
        backup_path = str(_backup_database(database, run_id))
        state = {
            "run_id": run_id,
            "database": str(database),
            "backup_path": backup_path,
            "suspicious_before": suspicious_before,
            "completed": [],
            "results": [],
        }
        _write_state(resume_path, state)

    print(
        f"eligible={len(eligible)} selected={len(codes)} pending={len(pending)} "
        f"requested_days={requested_days} suspicious_before={suspicious_before}"
    )
    source_manager = DataSourceManager()

    def run_one(code: str) -> RepairResult:
        result = _repair_with_busy_retries(
            lambda: repair_stock(
                code,
                requested_days=requested_days,
                source_manager=source_manager,
                dry_run=args.dry_run,
                repair_run_id=run_id,
            ),
            max_busy_retries=max(0, int(args.busy_retries)),
        )
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)
        return result

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
        futures = {executor.submit(run_one, code): code for code in pending}
        for index, future in enumerate(as_completed(futures), start=1):
            code = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = RepairResult(code=code, status="failed", source_errors={"worker": str(exc)})
            payload = asdict(result)
            if args.execute:
                _update_resume_state(state, payload)
                _write_state(resume_path, state)
                results = list(state["results"])
            else:
                results.append(payload)
            print(
                f"[{index}/{len(pending)}] {code} {result.status} "
                f"source={result.source or '-'} rows={result.row_count}",
                flush=True,
            )

    suspicious_after = count_suspicious_rows()
    _write_report(
        report_path,
        run_id=run_id,
        database=database,
        backup_path=backup_path,
        mode="EXECUTE" if args.execute else "DRY_RUN",
        requested_days=requested_days,
        eligible_count=len(eligible),
        suspicious_before=suspicious_before,
        suspicious_after=suspicious_after,
        results=results,
    )
    return 1 if any(item["status"] == "failed" for item in results) else 0


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _write_report(
    path: Path,
    *,
    run_id: str,
    database: Path,
    backup_path: str | None,
    mode: str,
    requested_days: int,
    eligible_count: int,
    suspicious_before: int,
    suspicious_after: int,
    results: list[dict],
) -> None:
    statuses = Counter(item["status"] for item in results)
    sources = Counter(item.get("source") for item in results if item.get("source"))
    lines = [
        "# 腾讯成交量单位修复报告",
        "",
        f"- 运行ID：`{run_id}`",
        f"- 模式：`{mode}`",
        f"- 数据库：`{database}`",
        f"- 备份：`{backup_path or '未创建（dry-run）'}`",
        f"- 修复窗口：{requested_days}根",
        f"- 科创板日线股票：{eligible_count}只",
        f"- 十亿股以上可疑行：{suspicious_before} -> {suspicious_after}",
        f"- 状态：`{dict(statuses)}`",
        f"- 成功来源：`{dict(sources)}`",
        "",
        "## 逐股结果",
        "",
        "| 股票 | 状态 | 数据源 | 行数 | 首日 | 末日 | 错误 |",
        "|---|---|---|---:|---|---|---|",
    ]
    for item in results:
        errors = json.dumps(item.get("source_errors") or {}, ensure_ascii=False).replace("|", "\\|")
        lines.append(
            f"| {item['code']} | {item['status']} | {item.get('source') or ''} | "
            f"{item.get('row_count') or 0} | {item.get('first_date') or ''} | "
            f"{item.get('latest_date') or ''} | `{errors}` |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
