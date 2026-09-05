from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class TickFlowDataError(ValueError):
    """Raised when TickFlow data cannot be safely normalized or persisted."""


@dataclass(frozen=True)
class BatchFetchResult:
    frames: dict[str, Any]
    missing_symbols: list[str] = field(default_factory=list)


@dataclass
class StockUpdateResult:
    code: str
    symbol: str = ""
    status: str = "pending"
    request_mode: str = ""
    row_count: int = 0
    first_date: str | None = None
    latest_date: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BatchUpdateResult:
    run_id: str
    mode: str
    dry_run: bool
    started_at: str = ""
    finished_at: str = ""
    elapsed_seconds: float = 0.0
    results: list[StockUpdateResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        succeeded = sum(
            result.status in {"success", "validated"} for result in self.results
        )
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed_seconds,
            "summary": {
                "requested": len(self.results),
                "succeeded": succeeded,
                "failed": sum(result.status == "failed" for result in self.results),
                "full_refresh": sum(
                    result.request_mode.startswith("full") for result in self.results
                ),
            },
            "results": [result.to_dict() for result in self.results],
        }
