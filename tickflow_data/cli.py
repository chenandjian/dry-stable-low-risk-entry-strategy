from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path

from scanner import db

from .client import TickFlowBatchClient
from .models import BatchUpdateResult
from .service import TickFlowDailyUpdateService


ADJUSTMENT = "forward_additive"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="TickFlow A-share batch daily updater")
    parser.add_argument("mode", choices=("update", "backfill"))
    safety = parser.add_mutually_exclusive_group()
    safety.add_argument("--execute", action="store_true", help="write validated data")
    safety.add_argument("--dry-run", action="store_true", help="request and validate only")
    parser.add_argument("--database", default="data/cuphandle.db")
    parser.add_argument("--codes", nargs="+")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--history-days", type=int, default=1100)
    parser.add_argument("--overlap-days", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--report")
    parser.add_argument("--progress-file")
    args = parser.parse_args(argv)
    args.dry_run = not args.execute
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if min(args.history_days, args.overlap_days, args.batch_size, args.max_workers) <= 0:
        parser.error("day counts, batch size, and worker count must be positive")
    return args


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _backup_database(database: Path) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = database.with_name(f"{database.stem}.pre-tickflow-{timestamp}.db")
    source_conn = sqlite3.connect(str(database))
    target_conn = sqlite3.connect(str(backup))
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    return backup


def _signature(args, database: Path) -> dict:
    return {
        "mode": args.mode,
        "database": str(database.resolve()),
        "history_days": args.history_days,
        "overlap_days": args.overlap_days,
        "adjustment": ADJUSTMENT,
        "requested_codes": sorted(args.codes or []),
        "limit": args.limit,
    }


def _new_run_id() -> str:
    return f"tickflow-{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def _load_progress(path: Path, signature: dict, run_id: str) -> dict:
    if not path.exists():
        return {**signature, "run_id": run_id, "completed_codes": [], "runs": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if any(payload.get(key) != value for key, value in signature.items()):
        raise ValueError(f"progress file does not match this run: {path}")
    payload.setdefault("completed_codes", [])
    payload.setdefault("runs", [])
    return payload


def _select_stocks(args, completed_codes: set[str]) -> list[dict]:
    stocks = db.get_stock_pool()
    by_code = {str(stock["code"]): stock for stock in stocks}
    if args.codes:
        requested = [str(code).strip() for code in args.codes]
        unknown = [code for code in requested if code not in by_code]
        if unknown:
            raise ValueError(f"codes are not present in stock_pool: {', '.join(unknown)}")
        stocks = [by_code[code] for code in requested]
    if args.limit is not None:
        stocks = stocks[: args.limit]
    return [stock for stock in stocks if str(stock["code"]) not in completed_codes]


def _write_report(path: Path, result: BatchUpdateResult, backup: Path | None) -> None:
    success = [item for item in result.results if item.status in {"success", "validated"}]
    failed = [item for item in result.results if item.status == "failed"]
    full = [item for item in result.results if item.request_mode.startswith("full")]
    lines = [
        "# TickFlow批量日线运行报告",
        "",
        f"- 运行ID：`{result.run_id}`",
        f"- 模式：`{result.mode}`",
        f"- 执行方式：`{'dry-run' if result.dry_run else 'execute'}`",
        f"- 复权口径：`{ADJUSTMENT}`",
        f"- 开始时间：`{result.started_at}`",
        f"- 结束时间：`{result.finished_at}`",
        f"- 批量耗时：`{result.elapsed_seconds:.3f}`秒",
        f"- 成功/验证：{len(success)}",
        f"- 失败：{len(failed)}",
        f"- 完整重拉：{len(full)}",
        f"- 数据库备份：`{backup or '无（dry-run）'}`",
        "",
        "| 股票 | 状态 | 请求类型 | 行数 | 首日 | 末日 | 错误 |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for item in result.results:
        error = (item.error or "").replace("|", "/")
        lines.append(
            f"| {item.code} | {item.status} | {item.request_mode} | "
            f"{item.row_count} | {item.first_date or ''} | {item.latest_date or ''} | {error} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_command(args, *, client_factory=TickFlowBatchClient) -> BatchUpdateResult:
    database = Path(args.database).resolve()
    db.init_db(str(database))

    proposed_run_id = _new_run_id()
    progress_path = (
        Path(args.progress_file)
        if args.progress_file
        else database.parent
        / "tickflow"
        / f"progress-{args.mode}-{proposed_run_id}.json"
    )
    signature = _signature(args, database)
    progress = _load_progress(progress_path, signature, proposed_run_id)
    completed = {str(code) for code in progress["completed_codes"]}
    stocks = _select_stocks(args, completed)

    backup = _backup_database(database) if args.execute else None
    client = client_factory(batch_size=args.batch_size, max_workers=args.max_workers)
    service = TickFlowDailyUpdateService(
        client,
        history_days=args.history_days,
        overlap_days=args.overlap_days,
    )

    def record_success(item) -> None:
        if args.execute:
            completed.add(item.code)
            progress["completed_codes"] = sorted(completed)
            _atomic_write_json(progress_path, progress)

    result = service.run(
        stocks,
        dry_run=args.dry_run,
        mode=args.mode,
        run_id=progress["run_id"],
        on_success=record_success,
    )
    progress["completed_codes"] = sorted(completed)
    progress["runs"].append(result.to_dict())
    _atomic_write_json(progress_path, progress)

    report_path = (
        Path(args.report)
        if args.report
        else database.parent / "tickflow" / "reports" / f"{result.run_id}.md"
    )
    _write_report(report_path, result, backup)
    return result


def main(argv=None) -> int:
    args = parse_args(argv)
    result = run_command(args)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 1 if any(item.status == "failed" for item in result.results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
