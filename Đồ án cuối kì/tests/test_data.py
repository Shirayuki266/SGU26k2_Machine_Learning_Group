"""Small synthetic unit fixtures, never used as project data or results."""

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from beijing_air.data import (
    DataQualityError, FEATURE_COLUMNS, RAW_COLUMNS, load_station_data,
    sha256, validate_temporal_integrity,
)


def make_row(station="Aotizhongxin", **changes):
    row = dict.fromkeys(RAW_COLUMNS, "1")
    row.update(year="2013", month="3", day="1", hour="0", station=station,
               TEMP="10", DEWP="5", PRES="1010", wd="N")
    row.update({key: str(value) for key, value in changes.items()})
    return row


def write_file(tmp_path, rows, station="Aotizhongxin"):
    path = tmp_path / f"PRSA_Data_{station}_20130301-20170228.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RAW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_merge_sort_missing_and_raw_unchanged(tmp_path):
    first = write_file(tmp_path, [make_row(hour=2, **{"PM2.5": "NA"}), make_row(hour=0)])
    second = write_file(tmp_path, [make_row("Changping")], "Changping")
    before = {path: sha256(path) for path in [first, second]}
    result = load_station_data([second, first])
    assert result.data.station.tolist() == ["Aotizhongxin", "Aotizhongxin", "Changping"]
    assert result.data.hour.tolist() == [0, 2, 0]
    assert pd.isna(result.data.loc[1, "PM2.5"])
    assert result.stations.set_index("station").loc["Aotizhongxin", "missing_hours_internal"] == 1
    assert "No" not in result.data and "No" not in FEATURE_COLUMNS
    assert len(result.data) == 3  # Missing hour is reported, never inserted/imputed.
    assert all(sha256(path) == digest for path, digest in before.items())
    validate_temporal_integrity(result.data)


@pytest.mark.parametrize("changes", [
    {"hour": 24}, {"hour": -1}, {"hour": 0.5}, {"month": 13},
    {"month": 2, "day": 30}, {"year": "NA"}, {"day": "oops"},
])
def test_invalid_dates_block_output(tmp_path, changes):
    path = write_file(tmp_path, [make_row(**changes)])
    with pytest.raises(DataQualityError) as exc:
        load_station_data([path])
    assert "invalid_timestamp" in exc.value.result.issues.code.values
    assert exc.value.result.summary["output_rows"] == 0


@pytest.mark.parametrize("changed,code", [
    ({"No": 2}, "identical_duplicate_key"),
    ({"PM2.5": 2}, "conflicting_duplicate_key"),
    ({"PM2.5": "NA"}, "conflicting_duplicate_key"),
])
def test_duplicates_never_arbitrarily_resolved(tmp_path, changed, code):
    path = write_file(tmp_path, [make_row(), make_row(**changed)])
    with pytest.raises(DataQualityError) as exc:
        load_station_data([path])
    assert exc.value.result.issues.code.eq(code).sum() == 2


def test_high_pollution_retained_without_iqr(tmp_path):
    path = write_file(tmp_path, [make_row(**{"PM2.5": 1200})])
    result = load_station_data([path], review_ranges={"PM2.5": [0, 500]})
    assert result.data.loc[0, "PM2.5"] == 1200
    assert result.issues.code.tolist() == ["review_extreme_value"]
    assert result.summary["error_count"] == 0


@pytest.mark.parametrize("column,value", [("PM2.5", -1), ("RAIN", -1), ("WSPM", -1), ("PRES", 0), ("TEMP", -274)])
def test_physical_invalid_values_block_output(tmp_path, column, value):
    path = write_file(tmp_path, [make_row(**{column: value})])
    with pytest.raises(DataQualityError) as exc:
        load_station_data([path])
    assert "physically_invalid_value" in exc.value.result.issues.code.values


@pytest.mark.parametrize("value", ["bad", "inf", "-inf", "NaN"])
def test_malformed_numeric_not_silently_imputed(tmp_path, value):
    path = write_file(tmp_path, [make_row(**{"PM2.5": value})])
    with pytest.raises(DataQualityError) as exc:
        load_station_data([path])
    assert "invalid_numeric" in exc.value.result.issues.code.values


def test_expected_period_detects_boundary_missing_hours(tmp_path):
    path = write_file(tmp_path, [make_row(hour=1)])
    result = load_station_data([path], expected_start="2013-03-01 00:00", expected_end="2013-03-01 03:00")
    assert result.stations.loc[0, "missing_hours_expected"] == 3
    assert len(result.data) == 1


def test_checksum_mismatch_is_fatal(tmp_path):
    path = write_file(tmp_path, [make_row()])
    with pytest.raises(DataQualityError) as exc:
        load_station_data([path], expected_hashes={path.name: "wrong"})
    assert "checksum_mismatch" in exc.value.result.issues.code.values


def test_wrong_station_name_is_fatal(tmp_path):
    path = write_file(tmp_path, [make_row("Changping")])
    with pytest.raises(DataQualityError) as exc:
        load_station_data([path])
    assert "station_file_mismatch" in exc.value.result.issues.code.values


def test_manifest_inventory_cannot_silently_lose_station(tmp_path):
    path = write_file(tmp_path, [make_row()])
    with pytest.raises(DataQualityError) as exc:
        load_station_data([path], expected_hashes={path.name: sha256(path), "missing.csv": "abc"})
    assert "missing_station_file" in exc.value.result.issues.code.values


def test_malformed_csv_is_fatal(tmp_path):
    path = write_file(tmp_path, [make_row()])
    with path.open("a") as stream:
        stream.write("only,two\n")
    with pytest.raises(DataQualityError) as exc:
        load_station_data([path])
    assert "invalid_csv_row" in exc.value.result.issues.code.values


def test_validator_rejects_bad_order_keys_and_alignment():
    frame = pd.DataFrame({"station": ["B", "A"], "timestamp": pd.to_datetime(["2013-03-01", "2013-03-01"])})
    with pytest.raises(ValueError, match="sorted"):
        validate_temporal_integrity(frame)
    with pytest.raises(ValueError, match="Duplicate"):
        validate_temporal_integrity(pd.concat([frame.iloc[[0]], frame.iloc[[0]]]))
    frame.loc[0, "timestamp"] = pd.NaT
    with pytest.raises(ValueError, match="Missing"):
        validate_temporal_integrity(frame)
    frame = pd.DataFrame({"station": ["A"], "timestamp": pd.to_datetime(["2013-03-01 00:30"])})
    with pytest.raises(ValueError, match="aligned"):
        validate_temporal_integrity(frame)


def test_saved_full_output_matches_audit_and_raw_checksums():
    """Integration check when real locally generated full outputs are available."""
    root = Path(__file__).resolve().parents[1]
    merged = root / "data/processed/merged_unimputed_full.csv"
    summary_path = root / "reports/quality_full/summary.json"
    manifest_path = root / "reports/data_manifest.json"
    if not all(path.exists() for path in [merged, summary_path, manifest_path]):
        pytest.skip("Run full merge first to verify the saved real dataset")
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not all((root / item["path"]).exists() for item in manifest["files"]):
        pytest.skip("Raw files are needed for the checksum integration check")
    frame = pd.read_csv(merged, parse_dates=["timestamp"])
    validate_temporal_integrity(frame)
    assert summary["status"] == "passed" and summary["merged_output_written"]
    assert len(frame) == summary["output_rows"]
    assert "No" not in frame
    assert all(int(frame[column].isna().sum()) == count for column, count in summary["missing"].items())
    assert sha256(merged) == summary["merged_sha256"]
    assert all(sha256(root / item["path"]) == item["sha256"] for item in manifest["files"])
