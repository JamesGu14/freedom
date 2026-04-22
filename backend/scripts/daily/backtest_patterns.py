#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_store import list_daily
from app.data.mongo import get_collection
from app.data.mongo_daily_stock_signals import list_daily_stock_signal_dates

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest pattern signals")
    parser.add_argument("--start-date", type=str, default=None, help="YYYYMMDD")
    parser.add_argument("--end-date", type=str, default=None, help="YYYYMMDD")
    parser.add_argument("--pattern", type=str, default=None, help="Specific pattern to test")
    parser.add_argument("--hold-days", type=int, default=5, help="Hold for N days")
    parser.add_argument("--min-samples", type=int, default=30, help="Minimum samples for valid stats")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def get_forward_return(ts_code: str, trade_date: str, hold_days: int) -> float | None:
    rows = list_daily(ts_code)
    if not rows:
        return None
    
    dates = [str(r["trade_date"]) for r in rows]
    prices = {str(r["trade_date"]): float(r["close"]) for r in rows}
    
    if trade_date not in prices:
        return None
    
    try:
        idx = dates.index(trade_date)
    except ValueError:
        return None
    
    target_idx = idx + hold_days
    if target_idx >= len(dates):
        return None
    
    entry_price = prices[trade_date]
    exit_price = prices[dates[target_idx]]
    
    if entry_price <= 0:
        return None
    
    return round((exit_price - entry_price) / entry_price * 100, 2)


def analyze_patterns(start_date: str, end_date: str, hold_days: int, min_samples: int, specific_pattern: str | None = None) -> dict:
    query = {"trade_date": {"$gte": start_date, "$lte": end_date}}
    
    pattern_stats: dict[str, dict] = {}
    resonance_stats: dict[str, dict] = {
        "normal": {"returns": [], "wins": 0, "total": 0},
        "strong": {"returns": [], "wins": 0, "total": 0},
        "very_strong": {"returns": [], "wins": 0, "total": 0},
    }
    
    for doc in get_collection("daily_stock_pattern_resonance").find(query, {"_id": 0}):
        trade_date = doc["trade_date"]
        signal_side = doc.get("signal_side", "")
        resonance_level = doc.get("resonance_level", "")
        
        for stock in doc.get("stocks", []):
            ts_code = stock["ts_code"]
            patterns = stock.get("patterns", [])
            
            ret = get_forward_return(ts_code, trade_date, hold_days)
            if ret is None:
                continue
            
            for pattern in patterns:
                if specific_pattern and pattern != specific_pattern:
                    continue
                
                if pattern not in pattern_stats:
                    pattern_stats[pattern] = {"returns": [], "wins": 0, "total": 0}
                
                pattern_stats[pattern]["returns"].append(ret)
                pattern_stats[pattern]["total"] += 1
                if ret > 0:
                    pattern_stats[pattern]["wins"] += 1
            
            if resonance_level in resonance_stats:
                resonance_stats[resonance_level]["returns"].append(ret)
                resonance_stats[resonance_level]["total"] += 1
                if ret > 0:
                    resonance_stats[resonance_level]["wins"] += 1
    
    results = {
        "patterns": {},
        "resonance": {},
        "hold_days": hold_days,
        "date_range": f"{start_date} to {end_date}",
    }
    
    for pattern, stats in sorted(pattern_stats.items(), key=lambda x: -x[1]["total"]):
        if stats["total"] < min_samples:
            continue
        
        returns = stats["returns"]
        avg_return = sum(returns) / len(returns)
        win_rate = stats["wins"] / stats["total"] * 100
        
        results["patterns"][pattern] = {
            "total_signals": stats["total"],
            "win_rate": round(win_rate, 1),
            "avg_return": round(avg_return, 2),
            "max_return": round(max(returns), 2),
            "min_return": round(min(returns), 2),
        }
    
    for level, stats in resonance_stats.items():
        if stats["total"] < min_samples:
            continue
        
        returns = stats["returns"]
        avg_return = sum(returns) / len(returns)
        win_rate = stats["wins"] / stats["total"] * 100
        
        results["resonance"][level] = {
            "total_signals": stats["total"],
            "win_rate": round(win_rate, 1),
            "avg_return": round(avg_return, 2),
            "max_return": round(max(returns), 2),
            "min_return": round(min(returns), 2),
        }
    
    return results


def print_results(results: dict) -> None:
    print(f"\n{'='*80}")
    print(f"Pattern Backtest Results")
    print(f"Date Range: {results['date_range']}")
    print(f"Hold Days: {results['hold_days']}")
    print(f"{'='*80}\n")
    
    print("Resonance Level Performance:")
    print(f"{'Level':<15} {'Signals':<10} {'Win Rate':<12} {'Avg Return':<12} {'Max':<10} {'Min':<10}")
    print("-" * 80)
    for level, stats in results["resonance"].items():
        print(f"{level:<15} {stats['total_signals']:<10} {stats['win_rate']:<11.1f}% {stats['avg_return']:<11.2f}% {stats['max_return']:<9.2f}% {stats['min_return']:<9.2f}%")
    
    print(f"\n{'='*80}")
    print("Individual Pattern Performance (sorted by sample size):")
    print(f"{'Pattern':<25} {'Signals':<10} {'Win Rate':<12} {'Avg Return':<12} {'Max':<10} {'Min':<10}")
    print("-" * 80)
    
    from app.signals.patterns.config import get_pattern_category_label
    
    for pattern, stats in sorted(results["patterns"].items(), key=lambda x: -x[1]["total_signals"])[:30]:
        label = get_pattern_category_label(pattern)
        print(f"{label:<25} {stats['total_signals']:<10} {stats['win_rate']:<11.1f}% {stats['avg_return']:<11.2f}% {stats['max_return']:<9.2f}% {stats['min_return']:<9.2f}%")
    
    print(f"\n{'='*80}\n")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    
    dates = list_daily_stock_signal_dates(limit=365*10)
    if not dates:
        logger.error("No signal dates found")
        return
    
    start_date = normalize_date(args.start_date) or dates[-1]
    end_date = normalize_date(args.end_date) or dates[0]
    
    logger.info(f"Analyzing patterns from {start_date} to {end_date}, hold_days={args.hold_days}")
    
    results = analyze_patterns(
        start_date=start_date,
        end_date=end_date,
        hold_days=args.hold_days,
        min_samples=args.min_samples,
        specific_pattern=args.pattern,
    )
    
    print_results(results)


if __name__ == "__main__":
    main()
