from __future__ import annotations

import csv
import io
import re


def provider_symbol(value: str) -> str:
    """Preserve share-class dots; never apply the A-share code parser."""
    symbol = value.strip().upper()
    ticker = symbol[:-3] if symbol.endswith(".US") else symbol
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)?", ticker):
        raise ValueError(f"invalid US symbol: {value!r}")
    if ticker.endswith((".SH", ".SZ", ".HK", ".BJ", ".US")):
        raise ValueError(f"foreign or repeated market suffix: {value!r}")
    return ticker + ".US"


def parse_directory(text: str, *, kind: str) -> dict:
    """Parse current Nasdaq directories, not a historical point-in-time universe."""
    if kind not in {"nasdaqlisted", "otherlisted"}:
        raise ValueError("unsupported directory kind")
    symbol_key = "Symbol" if kind == "nasdaqlisted" else "ACT Symbol"
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter="|")
    required = {symbol_key, "Security Name", "ETF", "Test Issue"}
    if kind == "otherlisted":
        required.add("Exchange")
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("missing official directory columns")
    instruments, seen, created = [], set(), None
    exchanges = {"N": "NYSE", "P": "NYSE ARCA", "A": "NYSE MKT", "Z": "BATS", "V": "IEXG"}
    for row in reader:
        raw_symbol = (row.get(symbol_key) or "").strip()
        if raw_symbol.startswith("File Creation Time:"):
            created = raw_symbol.partition(":")[2].strip()
            continue
        if not raw_symbol:
            continue
        if raw_symbol in seen:
            raise ValueError(f"duplicate directory symbol: {raw_symbol}")
        seen.add(raw_symbol)
        try:
            symbol = provider_symbol(raw_symbol)
        except ValueError:
            symbol = None
        name = row["Security Name"] or ""
        lower_name = name.lower()
        etf, test = row["ETF"], row["Test Issue"]
        security_type = "UNKNOWN"
        if etf == "Y":
            security_type = "ETF"
        elif etf == "N" and re.search(r"\b(common stock|ordinary shares)\b", lower_name):
            if not re.search(r"\b(preferred|preference|warrants?|rights?|units?|depositary|adrs?|ads)\b", lower_name):
                security_type = "COMMON_STOCK"
        exchange = "NASDAQ" if kind == "nasdaqlisted" else exchanges.get(row["Exchange"], "UNKNOWN")
        instruments.append({
            "symbol": symbol, "name": name, "exchange": exchange,
            "security_type": security_type,
            "eligible": symbol is not None and security_type == "COMMON_STOCK" and test == "N" and exchange != "UNKNOWN",
            "mapping_status": "PARSED_NOT_PROVIDER_VERIFIED" if symbol else "UNSUPPORTED_SYMBOL",
            "directory_kind": kind, "raw": row,
        })
    if not instruments:
        raise ValueError("empty directory; do not replace a previous universe")
    return {"instruments": instruments, "file_created_raw": created}
