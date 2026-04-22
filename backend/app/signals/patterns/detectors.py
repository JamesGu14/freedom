from __future__ import annotations

from typing import Any


def detect_ma_bullish_alignment(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """均线多头: MA5 > MA10 > MA20 > MA60 且昨日不满足"""
    return (today["ma5"] > today["ma10"] > today["ma20"] > today["ma60"] and
            not (prev["ma5"] > prev["ma10"] > prev["ma20"] > prev["ma60"]))


def detect_ma_bearish_alignment(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """均线空头: MA5 < MA10 < MA20 < MA60 且昨日不满足"""
    return (today["ma5"] < today["ma10"] < today["ma20"] < today["ma60"] and
            not (prev["ma5"] < prev["ma10"] < prev["ma20"] < prev["ma60"]))


def detect_five_ma_rising(today: dict[str, Any]) -> bool:
    """五线顺上: 收盘价在5/10/20/60/120/250日均线之上"""
    return (today["close_qfq"] > today["ma5"] > today["ma10"] > today["ma20"] >
            today["ma60"] > today["ma90"] > today["ma250"])


def detect_bollinger_breakout(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """布林突破: 收盘价突破布林上轨"""
    return today["close_qfq"] > today["boll_upper"] and prev["close_qfq"] <= prev["boll_upper"]


def detect_platform_breakout(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    """突破平台: 突破前20日高点且放量"""
    if not prior_window:
        return False
    prior_high = max(float(item["close_qfq"]) for item in prior_window)
    return today["close_qfq"] > prior_high and today["volume_ratio"] > 1.5


def detect_ma_convergence_breakout(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    """均线粘合突破: MA5/10/20收敛后向上突破"""
    if len(prior_window) < 10:
        return False
    recent = prior_window[-10:]
    ma_spreads = [abs(float(item["ma5"]) - float(item["ma20"])) / float(item["ma20"]) for item in recent]
    avg_spread = sum(ma_spreads) / len(ma_spreads)
    return avg_spread < 0.02 and today["close_qfq"] > today["ma5"] and today["volume_ratio"] > 1.5


def detect_water_lily(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """出水芙蓉: 巨量阳线突破5/10/20日均线"""
    return (today["close_qfq"] > today["open"] and
            today["close_qfq"] > today["ma5"] > prev["ma5"] and
            today["close_qfq"] > today["ma10"] > prev["ma10"] and
            today["close_qfq"] > today["ma20"] > prev["ma20"] and
            today["volume_ratio"] > 2.0)


def detect_one_yang_three_lines(today: dict[str, Any]) -> bool:
    """一阳穿三线: 阳线同时突破5/10/30日均线"""
    return (today["close_qfq"] > today["open"] and
            today["close_qfq"] > today["ma5"] and
            today["close_qfq"] > today["ma10"] and
            today["close_qfq"] > today["ma30"] and
            today["open"] < today["ma30"])


def detect_yang_engulfs_yin(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """阳包阴: 阳线实体完全吞没前日阴线"""
    return (today["close_qfq"] > today["open"] and
            prev["close_qfq"] < prev["open"] and
            today["open"] < prev["close_qfq"] and
            today["close_qfq"] > prev["open"])


def detect_hammer(today: dict[str, Any]) -> bool:
    """锤子线: 下影线 >= 2倍实体，无上影线或极短"""
    body = abs(today["close_qfq"] - today["open"])
    lower_shadow = min(today["close_qfq"], today["open"]) - today["low"]
    upper_shadow = today["high"] - max(today["close_qfq"], today["open"])
    return body > 0 and lower_shadow >= 2 * body and upper_shadow <= body * 0.1


def detect_red_three_soldiers(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any]) -> bool:
    """红三兵: 连续3根阳线，收盘价逐步抬高"""
    return (today["close_qfq"] > today["open"] and
            prev["close_qfq"] > prev["open"] and
            prev2["close_qfq"] > prev2["open"] and
            today["close_qfq"] > prev["close_qfq"] > prev2["close_qfq"])


def detect_black_three_soldiers(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any]) -> bool:
    """黑三兵: 连续3根阴线，收盘价逐步降低"""
    return (today["close_qfq"] < today["open"] and
            prev["close_qfq"] < prev["open"] and
            prev2["close_qfq"] < prev2["open"] and
            today["close_qfq"] < prev["close_qfq"] < prev2["close_qfq"])


def detect_morning_doji_star(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any]) -> bool:
    """早晨十字星: 长阴 + 十字星 + 长阳"""
    prev2_body = abs(prev2["close_qfq"] - prev2["open"])
    prev2_range = prev2["high"] - prev2["low"]
    prev_body = abs(prev["close_qfq"] - prev["open"])
    prev_range = prev["high"] - prev["low"]
    today_body = abs(today["close_qfq"] - today["open"])
    
    return (prev2["close_qfq"] < prev2["open"] and prev2_body > prev2_range * 0.5 and
            prev_body < prev_range * 0.1 and
            today["close_qfq"] > today["open"] and today_body > prev2_body * 0.8)


def detect_limit_up_double_cannon(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any], 
                                  today_limit: dict[str, Any], prev_limit: dict[str, Any]) -> bool:
    """涨停双响炮: 涨停 + 调整 + 再次涨停"""
    if not today_limit or not prev_limit:
        return False
    prev2_limit_up = prev2["close_qfq"] >= prev_limit.get("up_limit", float("inf")) * 0.99
    today_limit_up = today["close_qfq"] >= today_limit.get("up_limit", float("inf")) * 0.99
    prev_consolidation = abs(prev["close_qfq"] - prev["open"]) / prev["open"] < 0.03
    return prev2_limit_up and prev_consolidation and today_limit_up


def detect_golden_spider(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """金蜘蛛: MA5/10/20从下行转为上行并收敛"""
    return (today["ma5"] > today["ma10"] > today["ma20"] and
            prev["ma5"] < prev["ma10"] and
            abs(today["ma5"] - today["ma20"]) / today["ma20"] < 0.03)


def detect_dragon_out_of_sea(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """蛟龙出海: 长阳突破所有均线"""
    return (today["close_qfq"] > today["open"] and
            today["close_qfq"] > max(today["ma5"], today["ma10"], today["ma20"], today["ma60"]) and
            prev["close_qfq"] < prev["ma60"] and
            today["volume_ratio"] > 2.0)


def detect_bullish_cannon(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any]) -> bool:
    """多方炮: 两阳夹一阴"""
    return (prev2["close_qfq"] > prev2["open"] and
            prev["close_qfq"] < prev["open"] and
            today["close_qfq"] > today["open"] and
            today["close_qfq"] > prev2["close_qfq"])


def detect_rising_sun(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """旭日东升: 阴线后高开高走阳线"""
    return (prev["close_qfq"] < prev["open"] and
            today["open"] > prev["close_qfq"] and
            today["close_qfq"] > today["open"] and
            today["close_qfq"] > prev["open"])


def detect_desperate_counterattack(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    """绝地反击: 长期下跌后突然大阳线"""
    if len(prior_window) < 20:
        return False
    recent_trend = sum(1 for item in prior_window[-20:] if item["close_qfq"] < item["open"])
    return recent_trend >= 12 and today["pct_chg"] > 5.0


def detect_long_upper_shadow(today: dict[str, Any]) -> bool:
    """长上影巨震洗盘: 长上影线，实体较小"""
    body = abs(today["close_qfq"] - today["open"])
    upper_shadow = today["high"] - max(today["close_qfq"], today["open"])
    total_range = today["high"] - today["low"]
    return total_range > 0 and upper_shadow > total_range * 0.6 and body < total_range * 0.2


def detect_small_yang_steps(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any]) -> bool:
    """碎布小阳: 连续小阳线，收盘价在5/10日均线上方"""
    return (abs(today["pct_chg"]) < 3.0 and today["close_qfq"] > today["open"] and
            abs(prev["pct_chg"]) < 3.0 and prev["close_qfq"] > prev["open"] and
            abs(prev2["pct_chg"]) < 3.0 and prev2["close_qfq"] > prev2["open"] and
            today["close_qfq"] > today["ma5"] > today["ma10"])


def detect_bullish_vanguard(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    """多头尖兵: 带长上影线的试探性上涨"""
    body = abs(today["close_qfq"] - today["open"])
    upper_shadow = today["high"] - max(today["close_qfq"], today["open"])
    return (today["close_qfq"] > today["open"] and
            upper_shadow > body * 2 and
            today["close_qfq"] > prev["close_qfq"] and
            today["volume_ratio"] > 1.5)


def detect_ascending_channel(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 15:
        return False
    recent = prior_window[-15:]
    lows = [float(item["low"]) for item in recent]
    highs = [float(item["high"]) for item in recent]
    return (all(lows[i] <= lows[i + 1] for i in range(len(lows) - 1)) and
            all(highs[i] <= highs[i + 1] for i in range(len(highs) - 1)) and
            today["close_qfq"] > today["ma20"] > today["ma60"])


def detect_accelerating_uptrend(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any]) -> bool:
    return (today["close_qfq"] > today["open"] and
            prev["close_qfq"] > prev["open"] and
            prev2["close_qfq"] > prev2["open"] and
            today["pct_chg"] > prev["pct_chg"] > prev2["pct_chg"] > 0 and
            today["pct_chg"] > 3.0)


def detect_climbing_slope(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 10:
        return False
    recent = prior_window[-10:]
    return (all(abs(float(item["pct_chg"])) < 3.0 for item in recent) and
            sum(1 for item in recent if item["close_qfq"] > item["open"]) >= 7 and
            today["close_qfq"] > today["ma5"] > today["ma10"] > today["ma20"] and
            today["close_qfq"] > today["ma5"] * 0.98)


def detect_descending_channel(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 15:
        return False
    recent = prior_window[-15:]
    lows = [float(item["low"]) for item in recent]
    highs = [float(item["high"]) for item in recent]
    return (all(lows[i] >= lows[i + 1] for i in range(len(lows) - 1)) and
            all(highs[i] >= highs[i + 1] for i in range(len(highs) - 1)) and
            today["close_qfq"] < today["ma20"] < today["ma60"])


def detect_w_bottom(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 20:
        return False
    recent = prior_window[-20:]
    lows = [float(item["low"]) for item in recent]
    min1_idx = lows.index(min(lows))
    if min1_idx < 5 or min1_idx > 14:
        return False
    second_half = lows[min1_idx + 3:]
    if not second_half:
        return False
    min2 = min(second_half)
    return (abs(min2 - lows[min1_idx]) / lows[min1_idx] < 0.03 and
            today["close_qfq"] > today["open"] and
            today["close_qfq"] > max(float(item["high"]) for item in recent[min1_idx:min1_idx + 3]))


def detect_rounding_bottom(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 20:
        return False
    recent = prior_window[-20:]
    lows = [float(item["low"]) for item in recent]
    mid = len(lows) // 2
    return (all(lows[i] >= lows[i + 1] for i in range(mid)) and
            all(lows[i] <= lows[i + 1] for i in range(mid, len(lows) - 1)) and
            today["close_qfq"] > today["open"] and
            today["close_qfq"] > today["ma20"])


def detect_double_needle_bottom(today: dict[str, Any], prev: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 5:
        return False
    body = abs(today["close_qfq"] - today["open"])
    lower_shadow = min(today["close_qfq"], today["open"]) - today["low"]
    prev_body = abs(prev["close_qfq"] - prev["open"])
    prev_lower_shadow = min(prev["close_qfq"], prev["open"]) - prev["low"]
    return (lower_shadow > body * 2 and prev_lower_shadow > prev_body * 2 and
            abs(today["low"] - prev["low"]) / prev["low"] < 0.02 and
            today["close_qfq"] > today["open"] and
            sum(1 for item in prior_window[-5:] if item["close_qfq"] < item["open"]) >= 3)


def detect_golden_needle_bottom(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    body = abs(today["close_qfq"] - today["open"])
    lower_shadow = min(today["close_qfq"], today["open"]) - today["low"]
    upper_shadow = today["high"] - max(today["close_qfq"], today["open"])
    return (lower_shadow > body * 3 and upper_shadow < body * 0.5 and
            today["close_qfq"] > today["open"] and
            prev["close_qfq"] < prev["open"] and
            today["close_qfq"] > prev["close_qfq"])


def detect_v_reversal(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 10:
        return False
    recent = prior_window[-10:]
    mid = len(recent) // 2
    first_half = recent[:mid]
    second_half = recent[mid:]
    first_decline = (first_half[0]["close_qfq"] - first_half[-1]["close_qfq"]) / first_half[0]["close_qfq"]
    second_rise = (second_half[-1]["close_qfq"] - second_half[0]["close_qfq"]) / second_half[0]["close_qfq"]
    return (first_decline > 0.08 and second_rise > 0.05 and
            today["close_qfq"] > today["open"] and today["pct_chg"] > 3.0)


def detect_dark_cloud_cover(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    prev_body = prev["close_qfq"] - prev["open"]
    return (prev["close_qfq"] > prev["open"] and
            today["open"] > prev["close_qfq"] and
            today["close_qfq"] < today["open"] and
            today["close_qfq"] < prev["open"] + prev_body * 0.5 and
            today["close_qfq"] > prev["open"])


def detect_three_crows(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any]) -> bool:
    return (today["close_qfq"] < today["open"] and
            prev["close_qfq"] < prev["open"] and
            prev2["close_qfq"] < prev2["open"] and
            today["close_qfq"] < prev["close_qfq"] < prev2["close_qfq"] and
            today["open"] < prev["open"] and today["open"] > prev["close_qfq"] and
            prev["open"] < prev2["open"] and prev["open"] > prev2["close_qfq"])


def detect_limit_up_return_spear(today: dict[str, Any], prev: dict[str, Any], 
                                  today_limit: dict[str, Any] | None) -> bool:
    if not today_limit:
        return False
    prev_limit_up = prev["close_qfq"] >= today_limit.get("up_limit", float("inf")) * 0.99
    return (prev_limit_up and
            today["open"] > prev["close_qfq"] and
            today["close_qfq"] < today["open"] and
            today["close_qfq"] > prev["close_qfq"] * 0.97 and
            today["volume_ratio"] > 1.5)


def detect_immortal_pointing(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    body = abs(today["close_qfq"] - today["open"])
    upper_shadow = today["high"] - max(today["close_qfq"], today["open"])
    return (today["close_qfq"] > today["open"] and
            upper_shadow > body * 2 and
            today["close_qfq"] > prev["close_qfq"] and
            today["close_qfq"] > today["ma5"] > today["ma10"])


def detect_old_duck_head(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 15:
        return False
    recent = prior_window[-15:]
    ma5_vals = [float(item["ma5"]) for item in recent]
    ma10_vals = [float(item["ma10"]) for item in recent]
    ma20_vals = [float(item["ma20"]) for item in recent]
    early_alignment = all(ma5_vals[i] > ma10_vals[i] > ma20_vals[i] for i in range(5))
    mid_pullback = any(ma5_vals[i] < ma10_vals[i] for i in range(5, 10))
    late_breakout = today["ma5"] > today["ma10"] > today["ma20"] and today["close_qfq"] > today["ma5"]
    return early_alignment and mid_pullback and late_breakout


def detect_air_refueling(today: dict[str, Any], prev: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 5:
        return False
    recent = prior_window[-5:]
    limit_up_day = None
    for item in recent:
        if item["pct_chg"] > 9.5:
            limit_up_day = item
            break
    if not limit_up_day:
        return False
    return (today["close_qfq"] > today["open"] and
            today["pct_chg"] > 3.0 and
            today["volume_ratio"] > 1.5 and
            prev["volume_ratio"] < 1.0)


def detect_beauty_shoulder(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 15:
        return False
    recent = prior_window[-15:]
    return (all(item["close_qfq"] > item["ma10"] for item in recent) and
            sum(1 for item in recent if item["close_qfq"] > item["ma5"]) >= 10 and
            today["close_qfq"] > today["ma5"] > today["ma10"] > today["ma20"] and
            today["volume_ratio"] > 1.2)


def detect_golden_pit(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 15:
        return False
    recent = prior_window[-15:]
    mid = len(recent) // 2
    first_half = recent[:mid]
    second_half = recent[mid:]
    first_decline = (first_half[0]["close_qfq"] - first_half[-1]["close_qfq"]) / first_half[0]["close_qfq"]
    second_rise = (second_half[-1]["close_qfq"] - second_half[0]["close_qfq"]) / second_half[0]["close_qfq"]
    avg_vol_first = sum(float(item.get("vol", item.get("volume", 0))) for item in first_half) / len(first_half)
    avg_vol_second = sum(float(item.get("vol", item.get("volume", 0))) for item in second_half) / len(second_half)
    return (first_decline > 0.05 and second_rise > 0.03 and
            avg_vol_second > avg_vol_first * 1.5 and
            today["close_qfq"] > today["ma5"])


def detect_treasure_basin(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 20:
        return False
    recent = prior_window[-20:]
    closes = [float(item["close_qfq"]) for item in recent]
    avg_close = sum(closes) / len(closes)
    max_close = max(closes)
    min_close = min(closes)
    return (max_close / min_close < 1.08 and
            today["close_qfq"] > max_close * 0.98 and
            today["close_qfq"] > today["open"] and
            today["volume_ratio"] > 2.0 and
            today["close_qfq"] < avg_close * 1.15)


def detect_flag_formation(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 15:
        return False
    recent = prior_window[-15:]
    pole = recent[:5]
    flag = recent[5:]
    pole_rise = (pole[-1]["close_qfq"] - pole[0]["close_qfq"]) / pole[0]["close_qfq"]
    flag_high = max(float(item["high"]) for item in flag)
    flag_low = min(float(item["low"]) for item in flag)
    return (pole_rise > 0.1 and
            flag_high / flag_low < 1.05 and
            today["close_qfq"] > flag_high and
            today["volume_ratio"] > 1.5)


def detect_one_yang_finger(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    return (today["close_qfq"] > today["open"] and
            today["pct_chg"] > 5.0 and
            today["close_qfq"] > max(today["ma5"], today["ma10"], today["ma20"], today["ma60"]) and
            prev["close_qfq"] < prev["ma20"] and
            today["volume_ratio"] > 2.5)


def detect_long_lower_shadow(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    body = abs(today["close_qfq"] - today["open"])
    lower_shadow = min(today["close_qfq"], today["open"]) - today["low"]
    total_range = today["high"] - today["low"]
    return (total_range > 0 and lower_shadow > total_range * 0.6 and
            body < total_range * 0.3 and
            prev["close_qfq"] < prev["open"] and
            today["close_qfq"] > today["open"])


def detect_attack_forcing_line(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    return (prev["pct_chg"] > 9.5 and
            today["open"] > prev["close_qfq"] and
            today["close_qfq"] > today["open"] and
            today["close_qfq"] > prev["close_qfq"] and
            today["volume_ratio"] > 1.5)


def detect_buy_macd_kdj_double_cross(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    macd_golden = today["macd"] > today["macd_signal"] and prev["macd"] <= prev["macd_signal"]
    kdj_golden = today["kdj_k"] > today["kdj_d"] and prev["kdj_k"] <= prev["kdj_d"]
    return macd_golden and kdj_golden and today["kdj_k"] < 70


def detect_buy_volume_breakout_20d(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if not prior_window:
        return False
    max_20d = max(float(item["high"]) for item in prior_window)
    avg_vol = sum(float(item.get("vol", item.get("volume", 0))) for item in prior_window) / len(prior_window)
    return today["close_qfq"] > max_20d and today.get("vol", today.get("volume", 0)) > avg_vol * 2.0


def detect_buy_rsi_rebound(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    return prev["rsi6"] < 30 and today["rsi6"] > prev["rsi6"] and today["rsi6"] < 50


def detect_sell_macd_kdj_double_cross(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    macd_dead = today["macd"] < today["macd_signal"] and prev["macd"] >= prev["macd_signal"]
    kdj_dead = today["kdj_k"] < today["kdj_d"] and prev["kdj_k"] >= prev["kdj_d"]
    return macd_dead and kdj_dead and today["kdj_k"] > 30


def detect_sell_volume_breakdown_20d(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if not prior_window:
        return False
    min_20d = min(float(item["low"]) for item in prior_window)
    avg_vol = sum(float(item.get("vol", item.get("volume", 0))) for item in prior_window) / len(prior_window)
    return today["close_qfq"] < min_20d and today.get("vol", today.get("volume", 0)) > avg_vol * 2.0


def detect_sell_rsi_fall(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    return prev["rsi6"] > 70 and today["rsi6"] < prev["rsi6"] and today["rsi6"] > 50


def detect_evening_star(today: dict[str, Any], prev: dict[str, Any], prev2: dict[str, Any]) -> bool:
    prev2_body = abs(prev2["close_qfq"] - prev2["open"])
    prev2_range = prev2["high"] - prev2["low"]
    prev_body = abs(prev["close_qfq"] - prev["open"])
    prev_range = prev["high"] - prev["low"]
    today_body = abs(today["close_qfq"] - today["open"])
    return (prev2["close_qfq"] > prev2["open"] and prev2_body > prev2_range * 0.5 and
            prev_body < prev_range * 0.1 and
            today["close_qfq"] < today["open"] and today_body > prev2_body * 0.8)


def detect_inverted_hammer(today: dict[str, Any]) -> bool:
    body = abs(today["close_qfq"] - today["open"])
    upper_shadow = today["high"] - max(today["close_qfq"], today["open"])
    lower_shadow = min(today["close_qfq"], today["open"]) - today["low"]
    return body > 0 and upper_shadow >= 2 * body and lower_shadow <= body * 0.1


def detect_gap_up(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    return today["low"] > prev["high"]


def detect_gap_down(today: dict[str, Any], prev: dict[str, Any]) -> bool:
    return today["high"] < prev["low"]


def detect_rounding_top(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 20:
        return False
    recent = prior_window[-20:]
    highs = [float(item["high"]) for item in recent]
    mid = len(highs) // 2
    return (all(highs[i] <= highs[i + 1] for i in range(mid)) and
            all(highs[i] >= highs[i + 1] for i in range(mid, len(highs) - 1)) and
            today["close_qfq"] < today["open"] and
            today["close_qfq"] < today["ma20"])


def detect_tower_top(today: dict[str, Any], prior_window: list[dict[str, Any]]) -> bool:
    if len(prior_window) < 20:
        return False
    recent = prior_window[-20:]
    highs = [float(item["high"]) for item in recent]
    max_idx = highs.index(max(highs))
    if max_idx < 5 or max_idx > 14:
        return False
    left_trend = all(highs[i] <= highs[i + 1] for i in range(max_idx))
    right_trend = all(highs[i] >= highs[i + 1] for i in range(max_idx, len(highs) - 1))
    return left_trend and right_trend and today["close_qfq"] < today["open"]
