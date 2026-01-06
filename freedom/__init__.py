"""
Core package for the stock analysis toolkit.

This module currently exposes the data ingestion subpackage, which
provides interfaces for providers, storage backends, and orchestrated
ingestion flows for daily A-share data.
"""

from .data.ingestor import DailyIngestor  # noqa: F401
from .data.models import BasicInfo, DailyBar  # noqa: F401
from .data.provider import BaseDataProvider  # noqa: F401
from .data.storage import SQLiteStorage  # noqa: F401
from .data.storage_duckdb import DuckDBStorage  # noqa: F401

__all__ = [
    "DailyIngestor",
    "BasicInfo",
    "DailyBar",
    "BaseDataProvider",
    "SQLiteStorage",
    "DuckDBStorage",
]
