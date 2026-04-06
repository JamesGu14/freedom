from __future__ import annotations

from pathlib import Path

from app.audit.registry import get_dataset_registry
from scripts.audit.run_data_integrity_audit import build_parser, resolve_output_dir, run_audit, select_datasets


def test_runner_parser_accepts_dataset_filter_and_run_id() -> None:
    parser = build_parser()

    args = parser.parse_args(["--datasets", "daily,moneyflow_hsgt", "--run-id", "fixed-run"])

    assert args.datasets == "daily,moneyflow_hsgt"
    assert args.run_id == "fixed-run"


def test_resolve_output_dir_uses_fixed_data_audit_subdirectory(tmp_path) -> None:
    output_dir = resolve_output_dir(run_id="fixed-run", log_dir=tmp_path / "logs")

    assert output_dir == Path(tmp_path / "logs" / "data_audit" / "fixed-run")


def test_select_datasets_filters_registry_by_name() -> None:
    registry = get_dataset_registry()

    selected = select_datasets(registry, ["daily", "moneyflow_hsgt"])

    assert list(selected.keys()) == ["daily", "moneyflow_hsgt"]


def test_run_audit_uses_reference_counts_for_index_factor_pro_rowcount(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.resolve_output_dir", lambda run_id, log_dir=None: tmp_path / run_id)
    monkeypatch.setattr(
        "scripts.audit.run_data_integrity_audit.load_open_trade_dates",
        lambda start_date=None, end_date=None: [f"202506{day:02d}" for day in range(1, 23)],
    )

    def fake_load_counts_by_date(config, *, count_mode="auto", start_date=None, end_date=None):
        if config.name == "index_factor_pro":
            counts = {f"202506{day:02d}": 879 for day in range(1, 21)}
            counts["20250621"] = 587
            counts["20250622"] = 341
            return counts
        if config.name == "index_factor_pro_rowcount_reference":
            return {
                "20250621": 587,
                "20250622": 587,
            }
        raise AssertionError(f"unexpected config {config.name}")

    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.load_counts_by_date", fake_load_counts_by_date)

    result = run_audit(selected_names=["index_factor_pro"], run_id="fixed-run")

    assert len(result.datasets) == 1
    assert result.datasets[0].dataset == "index_factor_pro"
    assert [row.trade_date for row in result.datasets[0].rowcount_anomalies] == ["20250622"]
    assert result.datasets[0].rowcount_anomalies[0].baseline_source == "reference"


def test_run_audit_skips_trade_calendar_gap_check_for_moneyflow_hsgt(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.resolve_output_dir", lambda run_id, log_dir=None: tmp_path / run_id)
    monkeypatch.setattr(
        "scripts.audit.run_data_integrity_audit.load_open_trade_dates",
        lambda start_date=None, end_date=None: ["20230901", "20230904", "20230905"],
    )

    def fake_load_counts_by_date(config, *, count_mode="auto", start_date=None, end_date=None):
        if config.name == "moneyflow_hsgt":
            return {
                "20230904": 1,
                "20230905": 1,
            }
        raise AssertionError(f"unexpected config {config.name}")

    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.load_counts_by_date", fake_load_counts_by_date)

    result = run_audit(selected_names=["moneyflow_hsgt"], run_id="fixed-run")

    assert len(result.datasets) == 1
    assert result.datasets[0].dataset == "moneyflow_hsgt"
    assert result.datasets[0].date_gap.missing_trade_dates == []
    assert result.datasets[0].status == "green"


def test_run_audit_ignores_known_source_empty_day_for_moneyflow_dc(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.resolve_output_dir", lambda run_id, log_dir=None: tmp_path / run_id)
    monkeypatch.setattr(
        "scripts.audit.run_data_integrity_audit.load_open_trade_dates",
        lambda start_date=None, end_date=None: ["20231121", "20231122", "20231123"],
    )

    def fake_load_counts_by_date(config, *, count_mode="auto", start_date=None, end_date=None):
        if config.name == "daily":
            return {
                "20231121": 5000,
                "20231122": 5193,
                "20231123": 5001,
            }
        if config.name == "moneyflow_dc":
            return {
                "20231121": 5000,
                "20231123": 5001,
            }
        raise AssertionError(f"unexpected config {config.name}")

    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.load_counts_by_date", fake_load_counts_by_date)

    result = run_audit(selected_names=["moneyflow_dc"], run_id="fixed-run")

    assert len(result.datasets) == 1
    assert result.datasets[0].dataset == "moneyflow_dc"
    assert result.datasets[0].date_gap.missing_trade_dates == []
    assert result.datasets[0].coverage_anomalies == []
    assert result.datasets[0].status == "green"


def test_run_audit_applies_dataset_specific_baseline_filters(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.resolve_output_dir", lambda run_id, log_dir=None: tmp_path / run_id)
    monkeypatch.setattr(
        "scripts.audit.run_data_integrity_audit.load_open_trade_dates",
        lambda start_date=None, end_date=None: ["20250102", "20250103"],
    )

    seen_daily_configs = []

    def fake_load_counts_by_date(config, *, count_mode="auto", start_date=None, end_date=None):
        if config.name == "daily":
            seen_daily_configs.append(config)
            if config.baseline_excluded_ts_code_suffixes == [".BJ"] and config.baseline_excluded_ts_codes == ["300114.SZ", "600898.SH"]:
                return {
                    "20250102": 5615,
                    "20250103": 5618,
                }
            return {
                "20250102": 5880,
                "20250103": 5882,
            }
        if config.name == "cyq_perf":
            return {
                "20250102": 5615,
                "20250103": 5618,
            }
        raise AssertionError(f"unexpected config {config.name}")

    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.load_counts_by_date", fake_load_counts_by_date)

    result = run_audit(selected_names=["cyq_perf"], run_id="fixed-run")

    assert len(result.datasets) == 1
    assert result.datasets[0].dataset == "cyq_perf"
    assert result.datasets[0].coverage_anomalies == []
    assert result.datasets[0].status == "green"
    assert seen_daily_configs
    assert seen_daily_configs[-1].baseline_excluded_ts_code_suffixes == [".BJ"]
    assert seen_daily_configs[-1].baseline_excluded_ts_codes == ["300114.SZ", "600898.SH"]


def test_run_audit_ignores_known_rowcount_transition_days(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.resolve_output_dir", lambda run_id, log_dir=None: tmp_path / run_id)
    monkeypatch.setattr(
        "scripts.audit.run_data_integrity_audit.load_open_trade_dates",
        lambda start_date=None, end_date=None: ["20100531"],
    )

    def fake_load_counts_by_date(config, *, count_mode="auto", start_date=None, end_date=None):
        if config.name == "market_index_dailybasic":
            counts = {f"201005{day:02d}": 4 for day in range(1, 31)}
            counts["20100531"] = 3
            counts["20100601"] = 5
            return counts
        raise AssertionError(f"unexpected config {config.name}")

    monkeypatch.setattr("scripts.audit.run_data_integrity_audit.load_counts_by_date", fake_load_counts_by_date)

    result = run_audit(selected_names=["market_index_dailybasic"], run_id="fixed-run")

    assert len(result.datasets) == 1
    assert result.datasets[0].dataset == "market_index_dailybasic"
    assert result.datasets[0].rowcount_anomalies == []
    assert result.datasets[0].status == "green"
