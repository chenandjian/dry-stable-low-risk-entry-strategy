import argparse
import json
import sys

from .daily_data import diagnose
from .repository import USRepository


def main(argv=None):
    parser = argparse.ArgumentParser(description="US free-only data diagnostics, not a strategy scan")
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--db", default="data/us_market.db")
    parser.add_argument("--count", type=int, default=1100)
    parser.add_argument("--adjustment", choices=["none", "forward", "forward_additive"], default="forward")
    args = parser.parse_args(argv)
    repo = USRepository(args.db)
    failed = False
    for symbol in args.symbols:
        try:
            result = diagnose(repo, symbol, count=args.count, adjustment=args.adjustment)
            print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False))
        except Exception as exc:
            failed = True
            print(json.dumps({"symbol": symbol, "status": "FAILED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
