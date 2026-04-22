from __future__ import annotations

# Pattern classification with weights
PATTERN_CATEGORIES = {
    "trend": {
        "weight": 3,
        "label": "趋势信号",
        "patterns": [
            "ma_bullish_alignment",      # 均线多头
            "five_ma_rising",            # 五线顺上
            "ascending_channel",         # 上升通道
            "accelerating_uptrend",      # 加速上涨
            "climbing_slope",            # 上升爬坡形
            "ma_bearish_alignment",      # 均线空头（卖）
            "descending_channel",        # 下降通道（卖）
        ]
    },
    "breakout": {
        "weight": 2,
        "label": "突破信号",
        "patterns": [
            "platform_breakout",         # 突破平台
            "bollinger_breakout",        # 布林突破
            "ma_convergence_breakout",   # 均线粘合突破
            "water_lily",                # 出水芙蓉
            "one_yang_three_lines",      # 一阳穿三线
            "dragon_out_of_sea",         # 蛟龙出海
        ]
    },
    "reversal": {
        "weight": 2,
        "label": "反转信号",
        "patterns": [
            "w_bottom",                  # W底
            "rounding_bottom",           # 圆弧底
            "yang_engulfs_yin",          # 阳包阴
            "morning_doji_star",         # 早晨十字星
            "double_needle_bottom",      # 双针探底
            "golden_needle_bottom",      # 金针探底
            "hammer",                    # 锤子线
            "v_reversal",                # V型反转
            "dark_cloud_cover",          # 乌云盖顶（卖）
        ]
    },
    "candlestick": {
        "weight": 1,
        "label": "K线组合",
        "patterns": [
            "red_three_soldiers",
            "black_three_soldiers",
            "three_crows",
            "bullish_cannon",
            "rising_sun",
            "evening_star",
            "inverted_hammer",
        ]
    },
    "special": {
        "weight": 2,
        "label": "特殊形态",
        "patterns": [
            "limit_up_double_cannon",
            "limit_up_return_spear",
            "immortal_pointing",
            "old_duck_head",
            "air_refueling",
            "beauty_shoulder",
            "golden_pit",
            "treasure_basin",
            "flag_formation",
            "one_yang_finger",
            "desperate_counterattack",
            "long_upper_shadow",
            "small_yang_steps",
            "golden_spider",
            "long_lower_shadow",
            "attack_forcing_line",
            "bullish_vanguard",
            "gap_up",
            "gap_down",
            "rounding_top",
            "tower_top",
        ]
    },
    "technical": {
        "weight": 2,
        "label": "技术指标",
        "patterns": [
            "buy_macd_kdj_double_cross",     # 双金叉
            "buy_volume_breakout_20d",       # 放量突破
            "buy_rsi_rebound",               # RSI超卖回升
            "sell_macd_kdj_double_cross",    # 双死叉（卖）
            "sell_volume_breakdown_20d",     # 放量跌破（卖）
            "sell_rsi_fall",                 # RSI超买回落（卖）
        ]
    }
}

# Flatten all patterns
ALL_PATTERNS = []
for category, config in PATTERN_CATEGORIES.items():
    ALL_PATTERNS.extend(config["patterns"])

BUY_PATTERNS = [p for p in ALL_PATTERNS if not p.startswith("sell_") and p not in [
    "ma_bearish_alignment", "descending_channel", "dark_cloud_cover",
    "black_three_soldiers", "three_crows", "evening_star", "gap_down", "rounding_top", "tower_top"
]]

SELL_PATTERNS = [p for p in ALL_PATTERNS if p not in BUY_PATTERNS]

# Resonance thresholds (weighted score)
RESONANCE_THRESHOLDS = {
    "normal": 5,      # 普通共振
    "strong": 9,      # 强共振
    "very_strong": 14 # 极强共振
}


def get_pattern_weight(pattern: str) -> int:
    for category, config in PATTERN_CATEGORIES.items():
        if pattern in config["patterns"]:
            return config["weight"]
    return 1


def get_pattern_category(pattern: str) -> str:
    for category, config in PATTERN_CATEGORIES.items():
        if pattern in config["patterns"]:
            return category
    return "unknown"


def get_pattern_category_label(pattern: str) -> str:
    for category, config in PATTERN_CATEGORIES.items():
        if pattern in config["patterns"]:
            return config["label"]
    return "未知"


def classify_resonance_level(weighted_score: int) -> str | None:
    if weighted_score >= RESONANCE_THRESHOLDS["very_strong"]:
        return "very_strong"
    if weighted_score >= RESONANCE_THRESHOLDS["strong"]:
        return "strong"
    if weighted_score >= RESONANCE_THRESHOLDS["normal"]:
        return "normal"
    return None


def calculate_weighted_score(patterns: list[str]) -> int:
    return sum(get_pattern_weight(p) for p in patterns)
