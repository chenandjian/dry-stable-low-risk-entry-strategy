import argparse
import json
import sys

from .daily_data import diagnose
from .repository import USRepository
from .service import acquire_batch, run_research


def main(argv=None):
    parser = argparse.ArgumentParser(description="US free-only data diagnostics, not a strategy scan")
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--db", default="data/us_market.db")
    parser.add_argument("--count", type=int, default=1100)
    parser.add_argument("--adjustment", choices=["none", "forward", "forward_additive"], default="forward")
    parser.add_argument("--sync", action="store_true", help="batch acquisition into independent US history")
    parser.add_argument("--scan", action="store_true", help="acquire then run ORIGINAL Strategy6 research without indexes")
    parser.add_argument("--local-only", action="store_true", help="research from fresh local US history only")
    parser.add_argument("--force", action="store_true", help="ignore successful fetch cache")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--as-of", help="explicit completed US session for historical signal research")
    args = parser.parse_args(argv)
    repo = USRepository(args.db)
    if args.sync or args.scan or args.local_only:
        if args.adjustment != 'forward':
            parser.error('US acquisition/research requires forward; other modes are diagnostic-only')
        acquisition = None
        if not args.local_only:
            acquisition = acquire_batch(repo, args.symbols, count=args.count,
                                        batch_size=args.batch_size, force=args.force,
                                        as_of=args.as_of,
                                        progress=lambda event: print(json.dumps(event), file=sys.stderr))
            print(json.dumps(acquisition, ensure_ascii=False))
        if args.scan or args.local_only:
            symbols = args.symbols if acquisition is None else [stock['symbol'] for stock in acquisition['stocks'] if stock['status'] != 'FAILED']
            if symbols:
                result = run_research(repo, symbols, as_of=args.as_of)
                print(json.dumps(result, ensure_ascii=False))
                return int(bool(result['failed'] or (acquisition and acquisition['failed'])))
            return 1
        return int(bool(acquisition['failed']))
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
