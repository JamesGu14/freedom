from __future__ import annotations

from typing import Any

from app.signals.patterns.detectors import (
    detect_accelerating_uptrend,
    detect_air_refueling,
    detect_attack_forcing_line,
    detect_beauty_shoulder,
    detect_black_three_soldiers,
    detect_bollinger_breakout,
    detect_bullish_cannon,
    detect_bullish_vanguard,
    detect_buy_macd_kdj_double_cross,
    detect_buy_rsi_rebound,
    detect_buy_volume_breakout_20d,
    detect_climbing_slope,
    detect_dark_cloud_cover,
    detect_descending_channel,
    detect_desperate_counterattack,
    detect_double_needle_bottom,
    detect_dragon_out_of_sea,
    detect_evening_star,
    detect_five_ma_rising,
    detect_flag_formation,
    detect_gap_down,
    detect_gap_up,
    detect_golden_needle_bottom,
    detect_golden_pit,
    detect_golden_spider,
    detect_hammer,
    detect_immortal_pointing,
    detect_inverted_hammer,
    detect_limit_up_double_cannon,
    detect_limit_up_return_spear,
    detect_long_lower_shadow,
    detect_long_upper_shadow,
    detect_ma_bearish_alignment,
    detect_ma_bullish_alignment,
    detect_ma_convergence_breakout,
    detect_morning_doji_star,
    detect_old_duck_head,
    detect_one_yang_finger,
    detect_one_yang_three_lines,
    detect_platform_breakout,
    detect_red_three_soldiers,
    detect_rising_sun,
    detect_rounding_bottom,
    detect_rounding_top,
    detect_sell_macd_kdj_double_cross,
    detect_sell_rsi_fall,
    detect_sell_volume_breakdown_20d,
    detect_small_yang_steps,
    detect_three_crows,
    detect_tower_top,
    detect_treasure_basin,
    detect_v_reversal,
    detect_w_bottom,
    detect_water_lily,
    detect_yang_engulfs_yin,
    detect_ascending_channel,
)


def compute_pattern_flags_at(
    *,
    today: dict[str, Any],
    prev: dict[str, Any],
    prev2: dict[str, Any],
    prior_window: list[dict[str, Any]],
    today_limit: dict[str, Any] | None,
    prev_limit: dict[str, Any] | None,
) -> dict[str, bool]:
    """Compute pattern flags from pre-built context. Returns only truthy flags."""
    flags: dict[str, bool] = {}

    flags["ma_bullish_alignment"] = detect_ma_bullish_alignment(today, prev)
    flags["ma_bearish_alignment"] = detect_ma_bearish_alignment(today, prev)
    flags["five_ma_rising"] = detect_five_ma_rising(today)
    flags["ascending_channel"] = detect_ascending_channel(today, prior_window)
    flags["accelerating_uptrend"] = detect_accelerating_uptrend(today, prev, prev2)
    flags["climbing_slope"] = detect_climbing_slope(today, prior_window)
    flags["descending_channel"] = detect_descending_channel(today, prior_window)
    
    flags["bollinger_breakout"] = detect_bollinger_breakout(today, prev)
    flags["platform_breakout"] = detect_platform_breakout(today, prior_window)
    flags["ma_convergence_breakout"] = detect_ma_convergence_breakout(today, prior_window)
    flags["water_lily"] = detect_water_lily(today, prev)
    flags["one_yang_three_lines"] = detect_one_yang_three_lines(today)
    flags["dragon_out_of_sea"] = detect_dragon_out_of_sea(today, prev)
    
    flags["w_bottom"] = detect_w_bottom(today, prior_window)
    flags["rounding_bottom"] = detect_rounding_bottom(today, prior_window)
    flags["yang_engulfs_yin"] = detect_yang_engulfs_yin(today, prev)
    flags["morning_doji_star"] = detect_morning_doji_star(today, prev, prev2)
    flags["double_needle_bottom"] = detect_double_needle_bottom(today, prev, prior_window)
    flags["golden_needle_bottom"] = detect_golden_needle_bottom(today, prev)
    flags["hammer"] = detect_hammer(today)
    flags["v_reversal"] = detect_v_reversal(today, prior_window)
    flags["dark_cloud_cover"] = detect_dark_cloud_cover(today, prev)
    
    flags["red_three_soldiers"] = detect_red_three_soldiers(today, prev, prev2)
    flags["black_three_soldiers"] = detect_black_three_soldiers(today, prev, prev2)
    flags["three_crows"] = detect_three_crows(today, prev, prev2)
    flags["bullish_cannon"] = detect_bullish_cannon(today, prev, prev2)
    flags["rising_sun"] = detect_rising_sun(today, prev)
    flags["evening_star"] = detect_evening_star(today, prev, prev2)
    flags["inverted_hammer"] = detect_inverted_hammer(today)

    flags["limit_up_double_cannon"] = detect_limit_up_double_cannon(today, prev, prev2, today_limit, prev_limit)
    flags["limit_up_return_spear"] = detect_limit_up_return_spear(today, prev, today_limit)
    flags["immortal_pointing"] = detect_immortal_pointing(today, prev)
    flags["old_duck_head"] = detect_old_duck_head(today, prior_window)
    flags["air_refueling"] = detect_air_refueling(today, prev, prior_window)
    flags["beauty_shoulder"] = detect_beauty_shoulder(today, prior_window)
    flags["golden_pit"] = detect_golden_pit(today, prior_window)
    flags["treasure_basin"] = detect_treasure_basin(today, prior_window)
    flags["flag_formation"] = detect_flag_formation(today, prior_window)
    flags["one_yang_finger"] = detect_one_yang_finger(today, prev)
    flags["desperate_counterattack"] = detect_desperate_counterattack(today, prior_window)
    flags["long_upper_shadow"] = detect_long_upper_shadow(today)
    flags["long_lower_shadow"] = detect_long_lower_shadow(today, prev)
    flags["small_yang_steps"] = detect_small_yang_steps(today, prev, prev2)
    flags["golden_spider"] = detect_golden_spider(today, prev)
    flags["attack_forcing_line"] = detect_attack_forcing_line(today, prev)
    flags["bullish_vanguard"] = detect_bullish_vanguard(today, prev)
    flags["gap_up"] = detect_gap_up(today, prev)
    flags["gap_down"] = detect_gap_down(today, prev)
    flags["rounding_top"] = detect_rounding_top(today, prior_window)
    flags["tower_top"] = detect_tower_top(today, prior_window)
    
    flags["buy_macd_kdj_double_cross"] = detect_buy_macd_kdj_double_cross(today, prev)
    flags["buy_volume_breakout_20d"] = detect_buy_volume_breakout_20d(today, prior_window)
    flags["buy_rsi_rebound"] = detect_buy_rsi_rebound(today, prev)
    flags["sell_macd_kdj_double_cross"] = detect_sell_macd_kdj_double_cross(today, prev)
    flags["sell_volume_breakdown_20d"] = detect_sell_volume_breakdown_20d(today, prior_window)
    flags["sell_rsi_fall"] = detect_sell_rsi_fall(today, prev)

    return {k: v for k, v in flags.items() if v}


def compute_pattern_flags_for_stock(
    rows: list[dict[str, Any]],
    limit_rows: list[dict[str, Any]],
    *,
    target_date: str,
) -> dict[str, bool]:
    by_date = {str(row["trade_date"]): row for row in rows}
    dates = sorted(by_date)
    if target_date not in by_date or len(dates) < 3:
        return {}
    index = dates.index(target_date)
    if index < 2:
        return {}

    limit_by_date = {str(row["trade_date"]): row for row in limit_rows}
    return compute_pattern_flags_at(
        today=by_date[target_date],
        prev=by_date[dates[index - 1]],
        prev2=by_date[dates[index - 2]],
        prior_window=[by_date[d] for d in dates[max(0, index - 20) : index]],
        today_limit=limit_by_date.get(target_date),
        prev_limit=limit_by_date.get(dates[index - 1]),
    )
