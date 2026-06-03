# main.py
import argparse
import logging
import sys
import yaml
import os


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(config: dict):
    log_dir = config.get("output", {}).get("log_dir", "./logs")
    os.makedirs(log_dir, exist_ok=True)
    import time
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(
                os.path.join(log_dir, f"scan_{time.strftime('%Y-%m-%d')}.log"),
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )


def cmd_scan(args):
    """执行全市场或单只股票扫描。"""
    config = load_config(args.config)
    setup_logging(config)
    logger = logging.getLogger("main")

    from scanner.engine import scan_all
    from output.csv_writer import write_candidates_csv

    logger.info("=" * 60)
    logger.info("CupHandleScan - A股杯柄结构扫描")
    logger.info("=" * 60)

    result = scan_all(config)
    stats = result["stats"]
    candidates = result["candidates"]

    logger.info(f"扫描完成: {stats['total_stocks']} 只, "
                f"成功 {stats['scanned']}, 跳过 {stats['skipped']}, "
                f"候选 {stats['candidates_found']}, "
                f"耗时 {stats['elapsed_seconds']}s")

    if candidates:
        output_dir = config.get("output", {}).get("output_dir", "./output_data")
        csv_path = write_candidates_csv(candidates, output_dir)
        logger.info(f"候选列表: {csv_path}")

        strong = sum(1 for _, r in candidates if r.score >= 80)
        medium = sum(1 for _, r in candidates if 70 <= r.score < 80)
        breakout = sum(1 for _, r in candidates if r.is_breakout)
        logger.info(f"强候选: {strong}, 中等候选: {medium}, 已突破: {breakout}")
    else:
        logger.info("未发现符合条件的杯柄形态")


def cmd_analyze(args):
    """分析单只股票。"""
    print(f"Analyze {args.stock}: Phase 2 完善")


def cmd_serve(args):
    """启动 FastAPI Web 服务。"""
    import uvicorn
    config = load_config(args.config)
    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = args.port or server_cfg.get("port", 8080)
    uvicorn.run("server:app", host=host, port=port, reload=True)


def cmd_schedule(args):
    """仅启动定时调度器。"""
    from scheduler.scheduler import start_scheduler
    config = load_config(args.config)
    setup_logging(config)
    logger = logging.getLogger("main")
    logger.info("Starting scheduler in headless mode...")
    start_scheduler(config)
    import time
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")


def main():
    parser = argparse.ArgumentParser(
        description="CupHandleScan - A股杯柄结构自动扫描系统"
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="全市场扫描")
    p_scan.add_argument("--config", default="config.yaml", help="配置文件路径")
    p_scan.set_defaults(func=cmd_scan)

    p_analyze = sub.add_parser("analyze", help="分析单只股票")
    p_analyze.add_argument("stock", help="股票代码")
    p_analyze.set_defaults(func=cmd_analyze)

    p_serve = sub.add_parser("serve", help="启动 Web 服务")
    p_serve.add_argument("--config", default="config.yaml")
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=cmd_serve)

    p_sched = sub.add_parser("schedule", help="仅启动定时调度器")
    p_sched.add_argument("--config", default="config.yaml")
    p_sched.set_defaults(func=cmd_schedule)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
