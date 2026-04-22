from __future__ import annotations

import math
from dataclasses import dataclass

import duckdb
from pymongo import MongoClient

INDEX_TS_CODE = "000001.SH"
INDEX_COL = "index_factor_pro"


@dataclass(frozen=True)
class MarketRegimeResult:
    trade_date: str
    close: float
    pct_change: float
    trend_score: float
    breadth_score: float
    momentum_score: float
    total_score: float
    trend_detail: dict
    breadth_detail: dict
    momentum_detail: dict
    regime: str
    regime_label_cn: str


REGIME_MAP = [
    (-10, -6, "bear", "熊市 📉"),
    (-6, -2, "lean_bear", "偏空 🔵"),
    (-2, 2, "range", "震荡 🟡"),
    (2, 6, "lean_bull", "偏多 🟠"),
    (6, 10.01, "bull", "牛市 📈"),
]


def _regime_from_score(score: float) -> tuple[str, str]:
    for lo, hi, key, label in REGIME_MAP:
        if lo <= score < hi:
            return key, label
    return "range", "震荡 🟡"


def _safe(val) -> float:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return 0.0
    return float(val)


def _compute_trend(idx: dict) -> tuple[float, dict]:
    score = 0.0
    detail: dict = {}
    close = _safe(idx.get("close"))

    for ma_key, label, weight in [
        ("ma_bfq_20", "MA20", 1),
        ("ma_bfq_60", "MA60", 1.5),
        ("ma_bfq_250", "MA250", 2),
    ]:
        ma_val = _safe(idx.get(ma_key))
        if ma_val > 0:
            above = close > ma_val
            score += weight if above else -weight
            detail[f"above_{label}"] = above

    ma5 = _safe(idx.get("ma_bfq_5"))
    ma20 = _safe(idx.get("ma_bfq_20"))
    ma60 = _safe(idx.get("ma_bfq_60"))
    if ma5 > 0 and ma20 > 0 and ma60 > 0:
        if ma5 >= ma20 >= ma60:
            score += 2
            detail["ma_alignment"] = "bull"
        elif ma5 <= ma20 <= ma60:
            score -= 2
            detail["ma_alignment"] = "bear"
        else:
            detail["ma_alignment"] = "mixed"

    dif = _safe(idx.get("macd_dif_bfq"))
    dea = _safe(idx.get("macd_dea_bfq"))
    if dif != 0 or dea != 0:
        score += 1 if dif > dea else -1
        detail["macd_bull"] = dif > dea

    rsi12 = _safe(idx.get("rsi_bfq_12"))
    if rsi12 > 0:
        if 50 < rsi12 <= 70:
            score += 1
            detail["rsi12_zone"] = "strong"
        elif 30 < rsi12 <= 50:
            score -= 1
            detail["rsi12_zone"] = "weak"
        elif rsi12 > 70:
            detail["rsi12_zone"] = "overbought"
        else:
            detail["rsi12_zone"] = "oversold"

    return score, detail


def _compute_breadth(trade_date: str, data_dir: str) -> tuple[float, dict]:
    detail: dict = {}
    year = trade_date[:4]
    glob_pattern = f"{data_dir}/raw/daily/*/year={year}/*.parquet"

    try:
        con = duckdb.connect()
        row = con.execute(
            f"SELECT COUNT(*) as total,"
            f" SUM(CASE WHEN pct_chg > 0 THEN 1 ELSE 0 END) as up,"
            f" SUM(CASE WHEN pct_chg < 0 THEN 1 ELSE 0 END) as down"
            f" FROM read_parquet('{glob_pattern}')"
            f" WHERE trade_date = '{trade_date}'"
        ).fetchone()
        con.close()
    except Exception:
        return 0.0, {"error": "query_failed"}

    if not row or row[0] == 0:
        return 0.0, {"total": 0}

    total, up, down = int(row[0]), int(row[1]), int(row[2])
    up_ratio = up / total
    detail["total"] = total
    detail["up"] = up
    detail["down"] = down
    detail["up_ratio"] = round(up_ratio, 4)

    if up_ratio >= 0.7:
        return 2.0, detail
    if up_ratio >= 0.55:
        return 1.0, detail
    if up_ratio >= 0.45:
        return 0.0, detail
    if up_ratio >= 0.3:
        return -1.0, detail
    return -2.0, detail


def _compute_momentum(idx: dict, mongo_col) -> tuple[float, dict]:
    detail: dict = {}
    score = 0.0
    close = _safe(idx.get("close"))
    trade_date = idx.get("trade_date", "")

    for skip_n, field_name, threshold in [(20, "pct_20d", 5), (60, "pct_60d", 8)]:
        cursor = mongo_col.find(
            {"ts_code": INDEX_TS_CODE, "trade_date": {"$lt": trade_date}, "close": {"$ne": None}},
            {"close": 1},
            sort=[("trade_date", -1)],
        ).skip(skip_n).limit(1)
        docs = list(cursor)
        if not docs:
            continue
        prev_close = float(docs[0]["close"])
        if prev_close > 0:
            pct = (close / prev_close - 1) * 100
            detail[field_name] = round(pct, 2)
            if pct > threshold:
                score += 1
            elif pct < -threshold:
                score -= 1

    return score, detail


def compute_market_regime(
    trade_date: str,
    mongo_client: MongoClient,
    mongo_db: str = "freedom",
    data_dir: str = "data",
) -> MarketRegimeResult | None:
    db = mongo_client[mongo_db]
    col = db[INDEX_COL]

    idx = col.find_one({"ts_code": INDEX_TS_CODE, "trade_date": trade_date})
    if not idx or not idx.get("close"):
        return None

    trend_score, trend_detail = _compute_trend(idx)
    breadth_score, breadth_detail = _compute_breadth(trade_date, data_dir)
    momentum_score, momentum_detail = _compute_momentum(idx, col)

    total = round(trend_score * 0.4 + breadth_score * 0.4 + momentum_score * 0.2, 2)
    regime, label = _regime_from_score(total)

    return MarketRegimeResult(
        trade_date=trade_date,
        close=_safe(idx.get("close")),
        pct_change=_safe(idx.get("pct_change")),
        trend_score=round(trend_score, 2),
        breadth_score=round(breadth_score, 2),
        momentum_score=round(momentum_score, 2),
        total_score=total,
        trend_detail=trend_detail,
        breadth_detail=breadth_detail,
        momentum_detail=momentum_detail,
        regime=regime,
        regime_label_cn=label,
    )
