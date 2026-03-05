from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.api.stock_code import resolve_ts_code_input
from app.services.market_data_service import (
    get_ccass_hold,
    get_cyq_chips,
    get_cyq_perf,
    get_hk_hold,
    get_index_factors,
    get_moneyflow_dc,
    get_moneyflow_hsgt,
    get_stk_surv,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/chip-perf/{ts_code}")
def chip_perf(
    ts_code: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    data = get_cyq_perf(normalized, start_date, end_date)
    return {"ts_code": normalized, "data": data}


@router.get("/chip-distribution/{ts_code}")
def chip_distribution(
    ts_code: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    data = get_cyq_chips(normalized, start_date, end_date)
    return {"ts_code": normalized, "data": data}


@router.get("/ccass-hold/{ts_code}")
def ccass_hold(
    ts_code: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    data = get_ccass_hold(normalized, start_date, end_date)
    return {"ts_code": normalized, "data": data}


@router.get("/hk-hold/{ts_code}")
def hk_hold(
    ts_code: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
    exchange: str = Query(default=""),
) -> dict:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    data = get_hk_hold(normalized, start_date, end_date, exchange)
    return {"ts_code": normalized, "data": data}


@router.get("/institution-survey/{ts_code}")
def institution_survey(
    ts_code: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    data = get_stk_surv(normalized, start_date, end_date)
    return {"ts_code": normalized, "data": data}


@router.get("/moneyflow-dc/{ts_code}")
def moneyflow_dc(
    ts_code: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    data = get_moneyflow_dc(normalized, start_date, end_date)
    return {"ts_code": normalized, "data": data}


@router.get("/moneyflow-hsgt")
def moneyflow_hsgt(
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict:
    data = get_moneyflow_hsgt(start_date, end_date)
    return {"data": data}


@router.get("/index-factors/{ts_code}")
def index_factors(
    ts_code: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    data = get_index_factors(normalized, start_date, end_date)
    return {"ts_code": normalized, "data": data}
