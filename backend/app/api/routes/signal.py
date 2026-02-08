from fastapi import APIRouter

router = APIRouter()


@router.get("/signal")
def get_signal() -> dict[str, str]:
    return {"signal": "HOLD", "reason": "not_implemented"}
