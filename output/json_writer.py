# output/json_writer.py
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def write_candidates_json(
    candidates: list,
    output_dir: str = "./output_data",
) -> str:
    """Write candidate stocks to JSON file with full analysis.

    Args:
        candidates: list of (stock_info, CupHandleResult, analysis_dict) tuples
        output_dir: output directory

    Returns:
        file path
    """
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(output_dir, f"candidates_{date_str}.json")

    output = []
    for item in candidates:
        if len(item) == 3:
            stock, result, analysis = item
        else:
            stock, result = item
            analysis = {}

        entry = {
            "code": result.code,
            "name": result.name,
            "score": result.score,
            "rating": _rating(result.score),
            "breakout": {
                "is_breakout": result.is_breakout,
                "is_volume_breakout": result.is_volume_breakout,
                "breakout_price": result.breakout_price,
                "volume_multiplier": result.vol_multiplier,
            },
            "pattern": {
                "cup_depth_pct": result.cup_depth_pct,
                "cup_duration": result.cup_duration,
                "handle_depth_pct": result.handle_depth_pct,
                "handle_duration": result.handle_duration,
                "lip_deviation_pct": result.lip_deviation_pct,
            },
            "key_dates": {
                "left_high": result.left_high_date,
                "cup_low": result.cup_low_date,
                "right_high": result.right_high_date,
                "handle_low": result.handle_low_date,
            },
            "key_prices": {
                "left_high": result.left_high_price,
                "cup_low": result.cup_low_price,
                "right_high": result.right_high_price,
                "handle_low": result.handle_low_price,
            },
            "latest": {
                "close": stock.get("latest_close", 0),
                "turnover": stock.get("latest_turnover", 0),
            },
        }

        # Add dry-stable analysis if available
        if analysis:
            entry["dry_stable_analysis"] = analysis

        output.append(entry)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"JSON written: {filepath} ({len(output)} candidates)")
    return filepath


def write_single_analysis_json(
    analysis: dict,
    output_dir: str = "./output_data",
) -> str:
    """Write single stock detailed analysis to JSON."""
    os.makedirs(output_dir, exist_ok=True)
    code = analysis.get("code", "unknown")
    filepath = os.path.join(output_dir, f"analysis_{code}.json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    return filepath


def _rating(score: int) -> str:
    if score >= 80:
        return "强候选"
    elif score >= 70:
        return "中等候选"
    elif score >= 60:
        return "弱候选"
    return "不推荐"
