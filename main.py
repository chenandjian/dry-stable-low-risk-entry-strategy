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
    from scanner.pattern_detector import detect_cup_handle
    from scanner.scorer import score_cup_handle_advanced
    from analyzer.volume_dry import score_volume_dry
    from analyzer.price_stable import score_price_stable
    from analyzer.pattern_score import score_pattern
    from analyzer.key_prices import calculate_key_prices
    from analyzer.risk_reward import calculate_risk_reward
    from output.json_writer import write_single_analysis_json

    # Fetch data with fallback
    data = fetch_sina_daily(code)
    if data is None:
        logger.info("Sina failed, trying Tencent...")
        data = fetch_tencent_daily(code)

    if data is None:
        logger.error(f"Cannot fetch data for {code}")
        return

    logger.info(f"Got {len(data)} days of data")

    # Cup handle detection
    cup_cfg = config.get("cup", {})
    handle_cfg = config.get("handle", {})
    breakout_cfg = config.get("breakout", {})
    handle_prefixed = {f"handle_{k}": v for k, v in handle_cfg.items()}
    pattern_cfg = {**cup_cfg, **handle_prefixed, **breakout_cfg}

    result = detect_cup_handle(data, pattern_cfg)

    if not result.found:
        logger.info(f"{code}: 未发现杯柄形态")
        return

    # Scoring
    score = score_cup_handle_advanced(result, data)
    result.score = score

    # Dry-stable analysis
    vol_dry = score_volume_dry(data)
    price_stable = score_price_stable(data)
    pattern_score_result = score_pattern(result, data)
    key_prices = calculate_key_prices(result, data)
    rr = calculate_risk_reward(
        key_prices,
        volume_dry_score=vol_dry.total_score,
        price_stable_score=price_stable.total_score,
        pattern_score=pattern_score_result.total_score,
    )

    # Build analysis output
    analysis = {
        "code": code,
        "name": result.name,
        "analysis_date": __import__('time').strftime("%Y-%m-%d %H:%M"),
        "conclusion": {
            "verdict": _final_verdict(vol_dry.total_score, price_stable.total_score,
                                       pattern_score_result.total_score, rr),
            "score": score,
            "rating": "强候选" if score >= 80 else "中等候选" if score >= 70 else "弱候选",
            "pattern_type": pattern_score_result.pattern_type,
        },
        "volume_dry": {
            "score": vol_dry.total_score,
            "verdict": vol_dry.verdict,
            "sub_scores": vol_dry.sub_scores,
            "details": vol_dry.details,
        },
        "price_stable": {
            "score": price_stable.total_score,
            "verdict": price_stable.verdict,
            "sub_scores": price_stable.sub_scores,
            "details": price_stable.details,
        },
        "pattern_score": {
            "score": pattern_score_result.total_score,
            "type": pattern_score_result.pattern_type,
            "cup_handle_score": pattern_score_result.cup_handle_score,
        },
        "key_prices": {
            "current_price": key_prices.current_price,
            "entry_zone": f"{key_prices.entry_zone_low} - {key_prices.entry_zone_high}",
            "pivot": key_prices.pivot,
            "stop_loss": key_prices.stop_loss,
            "target_1": key_prices.target_1,
            "target_2": key_prices.target_2,
        },
        "risk_reward": {
            "risk_percent": rr.risk_percent,
            "rr1": rr.rr1,
            "rr2": rr.rr2,
            "risk_level": rr.risk_level,
            "position_advice": rr.position_advice,
        },
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
    print(f"  量干评分: {vol_dry.total_score}/10  价稳评分: {price_stable.total_score}/10")
    print(f"  形态评级: {pattern_score_result.pattern_type} ({pattern_score_result.total_score}/20)")
    print(f"  风险等级: {rr.risk_level}  仓位建议: {rr.position_advice}")
    print(f"  最终结论: {analysis['conclusion']['verdict']}")
    print(f"{'='*60}\n")


def _final_verdict(vol_dry, price_stable, pattern, rr) -> str:
    """综合判断最终结论。"""
    if pattern < 8:
        return "不建议买入 - 形态不成熟"
    if vol_dry < 6:
        return "不建议买入 - 量能未干"
    if price_stable < 6:
        return "不建议买入 - 价格未稳"
    if not rr.can_buy:
        if rr.risk_percent > 8:
            return "不建议买入 - 止损空间过大"
        if rr.rr1 < 2:
            return "不建议买入 - 盈亏比不足"
    if pattern >= 13 and vol_dry >= 7 and price_stable >= 7:
        return "可低吸"
    if pattern >= 13 and vol_dry >= 6 and price_stable >= 6:
        return "突破确认"
    return "观察"


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
    p_analyze.add_argument("--config", default="config.yaml", help="配置文件路径")
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
