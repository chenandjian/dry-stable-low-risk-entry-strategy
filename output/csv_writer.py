# output/csv_writer.py
import csv
import os
import logging
from datetime import datetime
from scanner.pattern_detector import CupHandleResult

logger = logging.getLogger(__name__)

CSV_HEADER = [
    "股票代码", "股票名称", "形态评分", "信号等级",
    "突破状态", "放量确认", "最新收盘价", "突破位",
    "距突破位比例", "杯体回撤深度", "杯体周期",
    "柄部回撤幅度", "柄部周期",
    "左杯口日期", "杯底日期", "右杯口日期", "柄部低点日期",
    "最近20日平均成交额", "最新成交额", "放量倍数",
]


def write_candidates_csv(
    candidates: list[tuple[dict, CupHandleResult]],
    output_dir: str = "./output_data",
) -> str:
    """写入候选股票 CSV 文件。

    Args:
        candidates: [(stock_info, cup_handle_result), ...]
        output_dir: 输出目录

    Returns:
        CSV 文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"candidates_{date_str}.csv"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)

        for stock, result in candidates:
            # 分级
            if result.score >= 80:
                rating = "强候选"
            elif result.score >= 70:
                rating = "中等候选"
            elif result.score >= 60:
                rating = "弱候选"
            else:
                continue  # < 60 分不输出

            # 距突破位比例
            latest_close = stock.get("latest_close", 0)
            bp = result.breakout_price
            dist_pct = f"{(latest_close - bp) / bp * 100:+.1f}%" if bp > 0 else "N/A"

            writer.writerow([
                stock.get("code", ""),
                stock.get("name", ""),
                result.score,
                rating,
                "已突破" if result.is_breakout else "未突破",
                "是" if result.is_volume_breakout else "否",
                f"{latest_close:.2f}",
                f"{result.breakout_price:.2f}",
                dist_pct,
                f"{result.cup_depth_pct:.1f}%",
                result.cup_duration,
                f"{result.handle_depth_pct:.1f}%",
                result.handle_duration,
                result.left_high_date,
                result.cup_low_date,
                result.right_high_date,
                result.handle_low_date,
                stock.get("avg_turnover_20", "N/A"),
                stock.get("latest_turnover", "N/A"),
                f"{result.vol_multiplier:.1f}×",
            ])

    logger.info(f"CSV written: {filepath} ({len(candidates)} candidates)")
    return filepath
