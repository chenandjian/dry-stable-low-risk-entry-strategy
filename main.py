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
    """分析单只股票（含干稳低吸分析）。"""
    config = load_config(args.config)
    setup_logging(config)
    logger = logging.getLogger("main")

    code = args.stock
    logger.info(f"分析 {code}...")

    from scanner.sina_source import fetch_sina_daily
    from scanner.tencent_source import fetch_tencent_daily
    from scanner.index_source import fetch_market_index_daily
    from scanner.strategy_engine import (
        CupHandleStrategyEngine,
        resolve_strategy_windows,
        select_strategy_window,
    )
    from output.json_writer import write_single_analysis_json

    # Read window config via unified resolver (RECHECK-001: before any fetch)
    windows = resolve_strategy_windows(config)
    kline_days = windows.min_listing_days
    scan_window_days = windows.scan_window_days

    # Fetch data with fallback (BUG-006: pass min_listing_days)
    data = fetch_sina_daily(code, days=kline_days)
    if data is None:
        logger.info("Sina failed, trying Tencent...")
        data = fetch_tencent_daily(code, days=kline_days)

    if data is None:
        logger.error("Cannot fetch data for %s", code)
        return

    # Truncate to fixed strategy window
    strategy_data = select_strategy_window(data, scan_window_days)
    if strategy_data is None:
        logger.error(
            f"策略计算数据不足：需要 {scan_window_days} 日，实际 {len(data)} 日"
        )
        return

    logger.info(f"策略分析窗口: {len(strategy_data)} 日 (配置 {scan_window_days} 日)")

    # Market data
    market_cfg = config.get("market_environment", {})
    market_data = fetch_market_index_daily(market_cfg.get("index_symbol"))

    # Unified strategy evaluation
    engine = CupHandleStrategyEngine(config)
    evaluation = engine.evaluate_at(
        strategy_data, code=code, name="", market_data=market_data,
    )

    if not evaluation.result.found and not evaluation.dry_stable:
        logger.info(f"{code}: 未发现杯柄形态")
        return

    result = evaluation.result
    dry_stable = evaluation.dry_stable
    score = result.score

    # Build analysis output
    analysis = {
        "code": code,
        "name": result.name,
        "analysis_date": __import__('time').strftime("%Y-%m-%d %H:%M"),
        "conclusion": {
            "verdict": dry_stable["decision"]["verdict"] if dry_stable else "无结论",
            "summary": dry_stable["decision"]["summary"] if dry_stable else "",
            "score": score,
            "rating": "强候选" if score >= 80 else "中等候选" if score >= 70 else "弱候选",
            "pattern_type": dry_stable["pattern_score"]["type"] if dry_stable else "",
        },
        "volume_dry": dry_stable.get("volume_dry", {}) if dry_stable else {},
        "price_stable": dry_stable.get("price_stable", {}) if dry_stable else {},
        "pattern_score": dry_stable.get("pattern_score", {}) if dry_stable else {},
        "key_prices": dry_stable.get("key_prices", {}) if dry_stable else {},
        "risk_reward": dry_stable.get("risk_reward", {}) if dry_stable else {},
        "dry_stable_decision": dry_stable.get("decision", {}) if dry_stable else {},
        "pattern_details": {
            "cup_depth_pct": result.cup_depth_pct,
            "cup_duration": result.cup_duration,
            "handle_depth_pct": result.handle_depth_pct,
            "handle_duration": result.handle_duration,
            "lip_deviation_pct": result.lip_deviation_pct,
            "is_breakout": result.is_breakout,
            "is_volume_breakout": result.is_volume_breakout,
            "vol_multiplier": result.vol_multiplier,
            "breakout_price": result.breakout_price,
            "key_dates": {
                "left_high": result.left_high_date,
                "cup_low": result.cup_low_date,
                "right_high": result.right_high_date,
                "handle_low": result.handle_low_date,
            },
        },
    }

    # Output
    json_path = write_single_analysis_json(analysis)
    logger.info(f"分析完成: {json_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  {code} {result.name}  形态评分: {score}")
    if dry_stable:
        print(f"  量干评分: {dry_stable['volume_dry']['score']}/10  价稳评分: {dry_stable['price_stable']['score']}/10")
        print(f"  形态评级: {dry_stable['pattern_score']['type']} ({dry_stable['pattern_score']['score']}/20)")
        print(f"  风险等级: {dry_stable['risk_reward']['risk_level']}  仓位建议: {dry_stable['risk_reward']['position_advice']}")
    print(f"  最终结论: {analysis['conclusion']['verdict']}")
    print(f"{'='*60}\n")


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


def cmd_backtest(args):
    """运行历史回测。"""
    config = load_config(args.config)
    setup_logging(config)
    logger = logging.getLogger("main")

    from scanner.stock_pool import get_a_stock_pool
    from scanner.sina_source import fetch_sina_daily
    from scanner.backtester import run_backtest, backtest_report_to_dict
    from output.json_writer import write_backtest_report

    logger.info("=" * 60)
    logger.info("CupHandleScan - 历史回测")
    logger.info("=" * 60)

    # Get stock pool (sample if --sample specified)
    stocks = get_a_stock_pool(config)
    if args.sample:
        sample_n = int(args.sample)
        stocks = stocks[:sample_n]
        logger.info(f"Sampling first {sample_n} stocks")

    logger.info(f"Testing {len(stocks)} stocks...")

    # Deprecation warning for --min-score (only when user explicitly sets it)
    if args.min_score is not None:
        logger.warning(
            "WARNING: --min-score 已废弃，仅用于回测报告展示过滤，"
            "不参与策略候选判断；下一版本将删除。"
        )

    result = run_backtest(
        stocks=stocks,
        fetch_fn=fetch_sina_daily,
        config=config,
        max_stocks=args.max_stocks,
        min_score=args.min_score,
    )

    # Output
    report_dict = backtest_report_to_dict(result)
    output_dir = config.get("output", {}).get("output_dir", "./output_data")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  回测结果")
    print(f"  {'='*60}")
    print(f"  测试股票: {result.total_stocks_tested}")
    print(f"  发现形态: {result.total_patterns}")
    print(f"  ")
    print(f"  命中率 (正收益比例):")
    print(f"    5日:  {result.hit_rate_5d}%  平均收益: {result.avg_return_5d}%")
    print(f"    10日: {result.hit_rate_10d}%  平均收益: {result.avg_return_10d}%")
    print(f"    20日: {result.hit_rate_20d}%  平均收益: {result.avg_return_20d}%")
    print(f"    60日: {result.hit_rate_60d}%  平均收益: {result.avg_return_60d}%")
    print(f"  ")
    print(f"  假突破率:")
    print(f"    5日:  {result.false_breakout_rate_5d}%")
    print(f"    10日: {result.false_breakout_rate_10d}%")
    print(f"    20日: {result.false_breakout_rate_20d}%")
    print(f"  ")
    if result.by_score_range:
        print(f"  按评分分层 (10日):")
        for s in result.by_score_range:
            print(f"    {s['range']}: {s['count']}个 命中率{s['hit_rate_10d']}% 均收益{s['avg_return_10d']}%")
    print(f"  ")
    if result.by_dry_stable_verdict:
        print(f"  按干稳结论分层 (10日):")
        for verdict, s in result.by_dry_stable_verdict.items():
            print(f"    {verdict}: {s['count']}个 均收益{s['avg_ret_10d']}%")
    print(f"  ")
    if result.parameter_suggestions:
        print(f"  参数优化建议:")
        for k, v in result.parameter_suggestions.items():
            print(f"    {k}: {v}")
    print(f"{'='*60}\n")

    # Write report
    report_path = write_backtest_report(report_dict, output_dir)
    logger.info(f"Backtest report: {report_path}")


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
    p_analyze.add_argument("--config", default="config.yaml", help="配置文件路径")
    p_analyze.set_defaults(func=cmd_analyze)

    p_serve = sub.add_parser("serve", help="启动 Web 服务")
    p_serve.add_argument("--config", default="config.yaml")
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=cmd_serve)

    p_sched = sub.add_parser("schedule", help="仅启动定时调度器")
    p_sched.add_argument("--config", default="config.yaml")
    p_sched.set_defaults(func=cmd_schedule)

    p_backtest = sub.add_parser("backtest", help="历史回测")
    p_backtest.add_argument("--config", default="config.yaml", help="配置文件路径")
    p_backtest.add_argument("--sample", default=None, help="采样前N只股票（用于快速测试）")
    p_backtest.add_argument("--max-stocks", type=int, default=None, help="最多测试股票数")
    p_backtest.add_argument("--min-score", type=int, default=None, help="[已废弃] 最低形态评分，仅报告展示过滤")
    p_backtest.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
