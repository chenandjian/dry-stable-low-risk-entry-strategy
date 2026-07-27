"""Repair legacy Sina unadjusted OHLC with complete forward-adjusted source data."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
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
from scanner.config_io import load_yaml_config  # noqa: E402
from scanner.data_source import DataSourceManager  # noqa: E402
from scanner.kline_repair import find_legacy_sina_candidates, repair_stock  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="validate source coverage without writing OHLC")
    mode.add_argument("--execute", action="store_true", help="backup DB and replace eligible OHLC")
    parser.add_argument("--database", default="data/cuphandle.db")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--codes", nargs="*", help="repair only these codes after eligibility check")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--busy-retries", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--resume-file", default="data/sina-qfq-repair-progress.json")
    parser.add_argument("--report", default="docs/reviews/2026-07-19-sina-qfq-data-repair-report.md")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = _resolve(args.database)
    config_path = _resolve(args.config)
    resume_path = _resolve(args.resume_file)
    report_path = _resolve(args.report)
    requested_days = _load_requested_days(config_path)
    db.init_db(str(database))

    candidates, unknown = find_legacy_sina_candidates()
    eligible = {item["code"]: item for item in candidates}
    requested_codes = [str(code).zfill(6) for code in (args.codes or eligible.keys())]
    codes = [code for code in requested_codes if code in eligible]
    ineligible = [code for code in requested_codes if code not in eligible]
    if args.limit > 0:
        codes = codes[: args.limit]

    state = _read_state(resume_path)
    completed = set(state.get("completed", [])) if args.execute else set()
    results = list(state.get("results", [])) if args.execute else []
    pending = [code for code in codes if code not in completed]
    run_id = state.get("run_id") if args.execute else None
    if not run_id:
        run_id = datetime.now().strftime("sina-qfq-repair-%Y%m%d-%H%M%S")

    backup_path = state.get("backup_path") if args.execute else None
    if args.execute and not backup_path:
        backup_path = str(_backup_database(database, run_id))
        state = {
            "run_id": run_id,
            "database": str(database),
            "backup_path": backup_path,
            "completed": [],
            "results": [],
        }
        _write_state(resume_path, state)

    print(
        f"eligible={len(candidates)} unknown={len(unknown)} selected={len(codes)} "
        f"pending={len(pending)} requested_days={requested_days}"
    )
    if ineligible:
        print(f"ineligible={','.join(ineligible)}")

    source_manager = DataSourceManager()

    def run_one(code: str):
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
                from scanner.kline_repair import RepairResult

                result = RepairResult(code=code, status="failed", source_errors={"worker": str(exc)})
            payload = asdict(result)
            if args.execute:
                _update_resume_state(state, payload)
                completed = set(state["completed"])
                results = list(state["results"])
            else:
                results.append(payload)
            print(
                f"[{index}/{len(pending)}] {code} {result.status} "
                f"source={result.source or '-'} rows={result.row_count} latest={result.latest_date or '-'}",
                flush=True,
            )
            if args.execute:
                _write_state(resume_path, state)

    _write_report(
        report_path,
        run_id=run_id,
        database=database,
        backup_path=backup_path,
        dry_run=args.dry_run,
        requested_days=requested_days,
        eligible_count=len(candidates),
        unknown=unknown,
        ineligible=ineligible,
        results=results,
    )
    failed = sum(1 for item in results if item["status"] == "failed")
    return 1 if failed else 0


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _load_requested_days(config_path: Path) -> int:
    config = load_yaml_config(config_path)
    windows = [int(config.get("liquidity", {}).get("min_listing_days", 800))]
    for section in config.values():
        if isinstance(section, dict) and "kline_days" in section:
            windows.append(int(section["kline_days"]))
    return max(windows)


def _backup_database(database: Path, run_id: str) -> Path:
    backup_dir = database.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"cuphandle-before-{run_id}.db"
    required = database.stat().st_size
    free = shutil.disk_usage(backup_dir).free
    if free < required * 1.1:
        raise RuntimeError(f"insufficient disk space for backup: required={required}, free={free}")
    source = db.get_conn()
    with sqlite3.connect(backup_path) as target:
        source.backup(target)
    return backup_path


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _update_resume_state(state: dict, result: dict):
    """Replace a code's latest result and only checkpoint successful repairs."""
    code = result["code"]
    by_code = {item["code"]: item for item in state.get("results", [])}
    by_code[code] = result
    completed = set(state.get("completed", []))
    if result.get("status") == "repaired":
        completed.add(code)
    else:
        completed.discard(code)
    state["completed"] = sorted(completed)
    state["results"] = [by_code[key] for key in sorted(by_code)]


def _repair_with_busy_retries(repair_fn, *, max_busy_retries: int, sleep_fn=time.sleep):
    """Requeue a stock when at least one preferred source was temporarily busy."""
    result = repair_fn()
    retries = 0
    while (
        result.status == "failed"
        and "busy" in result.source_errors.values()
        and retries < max_busy_retries
    ):
        retries += 1
        sleep_fn(min(0.1 * retries, 0.5))
        result = repair_fn()
    return result


def _write_report(
    path: Path,
    *,
    run_id: str,
    database: Path,
    backup_path: str | None,
    dry_run: bool,
    requested_days: int,
    eligible_count: int,
    unknown: list[dict],
    ineligible: list[str],
    results: list[dict],
):
    status_counts = Counter(item["status"] for item in results)
    source_counts = Counter(item["source"] for item in results if item.get("source"))
    lines = [
        "# 新浪未复权历史 K 线修复报告",
        "",
        f"- 运行ID：`{run_id}`",
        f"- 模式：`{'DRY_RUN' if dry_run else 'EXECUTE'}`",
        f"- 数据库：`{database}`",
        f"- 备份：`{backup_path or '未创建（dry-run）'}`",
        f"- 修复窗口：{requested_days} 根",
        f"- 可推断旧新浪来源：{eligible_count} 只",
        f"- 无法推断来源：{len(unknown)} 只",
        f"- 本次结果：`{dict(status_counts)}`",
        f"- 成功数据源：`{dict(source_counts)}`",
        "",
        "## 逐股结果",
        "",
        "| 股票 | 状态 | 成功源 | 行数 | 首日 | 末日 | 源错误 |",
        "|---|---|---|---:|---|---|---|",
    ]
    for item in results:
        errors = json.dumps(item.get("source_errors") or {}, ensure_ascii=False).replace("|", "\\|")
        lines.append(
            f"| {item['code']} | {item['status']} | {item.get('source') or ''} | "
            f"{item.get('row_count') or 0} | {item.get('first_date') or ''} | "
            f"{item.get('latest_date') or ''} | `{errors}` |"
        )
    if ineligible:
        lines.extend(["", "## 不符合自动修复资格", "", ", ".join(ineligible)])
    if unknown:
        lines.extend(["", "## 来源无法推断", "", ", ".join(item["code"] for item in unknown)])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
