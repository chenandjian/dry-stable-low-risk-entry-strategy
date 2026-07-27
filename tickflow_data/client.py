from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import Any

from .models import BatchFetchResult


DEFAULT_TICKFLOW_API_KEY = "tk_c585255a8a8843a08bc15bc5a7539acf"
FREE_ACCESS_MODE = "free"
AUTHENTICATED_ACCESS_MODE = "authenticated"
TICKFLOW_ACCESS_MODES = {FREE_ACCESS_MODE, AUTHENTICATED_ACCESS_MODE}


class TickFlowClientError(RuntimeError):
    """Raised when a TickFlow batch request cannot be completed safely."""


def resolve_tickflow_access_mode(access_mode: str | None = None) -> str:
    value = FREE_ACCESS_MODE if access_mode is None else access_mode
    if not isinstance(value, str):
        raise ValueError("data.tickflow_access_mode must be a string")
    normalized = value.strip().lower()
    if normalized not in TICKFLOW_ACCESS_MODES:
        allowed = ", ".join(sorted(TICKFLOW_ACCESS_MODES))
        raise ValueError(f"data.tickflow_access_mode must be one of: {allowed}")
    return normalized


def resolve_tickflow_api_key(api_key: str | None = None) -> str:
    """Resolve an authenticated key without assuming a provider-specific prefix."""
    if api_key is not None and not isinstance(api_key, str):
        raise TickFlowClientError("TickFlow API key must be a string")
    explicit = (api_key or "").strip()
    if explicit:
        return explicit
    environment = os.environ.get("TICKFLOW_API_KEY", "").strip()
    if environment:
        return environment
    default = DEFAULT_TICKFLOW_API_KEY.strip()
    if default:
        return default
    raise TickFlowClientError("TickFlow API key is not configured")


class TickFlowBatchClient:
    def __init__(
        self,
        *,
        sdk: Any | None = None,
        access_mode: str | None = None,
        api_key: str | None = None,
        batch_size: int = 100,
        max_workers: int = 5,
        batch_retries: int = 1,
        retry_delay_seconds: float = 0.5,
    ):
        if batch_size <= 0 or max_workers <= 0 or batch_retries < 0:
            raise ValueError("invalid TickFlow batch client settings")
        self._sdk = sdk
        self._access_mode = resolve_tickflow_access_mode(access_mode)
        self._api_key = api_key
        self._owns_sdk = False
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.batch_retries = batch_retries
        self.retry_delay_seconds = retry_delay_seconds

    def __enter__(self) -> "TickFlowBatchClient":
        self._ensure_sdk()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._owns_sdk and self._sdk is not None:
            self._sdk.close()
            self._sdk = None
            self._owns_sdk = False

    def _ensure_sdk(self):
        if self._sdk is not None:
            return self._sdk
        try:
            from tickflow import TickFlow
        except ImportError as exc:
            raise TickFlowClientError(
                "TickFlow SDK is not installed; run pip install -r requirements.txt"
            ) from exc

        if self._access_mode == FREE_ACCESS_MODE:
            self._sdk = TickFlow.free()
        else:
            self._sdk = TickFlow(api_key=resolve_tickflow_api_key(self._api_key))
        self._owns_sdk = True
        return self._sdk

    def fetch(self, symbols: list[str], *, count: int) -> BatchFetchResult:
        return self._fetch(symbols, count=count, adjustment="forward_additive")

    def fetch_indexes(self, symbols: list[str], *, count: int) -> BatchFetchResult:
        """Fetch unadjusted index bars without weakening the stock price contract."""
        return self._fetch(symbols, count=count, adjustment="none")

    def _fetch(
        self,
        symbols: list[str],
        *,
        count: int,
        adjustment: str,
    ) -> BatchFetchResult:
        requested = [str(symbol).strip().upper() for symbol in symbols]
        if not requested or count <= 0:
            raise ValueError("symbols must not be empty and count must be positive")
        if len(set(requested)) != len(requested):
            raise ValueError("TickFlow batch request contains duplicate symbols")

        sdk = self._ensure_sdk()
        last_error: Exception | None = None
        for attempt in range(self.batch_retries + 1):
            try:
                raw = sdk.klines.batch(
                    requested,
                    period="1d",
                    count=count,
                    adjust=adjustment,
                    as_dataframe=True,
                    show_progress=False,
                    max_workers=self.max_workers,
                    batch_size=self.batch_size,
                )
                frames = self._coerce_frames(raw)
                requested_set = set(requested)
                unexpected = sorted(set(frames) - requested_set)
                if unexpected:
                    raise TickFlowClientError(
                        f"batch returned unexpected symbols: {', '.join(unexpected)}"
                    )
                return BatchFetchResult(
                    frames=frames,
                    missing_symbols=[symbol for symbol in requested if symbol not in frames],
                )
            except TickFlowClientError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self.batch_retries and self.retry_delay_seconds > 0:
                    time.sleep(self.retry_delay_seconds)

        raise TickFlowClientError(f"TickFlow batch request failed: {last_error}") from last_error

    @staticmethod
    def _coerce_frames(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise TickFlowClientError(
                f"unexpected TickFlow batch response type: {type(raw).__name__}"
            )
        frames: dict[str, Any] = {}
        for symbol, frame in raw.items():
            normalized_symbol = str(symbol).strip().upper()
            if normalized_symbol in frames:
                raise TickFlowClientError(
                    f"batch returned duplicate symbol: {normalized_symbol}"
                )
            frames[normalized_symbol] = frame
        return frames


__all__ = [
    "AUTHENTICATED_ACCESS_MODE",
    "DEFAULT_TICKFLOW_API_KEY",
    "FREE_ACCESS_MODE",
    "TICKFLOW_ACCESS_MODES",
    "TickFlowBatchClient",
    "TickFlowClientError",
    "resolve_tickflow_access_mode",
    "resolve_tickflow_api_key",
]
