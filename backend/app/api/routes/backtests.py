from fastapi import APIRouter

router = APIRouter()


@router.post("/backtests")
def create_backtest() -> dict[str, str]:
    return {"status": "not_implemented"}


@router.get("/backtests/{backtest_id}")
def get_backtest(backtest_id: str) -> dict[str, str]:
    return {"backtest_id": backtest_id}


@router.get("/backtests/{backtest_id}/trades")
def list_backtest_trades(backtest_id: str) -> dict[str, str]:
    return {"backtest_id": backtest_id, "items": []}
