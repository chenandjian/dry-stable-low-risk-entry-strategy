"""Run one Strategy6 quality stage against a frozen local data/config snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path.cwd()))

from scanner import db
from scanner.config_io import load_yaml_config
from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.index_history import load_index_history
from strategy6.backtest.report import write_backtest_report
from strategy6.backtest.runner import run_local_parameter_set
from strategy6.validation import resolve_strategy6_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--oos-start", default="2026-01-01")
    parser.add_argument("--mode", default="COARSE_TRAIN")
    parser.add_argument("--evaluation-step", type=int, default=5)
    parser.add_argument("--workers", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db.init_db(args.db)
    coverage = load_index_history(args.start, args.end)
    if coverage.status != "READY":
        raise RuntimeError(f"real index history unavailable: {coverage.missing_symbols}")
    root = load_yaml_config(args.config)
    strategy_config = resolve_strategy6_config({"strategy6": root.get("strategy6") or {}})
    run_args = SimpleNamespace(
        db=args.db,
        start=args.start,
        end=args.end,
        oos_start=args.oos_start,
        run_mode=args.mode,
        evaluation_step=args.evaluation_step,
        stage_id=args.stage,
        parent_parameter_set_id="",
        workers=args.workers,
    )
    result = run_local_parameter_set(
        experiment_id=f"QUALITY_MAIN_CHAIN_{args.stage}_{args.mode}",
        strategy_config=strategy_config,
        backtest_config=resolve_backtest_config({}),
        coverage=coverage,
        args=run_args,
    )
    output = Path(args.output)
    paths = write_backtest_report(result, output)
    manifest = {
        "stage_id": args.stage,
        "mode": args.mode,
        "evaluation_step": args.evaluation_step,
        "start": args.start,
        "end": args.end,
        "run": result.get("run") or {},
        "parameter_set_id": result.get("parameter_set_id"),
        "paths": {key: str(path.resolve()) for key, path in paths.items()},
    }
    manifest_path = output / "stage-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
