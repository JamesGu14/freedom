from fastapi import APIRouter

router = APIRouter()


@router.get("/strategies")
def list_strategies() -> dict[str, list[dict[str, str]]]:
    return {"items": []}


@router.post("/strategies")
def create_strategy() -> dict[str, str]:
    return {"status": "not_implemented"}


@router.put("/strategies/{strategy_id}")
def update_strategy(strategy_id: int) -> dict[str, str]:
    return {"strategy_id": str(strategy_id)}


@router.post("/strategies/{strategy_id}/enable")
def enable_strategy(strategy_id: int) -> dict[str, str]:
    return {"strategy_id": str(strategy_id), "enabled": "true"}


@router.post("/strategies/{strategy_id}/disable")
def disable_strategy(strategy_id: int) -> dict[str, str]:
    return {"strategy_id": str(strategy_id), "enabled": "false"}


@router.get("/strategies/{strategy_id}/versions")
def list_strategy_versions(strategy_id: int) -> dict[str, list[dict[str, str]]]:
    return {"strategy_id": str(strategy_id), "items": []}
