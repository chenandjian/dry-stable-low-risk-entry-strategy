"""Strategy4 topic data-source adapter layer."""
from __future__ import annotations


class TopicSourceError(RuntimeError):
    """Raised when all Strategy4 topic sources fail."""


class TopicSourceService:
    """AkShare-first topic source facade.

    The production fetch is intentionally explicit: when AkShare adapters are
    not available, callers receive a clear error instead of fake hot topics.
    Tests can inject a callable topic source into ``scan_strategy4_all``.
    """

    def fetch_topics(self) -> list[dict]:
        try:
            import akshare as ak
        except Exception as exc:  # pragma: no cover - depends on optional runtime import
            raise TopicSourceError(f"AKSHARE_IMPORT_FAILED: {exc}") from exc

        sources = [
            ("concept", "stock_board_concept_name_ths"),
            ("industry", "stock_board_industry_name_ths"),
        ]
        topics: list[dict] = []
        errors: list[str] = []
        for topic_type, func_name in sources:
            func = getattr(ak, func_name, None)
            if func is None:
                errors.append(f"{func_name}: missing")
                continue
            try:
                frame = func()
                rows = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame or [])
                for idx, row in enumerate(rows):
                    topics.append(_normalize_ths_row(row, topic_type, idx))
            except Exception as exc:
                errors.append(f"{func_name}: {exc}")

        if not topics:
            raise TopicSourceError("; ".join(errors) or "AKSHARE_THS_EMPTY")
        return topics


def _normalize_ths_row(row: dict, topic_type: str, idx: int) -> dict:
    name = _pick(row, "板块", "概念名称", "行业名称", "名称", default=f"{topic_type}-{idx}")
    up = _to_float(_pick(row, "上涨家数", "上涨数", default=0))
    down = _to_float(_pick(row, "下跌家数", "下跌数", default=0))
    breadth = up / (up + down) if up + down > 0 else 0.0
    return {
        "topic_id": f"{topic_type}:{name}",
        "topic_name": str(name),
        "topic_type": topic_type,
        "source": "akshare_ths",
        "return_1d": _pct(_pick(row, "涨跌幅", "涨幅", "最新涨跌幅", default=0)),
        "return_3d": _pct(_pick(row, "3日涨幅", "三日涨幅", default=0)),
        "return_5d": _pct(_pick(row, "5日涨幅", "五日涨幅", default=0)),
        "amount_ratio": max(1.0, _to_float(_pick(row, "成交额放大倍数", "量比", default=1))),
        "net_inflow": _to_float(_pick(row, "净流入", "主力净流入", "资金净流入", default=0)),
        "breadth_ratio": breadth,
        "leader_limit_count": int(_to_float(_pick(row, "涨停家数", "涨停数", default=0))),
        "breakout": bool(_pick(row, "突破", default=False)),
        "leading_stock_code": str(_pick(row, "领涨股代码", "领涨股票代码", "代码", default="")).zfill(6)[-6:] if _pick(row, "领涨股代码", "领涨股票代码", "代码", default="") else "",
        "leading_stock_name": str(_pick(row, "领涨股票", "领涨股", "领涨股名称", default="")),
        "raw_snapshot": dict(row),
    }


def _pick(row: dict, *keys, default=None):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def _pct(value) -> float:
    number = _to_float(value)
    return number / 100 if abs(number) > 1 else number


def _to_float(value) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return 0.0
