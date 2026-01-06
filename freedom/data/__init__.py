"""
Data subpackage containing provider interfaces, storage backends, and
ingestion orchestration for A-share daily data.
"""

from .ingestor import DailyIngestor  # noqa: F401
from .models import BasicInfo, DailyBar  # noqa: F401
from .provider import BaseDataProvider  # noqa: F401
from .storage import SQLiteStorage  # noqa: F401
from .storage_duckdb import DuckDBStorage  # noqa: F401

__all__ = [
    "DailyIngestor",
    "BasicInfo",
    "DailyBar",
    "BaseDataProvider",
    "SQLiteStorage",
    "DuckDBStorage",
]
