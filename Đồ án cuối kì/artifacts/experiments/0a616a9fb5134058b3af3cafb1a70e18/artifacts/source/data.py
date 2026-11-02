"""Read-only CSV loading and temporal/data-quality validation (no imputation)."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

TIME_COLUMNS = ["year", "month", "day", "hour"]
MEASUREMENTS = ["PM2.5", "PM10", "SO2", "NO2", "CO", "O3", "TEMP", "PRES", "DEWP", "RAIN", "WSPM"]
FEATURE_COLUMNS = TIME_COLUMNS + MEASUREMENTS + ["wd", "station"]
RAW_COLUMNS = ["No"] + TIME_COLUMNS + MEASUREMENTS[:-1] + ["wd", "WSPM", "station"]
ISSUE_COLUMNS = ["severity", "code", "station", "timestamp", "source_file", "source_row", "column", "value", "detail"]
STATION_AUDIT_COLUMNS = ["station", "rows", "unique_hours", "timestamp_min", "timestamp_max", "missing_hours_internal", "missing_hours_expected", "duplicate_rows"]
WIND_DIRECTIONS = set("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class LoadResult:
    data: pd.DataFrame
    issues: pd.DataFrame
    stations: pd.DataFrame
    summary: dict


class DataQualityError(ValueError):
    """Fatal input issues; result contains audit evidence, not approved data."""

    def __init__(self, result: LoadResult):
        self.result = result
        super().__init__(f"Data quality errors: {result.summary['error_count']}; merged output blocked")


def validate_temporal_integrity(frame: pd.DataFrame) -> None:
    """Require nonmissing hourly timestamps, unique keys, and canonical order."""
    if not pd.api.types.is_datetime64_any_dtype(frame["timestamp"]):
        raise ValueError("timestamp must have datetime dtype")
    if frame[["station", "timestamp"]].isna().any().any() or frame["station"].eq("").any():
        raise ValueError("Missing station/timestamp key")
    if not frame["timestamp"].eq(frame["timestamp"].dt.floor("h")).all():
        raise ValueError("timestamp must be aligned to an hour")
    if frame.duplicated(["station", "timestamp"]).any():
        raise ValueError("Duplicate station-timestamp key")
    actual = pd.MultiIndex.from_frame(frame[["station", "timestamp"]])
    if not actual.equals(actual.sort_values()):
        raise ValueError("Data must be sorted by station and timestamp")


def load_station_data(
    paths: list[Path], *, rows_per_file: int | None = None,
    review_ranges: dict | None = None, expected_start: str | None = None,
    expected_end: str | None = None, expected_hashes: dict | None = None,
) -> LoadResult:
    """Merge station files; reject every duplicate, including identical copies.

    Missing hours and contextual extremes are reported without reindexing,
    deleting, filling, or changing raw values. No is excluded from output.
    """
    if not paths:
        raise ValueError("No station CSV files found")
    if rows_per_file is not None and rows_per_file < 1:
        raise ValueError("rows_per_file must be positive")
    issues: list[dict] = []
    frames = []
    input_hashes = {}

    def issue(code, severity="error", *, row=None, column="", value="", detail="", source_file=""):
        record = dict.fromkeys(ISSUE_COLUMNS, "")
        record.update(severity=severity, code=code, column=column, value=str(value), detail=detail, source_file=source_file)
        if row is not None:
            record.update(station=row.get("station", ""), timestamp=row.get("timestamp", ""),
                          source_file=row["source_file"], source_row=int(row["source_row"]))
        issues.append(record)

    if expected_hashes is not None:
        observed_files = {Path(path).name for path in paths}
        for missing_file in sorted(set(expected_hashes) - observed_files):
            issue("missing_station_file", source_file=missing_file, detail="File listed in raw manifest is absent")

    for path in sorted(map(Path, paths)):
        digest = sha256(path)
        input_hashes[path.name] = digest
        if expected_hashes is not None and expected_hashes.get(path.name) != digest:
            issue("checksum_mismatch", source_file=path.name)
            continue
        records = []
        try:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                if next(reader, None) != RAW_COLUMNS:
                    issue("invalid_schema", source_file=path.name, detail="Expected exact UCI 501 column order")
                    continue
                for row_number, values in enumerate(reader, start=2):
                    if rows_per_file is not None and row_number > rows_per_file + 1:
                        break
                    if len(values) != len(RAW_COLUMNS):
                        issue("invalid_csv_row", source_file=path.name, value=row_number, detail=f"Observed {len(values)} fields")
                        continue
                    records.append(values + [path.name, row_number])
        except (csv.Error, UnicodeError) as exc:
            issue("invalid_csv_format", source_file=path.name, detail=str(exc))
        if records:
            frames.append(pd.DataFrame(records, columns=RAW_COLUMNS + ["source_file", "source_row"]))
        else:
            issue("empty_station_file", source_file=path.name)
        if sha256(path) != digest:
            issue("raw_changed_during_read", source_file=path.name)

    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=RAW_COLUMNS + ["source_file", "source_row"])
    input_rows = len(data)
    identifiers = pd.to_numeric(data["No"], errors="coerce")
    bad_identifier = identifiers.isna() | ~np.isfinite(identifiers) | identifiers.lt(1) | identifiers.mod(1).ne(0)
    for index in data.index[bad_identifier]:
        issue("review_invalid_row_number", "warning", row=data.loc[index], column="No", value=data.loc[index, "No"], detail="Raw identifier only; excluded from merged output/features")
    for column in TIME_COLUMNS + MEASUREMENTS:
        text = data[column].astype("string")
        missing = text.isin(["NA", ""])
        numeric = pd.to_numeric(text.mask(missing), errors="coerce").astype("float64")
        malformed = ~missing & (numeric.isna() | ~np.isfinite(numeric))
        for index in data.index[malformed]:
            issue("invalid_numeric", row=data.loc[index], column=column, value=text.loc[index])
        data[column] = numeric

    for column in ["station", "wd"]:
        data[column] = data[column].astype("string").replace({"NA": pd.NA, "": pd.NA})
    bad_station = data["station"].isna() | data["station"].str.strip().ne(data["station"]).fillna(False)
    for index in data.index[bad_station]:
        issue("invalid_station", row=data.loc[index])
    for filename, group in data.groupby("source_file", sort=True):
        stations = group["station"].dropna().unique()
        if len(stations) != 1 or filename != f"PRSA_Data_{stations[0]}_20130301-20170228.csv":
            issue("station_file_mismatch", source_file=filename, detail=str(list(stations)))

    valid_time = data[TIME_COLUMNS].notna().all(axis=1)
    for column, lower, upper in [("year", 1, 9999), ("month", 1, 12), ("day", 1, 31), ("hour", 0, 23)]:
        valid_time &= data[column].between(lower, upper) & data[column].eq(data[column].round())
    data["timestamp"] = pd.to_datetime(data[TIME_COLUMNS].where(valid_time), errors="coerce")
    for index in data.index[data["timestamp"].isna()]:
        issue("invalid_timestamp", row=data.loc[index], detail="Invalid/missing/noninteger date components; no hour rollover allowed")

    duplicate_mask = data.duplicated(["station", "timestamp"], keep=False) & ~bad_station & data["timestamp"].notna()
    payload = TIME_COLUMNS + MEASUREMENTS + ["wd"]
    for _, group in data.loc[duplicate_mask].groupby(["station", "timestamp"], sort=True):
        conflicting = group[payload].nunique(dropna=False).gt(1).any()
        code = "conflicting_duplicate_key" if conflicting else "identical_duplicate_key"
        for _, row in group.iterrows():
            issue(code, row=row, detail="All records for this key rejected; no arbitrary keep-first/last")

    for column in MEASUREMENTS:
        values = data[column]
        impossible = pd.Series(False, index=data.index)
        if column in ["PM2.5", "PM10", "SO2", "NO2", "CO", "O3", "RAIN", "WSPM"]:
            impossible = values.lt(0)
        elif column == "PRES":
            impossible = values.le(0)
        elif column in ["TEMP", "DEWP"]:
            impossible = values.lt(-273.15)
        for index in data.index[impossible]:
            issue("physically_invalid_value", row=data.loc[index], column=column, value=values.loc[index])
        if column in (review_ranges or {}):
            lower, upper = review_ranges[column]
            review = values.notna() & ~values.between(lower, upper) & ~impossible
            for index in data.index[review]:
                issue("review_extreme_value", "warning", row=data.loc[index], column=column, value=values.loc[index], detail="Retained; contextual threshold, not proof of invalid data")
    for index in data.index[data["DEWP"].gt(data["TEMP"])]:
        issue("review_dewpoint_above_temperature", "warning", row=data.loc[index], detail="Retained for instrument/metadata review")
    for index in data.index[data["wd"].notna() & ~data["wd"].isin(WIND_DIRECTIONS)]:
        issue("review_wind_direction", "warning", row=data.loc[index], column="wd", value=data.loc[index, "wd"])

    station_records = []
    for station, group in data.loc[~bad_station & data["timestamp"].notna()].groupby("station", sort=True):
        # Unique timestamps only for gap accounting; no data record is removed.
        times = pd.DatetimeIndex(group["timestamp"].unique()).sort_values()
        hours = np.asarray((times[1:] - times[:-1]) / pd.Timedelta(hours=1), dtype=int)
        gaps = int(np.maximum(hours - 1, 0).sum())
        for index in np.flatnonzero(hours > 1):
            issue("missing_hours", "warning", detail=f"{station}: after {times[index]} before {times[index+1]}; missing {hours[index]-1} hours")
        expected_missing = None
        if expected_start and expected_end:
            grid = pd.date_range(expected_start, expected_end, freq="h")
            expected_missing = len(grid.difference(times))
            outside = int(((times < grid[0]) | (times > grid[-1])).sum())
            if expected_missing or outside:
                issue("review_expected_coverage", "warning", detail=f"{station}: missing {expected_missing} expected hours, {outside} outside period")
        station_records.append(dict(station=station, rows=len(group), unique_hours=len(times),
                                    timestamp_min=str(times[0]), timestamp_max=str(times[-1]),
                                    missing_hours_internal=gaps, missing_hours_expected=expected_missing,
                                    duplicate_rows=int(group.duplicated("timestamp", keep=False).sum())))

    # No is a raw row identifier, never a model feature or duplicate tie-breaker.
    data = data.drop(columns="No").sort_values(["station", "timestamp", "source_file", "source_row"], kind="stable").reset_index(drop=True)
    issue_table = pd.DataFrame(issues, columns=ISSUE_COLUMNS)
    error_count = int(issue_table["severity"].eq("error").sum())
    if not error_count:
        for column in TIME_COLUMNS:
            data[column] = data[column].astype("Int64")
    summary = dict(input_files=len(paths), parsed_rows=input_rows, candidate_rows=len(data), output_rows=0 if error_count else len(data),
                   station_count=int(data["station"].nunique()), error_count=error_count,
                   warning_count=int(issue_table["severity"].eq("warning").sum()),
                   missing={column: int(data[column].isna().sum()) for column in FEATURE_COLUMNS},
                   dtypes={column: str(dtype) for column, dtype in data.dtypes.items()},
                   raw_sha256=input_hashes, duplicate_policy="reject_all_duplicate_keys",
                   imputed=False, outlier_removal=False, no_column_in_features="No" not in FEATURE_COLUMNS)
    result = LoadResult(data, issue_table, pd.DataFrame(station_records, columns=STATION_AUDIT_COLUMNS), summary)
    if error_count:
        raise DataQualityError(result)
    validate_temporal_integrity(data)
    return result
