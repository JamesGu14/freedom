from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


StorageType = Literal["parquet", "mongo", "duckdb"]
AuditMode = Literal["date_only", "date_and_coverage", "date_and_rowcount"]
Severity = Literal["green", "yellow", "red"]


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    storage_type: StorageType
    location: str
    date_field: str
    audit_mode: AuditMode
    coverage_key: str | None = None
    baseline_dataset: str | None = None
    baseline_excluded_ts_code_suffixes: list[str] = field(default_factory=list)
    baseline_excluded_ts_codes: list[str] = field(default_factory=list)
    ignored_trade_dates: list[str] = field(default_factory=list)
    ignored_rowcount_trade_dates: list[str] = field(default_factory=list)
    use_trade_calendar: bool = True
    rowcount_reference_storage_type: StorageType | None = None
    rowcount_reference_location: str | None = None
    rowcount_reference_date_field: str | None = None


@dataclass
class DateGapResult:
    local_min_date: str | None
    local_max_date: str | None
    expected_trade_date_count: int
    actual_trade_date_count: int
    missing_trade_dates: list[str]
    severity: Severity
    expected_trade_dates: list[str] = field(default_factory=list)
    missing_ranges: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CoverageAnomaly:
    dataset: str
    trade_date: str
    baseline_count: int
    dataset_count: int
    missing_count: int
    coverage_ratio: float
    severity: Severity

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RowCountAnomaly:
    dataset: str
    trade_date: str
    row_count: int
    median_lookback: float
    baseline_count: float
    baseline_source: str
    deviation_ratio: float
    severity: Severity

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DatasetAuditResult:
    dataset: str
    audit_mode: AuditMode
    local_min_date: str | None
    local_max_date: str | None
    status: Severity
    date_gap: DateGapResult
    coverage_anomalies: list[CoverageAnomaly] = field(default_factory=list)
    rowcount_anomalies: list[RowCountAnomaly] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "audit_mode": self.audit_mode,
            "local_min_date": self.local_min_date,
            "local_max_date": self.local_max_date,
            "status": self.status,
            "date_gap": self.date_gap.to_dict(),
            "coverage_anomalies": [item.to_dict() for item in self.coverage_anomalies],
            "rowcount_anomalies": [item.to_dict() for item in self.rowcount_anomalies],
        }


@dataclass
class AuditRunResult:
    run_id: str
    output_dir: str
    datasets: list[DatasetAuditResult]
    excluded_datasets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "output_dir": self.output_dir,
            "datasets": [item.to_dict() for item in self.datasets],
            "excluded_datasets": list(self.excluded_datasets),
        }
