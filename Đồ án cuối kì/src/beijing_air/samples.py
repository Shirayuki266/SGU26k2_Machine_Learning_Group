"""Exact one-hour supervised samples and temporal partition metadata; no fit."""

from dataclasses import dataclass
import hashlib
import json

import numpy as np
import pandas as pd

from beijing_air.data import validate_temporal_integrity


SPLITS = ("train", "validation", "test")
COHORTS = ("operational", "primary")
ID_COLUMNS = ["sample_id", "station", "input_timestamp", "target_timestamp", "is_primary"]
EXCLUSION_REASONS = ("end_of_series", "missing_target_timestamp", "missing_target_value")
RESERVED = {"sample_id", "input_timestamp", "target_timestamp", "target_pm25", "is_primary", "split", "_target_match"}


@dataclass
class SampleResult:
    samples: pd.DataFrame
    exclusions: pd.DataFrame
    station_audit: pd.DataFrame
    totals: dict


def _timestamp(value):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is not None or timestamp != timestamp.floor("h"):
        raise ValueError("Timestamps must be nonmissing, timezone-naive and aligned to an hour")
    return timestamp


def _check_times(series):
    if not pd.api.types.is_datetime64_any_dtype(series) or isinstance(series.dtype, pd.DatetimeTZDtype):
        raise ValueError("Expected timezone-naive datetime column")
    if series.isna().any() or not series.eq(series.dt.floor("h")).all():
        raise ValueError("Missing or non-hourly timestamp")


def _iso(value):
    return None if pd.isna(value) else value.isoformat(timespec="seconds")


def _sample_id(station, origin, target):
    # IDs identify the observation key, not its values, row order or file path.
    key = json.dumps(["pm25-h1-v1", station, _iso(origin), _iso(target)],
                     ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def build_samples(data, *, horizon_hours=1):
    """Retain observed targets; flag the PM2.5(t)-observed primary cohort.

    All exclusions are mutually exclusive. End-of-series is relative to the
    supplied input, so a smoke prefix must never be interpreted as full data.
    """
    if horizon_hours != 1 or isinstance(horizon_hours, bool):
        raise ValueError("This protocol requires horizon_hours=1")
    required = {"station", "timestamp", "PM2.5"}
    if not required.issubset(data.columns) or data.empty:
        raise ValueError("Nonempty station/timestamp/PM2.5 input is required")
    if not data.columns.is_unique or RESERVED.intersection(data.columns) or "No" in data:
        raise ValueError("Input must be merged observations, without No or supervised/reserved columns")
    _check_times(data["timestamp"])
    if not data["station"].map(lambda value: isinstance(value, str) and bool(value.strip()) and value == value.strip()).all():
        raise ValueError("station must contain nonempty, trimmed strings")
    if not pd.api.types.is_numeric_dtype(data["PM2.5"]) or pd.api.types.is_bool_dtype(data["PM2.5"]):
        raise ValueError("PM2.5 must be numeric with missing values represented as null")
    observed = data["PM2.5"].dropna().astype("float64")
    if not np.isfinite(observed).all() or observed.lt(0).any():
        raise ValueError("Observed PM2.5 must be finite and nonnegative")
    ordered = data.sort_values(["station", "timestamp"], kind="stable").reset_index(drop=True).copy()
    validate_temporal_integrity(ordered)
    lookup = ordered[["station", "timestamp", "PM2.5"]].rename(
        columns={"timestamp": "target_timestamp", "PM2.5": "target_pm25"})
    candidates = ordered.rename(columns={"timestamp": "input_timestamp"})
    candidates["target_timestamp"] = candidates["input_timestamp"] + pd.Timedelta(hours=1)
    if candidates["target_timestamp"].isna().any():
        raise ValueError("Target timestamp overflow")
    candidates = candidates.merge(lookup, on=["station", "target_timestamp"], how="left",
                                  validate="one_to_one", sort=False, indicator="_target_match")
    candidates["sample_id"] = [
        _sample_id(station, origin, target) for station, origin, target in
        candidates[["station", "input_timestamp", "target_timestamp"]].itertuples(index=False, name=None)
    ]
    if candidates["sample_id"].duplicated().any():
        raise ValueError("Duplicate sample ID")
    candidates["is_primary"] = candidates["PM2.5"].notna()
    last = ordered.groupby("station")["timestamp"].max()
    terminal = candidates["target_timestamp"].gt(candidates["station"].map(last))
    absent = candidates["_target_match"].eq("left_only")
    reason = pd.Series(pd.NA, index=candidates.index, dtype="string")
    reason.loc[terminal] = "end_of_series"
    reason.loc[absent & ~terminal] = "missing_target_timestamp"
    reason.loc[~absent & candidates["target_pm25"].isna()] = "missing_target_value"
    rejected = reason.notna()
    exclusions = candidates.loc[rejected, ID_COLUMNS].copy()
    exclusions = exclusions.rename(columns={"is_primary": "origin_pm25_observed"})
    exclusions["reason"] = reason.loc[rejected]
    samples = candidates.loc[~rejected].drop(columns="_target_match").reset_index(drop=True)
    exclusions = exclusions.reset_index(drop=True)
    records = []
    for station, group in candidates.groupby("station", sort=True):
        kept = samples.loc[samples["station"].eq(station)]
        dropped = exclusions.loc[exclusions["station"].eq(station)]
        record = {
            "station": station, "input_rows": len(group), "retained_operational": len(kept),
            "retained_primary": int(kept["is_primary"].sum()), "excluded_total": len(dropped),
            "missing_origin_pm25_total": int((~group["is_primary"]).sum()),
            "retained_missing_origin_pm25": int((~kept["is_primary"]).sum()),
        }
        record.update({f"excluded_{code}": int(dropped["reason"].eq(code).sum()) for code in EXCLUSION_REASONS})
        records.append(record)
    station_audit = pd.DataFrame(records)
    totals = {column: int(station_audit[column].sum()) for column in station_audit.columns if column != "station"}
    if totals["input_rows"] != totals["retained_operational"] + totals["excluded_total"]:
        raise ValueError("Sample accounting failed")
    if totals["excluded_total"] != sum(totals[f"excluded_{code}"] for code in EXCLUSION_REASONS):
        raise ValueError("Exclusion reasons do not reconcile")
    return SampleResult(samples, exclusions, station_audit, totals)


def temporal_split(samples, *, validation_start, test_start):
    """Assign [train, validation, test] by target timestamp, for every station."""
    validation_start, test_start = _timestamp(validation_start), _timestamp(test_start)
    if validation_start >= test_start:
        raise ValueError("validation_start must precede test_start")
    required = set(ID_COLUMNS) | {"target_pm25"}
    if not required.issubset(samples.columns):
        raise ValueError("Missing supervised sample columns")
    for column in ("input_timestamp", "target_timestamp"):
        _check_times(samples[column])
    if not (samples["target_timestamp"] - samples["input_timestamp"]).eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Every target must be exactly one hour after its origin")
    if samples["sample_id"].isna().any() or samples["sample_id"].duplicated().any() or samples["target_pm25"].isna().any():
        raise ValueError("Sample IDs must be unique and targets observed")
    result = samples.copy()
    result["split"] = np.select(
        [result["target_timestamp"].lt(validation_start), result["target_timestamp"].lt(test_start)],
        ["train", "validation"], default="test")
    return result


def summarize_splits(samples, *, by_station=False, station_names=None):
    """Only IDs/counts/date ranges: never target-value statistics or metrics."""
    records = []
    if by_station:
        names = sorted(samples["station"].unique() if station_names is None else station_names)
        groups = [(station, samples.loc[samples["station"].eq(station)]) for station in names]
    else:
        groups = [(None, samples)]
    for station, group in groups:
        for cohort in COHORTS:
            cohort_rows = group if cohort == "operational" else group.loc[group["is_primary"]]
            for split in SPLITS:
                selected = cohort_rows.loc[cohort_rows["split"].eq(split)]
                record = {"cohort": cohort, "split": split, "samples": len(selected),
                          "stations": int(selected["station"].nunique())}
                if by_station:
                    record["station"] = station
                for column in ("input_timestamp", "target_timestamp"):
                    for suffix, reducer in (("min", "min"), ("max", "max")):
                        record[f"{column}_{suffix}"] = _iso(getattr(selected[column], reducer)())
                records.append(record)
    columns = ["cohort", "split", "samples", "stations"] + (["station"] if by_station else [])
    columns += [f"{column}_{suffix}" for column in ("input_timestamp", "target_timestamp") for suffix in ("min", "max")]
    return pd.DataFrame(records, columns=columns)


def check_label_availability(fit_samples, evaluation_samples, *, fit_cutoff=None, strict_before_origin=False):
    """Check a *planned* fit's label availability; no estimator is fitted.

    Holdout allows equality: observations at t are known before issuing t+1.
    CV callers use strict_before_origin=True after purging labels at the origin.
    The check is global across stations for a shared model.
    """
    if fit_samples.empty or evaluation_samples.empty:
        raise ValueError("Cannot verify label availability for empty partitions")
    _check_times(fit_samples["target_timestamp"])
    _check_times(evaluation_samples["input_timestamp"])
    last_label = fit_samples["target_timestamp"].max()
    first_origin = evaluation_samples["input_timestamp"].min()
    cutoff = first_origin if fit_cutoff is None else _timestamp(fit_cutoff)
    if cutoff > first_origin or last_label > cutoff:
        raise ValueError("Fit labels are unavailable by the planned cutoff/first evaluation origin")
    if strict_before_origin and last_label >= first_origin:
        raise ValueError("CV fit target must strictly precede the first evaluation origin; purge boundary labels")
    return {"status": "passed", "fit_samples": len(fit_samples), "evaluation_samples": len(evaluation_samples),
            "latest_fit_target_timestamp": _iso(last_label), "first_evaluation_input_timestamp": _iso(first_origin),
            "planned_label_cutoff": _iso(cutoff), "comparison": "<" if strict_before_origin else "<=",
            "fitted": False}
