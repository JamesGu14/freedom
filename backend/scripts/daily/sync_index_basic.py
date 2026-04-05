#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo_index_data import upsert_index_basic_batch  # noqa: E402
from app.data.tushare_client import fetch_index_basic  # noqa: E402

logger = logging.getLogger(__name__)
SUPPORTED_MARKETS = ["SSE", "SZSE", "CSI", "CICC", "SW", "MSCI"]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    total_rows = 0
    total_upserted = 0
    for market in SUPPORTED_MARKETS:
        df = fetch_index_basic(market=market)
        records = [] if df is None or df.empty else df.where(df.notna(), None).to_dict(orient="records")
        upserted = upsert_index_basic_batch(records)
        total_rows += len(records)
        total_upserted += upserted
        logger.info("sync_index_basic market=%s rows=%s upserted=%s", market, len(records), upserted)

    logger.info("sync_index_basic done: markets=%s api_rows=%s upserted=%s", len(SUPPORTED_MARKETS), total_rows, total_upserted)


if __name__ == "__main__":
    main()
