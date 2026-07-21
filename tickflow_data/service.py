from __future__ import annotations

import datetime as dt
import time
import uuid

from scanner import db

from .models import BatchUpdateResult, StockUpdateResult
from .normalize import normalize_frame
from .symbols import to_tickflow_symbol


ADJUSTMENT_TOLERANCE = 1e-6


def _ohlc_changed(old: dict, new: dict) -> bool:
    for field in ("open", "high", "low", "close"):
        old_value = float(old[field])
        new_value = float(new[field])
        scale = max(abs(old_value), abs(new_value), 1e-12)
        if abs(old_value - new_value) / scale > ADJUSTMENT_TOLERANCE:
            return True
    return False


def _merge_rows(existing: list[dict], fresh: list[dict], max_rows: int) -> list[dict]:
    merged = {row["date"]: dict(row) for row in existing}
    merged.update({row["date"]: dict(row) for row in fresh})
    rows = [merged[date] for date in sorted(merged)]
    return rows[-max_rows:]


class TickFlowDailyUpdateService:
    def __init__(
        self,
        client,
        *,
        history_days: int = 1100,
        overlap_days: int = 10,
    ):
        if history_days <= 0 or overlap_days <= 0:
            raise ValueError("history_days and overlap_days must be positive")
        self.client = client
        self.history_days = history_days
        self.overlap_days = overlap_days

    def run(
        self,
        stocks: list[dict],
        *,
        dry_run: bool,
        mode: str = "update",
        run_id: str | None = None,
        on_success=None,
    ) -> BatchUpdateResult:
        if mode not in {"update", "backfill"}:
            raise ValueError(f"unsupported TickFlow update mode: {mode}")
        started = time.perf_counter()
        started_at = dt.datetime.now().isoformat(timespec="seconds")
        run_id = run_id or f"tickflow-{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        batch = BatchUpdateResult(
            run_id=run_id,
            mode=mode,
            dry_run=dry_run,
            started_at=started_at,
        )
        if not stocks:
            batch.finished_at = dt.datetime.now().isoformat(timespec="seconds")
            batch.elapsed_seconds = round(time.perf_counter() - started, 3)
            return batch

        results_by_code: dict[str, StockUpdateResult] = {}
        full_symbols: list[str] = []
        incremental_symbols: list[str] = []

        for stock in stocks:
            code = str(stock.get("code", "")).strip()
            result = StockUpdateResult(code=code)
            if code in results_by_code:
                raise ValueError(f"duplicate stock code in update request: {code}")
            results_by_code[code] = result
            try:
                symbol = to_tickflow_symbol(code, stock.get("market"))
            except ValueError as exc:
                result.status = "failed"
                result.error = str(exc)
                continue
            result.symbol = symbol
            metadata = db.get_ohlc_metadata(code)
            existing = db.get_ohlc(code) or []
            if mode == "backfill" or not existing or not metadata or metadata.get("source") != "tickflow":
                result.request_mode = "full"
                full_symbols.append(symbol)
            else:
                result.request_mode = "incremental"
                incremental_symbols.append(symbol)

        with self.client as client:
            self._process_full_group(
                client,
                full_symbols,
                results_by_code,
                dry_run=dry_run,
                run_id=run_id,
                on_success=on_success,
            )
            refresh_symbols = self._process_incremental_group(
                client,
                incremental_symbols,
                results_by_code,
                dry_run=dry_run,
                run_id=run_id,
                on_success=on_success,
            )
            if refresh_symbols:
                for symbol in refresh_symbols:
                    results_by_code[self._code_for_symbol(symbol)].request_mode = (
                        "full_adjustment_refresh"
                    )
                self._process_full_group(
                    client,
                    refresh_symbols,
                    results_by_code,
                    dry_run=dry_run,
                    run_id=run_id,
                    on_success=on_success,
                )

        batch.results = [results_by_code[str(stock.get("code", "")).strip()] for stock in stocks]
        batch.finished_at = dt.datetime.now().isoformat(timespec="seconds")
        batch.elapsed_seconds = round(time.perf_counter() - started, 3)
        return batch

    def _fetch(self, client, symbols: list[str], *, count: int, results_by_code):
        if not symbols:
            return None
        try:
            return client.fetch(symbols, count=count)
        except Exception as exc:
            for symbol in symbols:
                result = results_by_code[self._code_for_symbol(symbol)]
                result.status = "failed"
                result.error = f"TickFlow batch request failed: {exc}"
            return None

    def _process_full_group(
        self,
        client,
        symbols: list[str],
        results_by_code: dict[str, StockUpdateResult],
        *,
        dry_run: bool,
        run_id: str,
        on_success,
    ) -> None:
        fetched = self._fetch(
            client,
            symbols,
            count=self.history_days,
            results_by_code=results_by_code,
        )
        if fetched is None:
            return
        missing = set(fetched.missing_symbols)
        for symbol in symbols:
            code = self._code_for_symbol(symbol)
            result = results_by_code[code]
            if symbol in missing or symbol not in fetched.frames:
                result.status = "failed"
                result.error = "TickFlow batch response omitted this symbol"
                continue
            try:
                rows = normalize_frame(fetched.frames[symbol])[-self.history_days :]
                existing = db.get_ohlc(code) or []
                if existing:
                    required_rows = min(len(existing), self.history_days)
                    if len(rows) < required_rows:
                        raise ValueError(
                            f"full history shortened from {required_rows} to {len(rows)} rows"
                        )
                    if rows[-1]["date"] < existing[-1]["date"]:
                        raise ValueError(
                            "full history latest date regressed from "
                            f"{existing[-1]['date']} to {rows[-1]['date']}"
                        )
                self._finish_stock(
                    result,
                    rows,
                    dry_run=dry_run,
                    run_id=run_id,
                )
            except Exception as exc:
                result.status = "failed"
                result.error = str(exc)
            else:
                if on_success is not None:
                    on_success(result)

    def _process_incremental_group(
        self,
        client,
        symbols: list[str],
        results_by_code: dict[str, StockUpdateResult],
        *,
        dry_run: bool,
        run_id: str,
        on_success,
    ) -> list[str]:
        fetched = self._fetch(
            client,
            symbols,
            count=self.overlap_days,
            results_by_code=results_by_code,
        )
        if fetched is None:
            return []
        missing = set(fetched.missing_symbols)
        full_refresh: list[str] = []
        for symbol in symbols:
            code = self._code_for_symbol(symbol)
            result = results_by_code[code]
            if symbol in missing or symbol not in fetched.frames:
                result.status = "failed"
                result.error = "TickFlow batch response omitted this symbol"
                continue
            try:
                fresh = normalize_frame(fetched.frames[symbol])
                existing = db.get_ohlc(code) or []
                existing_by_date = {row["date"]: row for row in existing}
                common = [row for row in fresh if row["date"] in existing_by_date]
                if not common or _ohlc_changed(existing_by_date[common[0]["date"]], common[0]):
                    full_refresh.append(symbol)
                    continue
                merged = _merge_rows(existing, fresh, self.history_days)
                self._finish_stock(
                    result,
                    merged,
                    dry_run=dry_run,
                    run_id=run_id,
                )
            except Exception as exc:
                result.status = "failed"
                result.error = str(exc)
            else:
                if on_success is not None:
                    on_success(result)
        return full_refresh

    @staticmethod
    def _code_for_symbol(symbol: str) -> str:
        return symbol.split(".", 1)[0]

    @staticmethod
    def _finish_stock(
        result: StockUpdateResult,
        rows: list[dict],
        *,
        dry_run: bool,
        run_id: str,
    ) -> None:
        if not rows:
            raise ValueError("normalized TickFlow history is empty")
        if not dry_run:
            db.replace_ohlc_with_metadata(
                result.code,
                rows,
                source="tickflow",
                price_basis="FORWARD_ADJUSTED",
                repair_run_id=run_id,
            )
        result.status = "validated" if dry_run else "success"
        result.row_count = len(rows)
        result.first_date = rows[0]["date"]
        result.latest_date = rows[-1]["date"]
        result.error = None
