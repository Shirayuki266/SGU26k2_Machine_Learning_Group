"""Verified train/validation identities and bounded observation history; no test I/O."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from beijing_air.data import load_station_data, sha256
from beijing_air.eda import ids_digest, load_training_data, project_path, read_json
from beijing_air.features import _requests
from beijing_air.samples import ID_COLUMNS, check_label_availability


def load_train_validation(root, manifest_path="reports/splits_full/split_manifest.json"):
    root = Path(root).resolve()
    train, provenance = load_training_data(root, manifest_path)
    manifest = read_json(project_path(root, manifest_path))
    if manifest["mode"] != "full":
        raise ValueError("Official evaluation requires full T05 snapshot")
    frames, infos = {}, {}
    needed = [*ID_COLUMNS, "split", "PM2.5", "target_pm25"]
    for key in ("validation_samples", "validation_ids"):
        info = manifest["files"][key]
        path = project_path(root, info["path"])
        if path.name != "validation.csv":
            raise ValueError("Only validation.csv may be opened for evaluation")
        if path.stat().st_size != info["bytes"] or sha256(path) != info["sha256"]:
            raise ValueError("Validation checksum differs from T05")
        frames[key] = pd.read_csv(path, usecols=needed if key == "validation_samples" else ID_COLUMNS,
                                  na_values=["NA"], parse_dates=["input_timestamp", "target_timestamp"])
        infos[key] = info
    validation, ids = frames["validation_samples"], frames["validation_ids"]
    _requests(validation)
    split = manifest["signature"]["split"]
    if (not validation.split.eq("validation").all()
            or not validation.target_timestamp.ge(pd.Timestamp(split["validation_start"])).all()
            or not validation.target_timestamp.lt(pd.Timestamp(split["test_start"])).all()
            or validation.target_pm25.isna().any() or not np.isfinite(validation.target_pm25).all()
            or validation.target_pm25.lt(0).any()):
        raise ValueError("Invalid validation boundary or target")
    if not validation.is_primary.equals(validation["PM2.5"].notna()) or not validation[ID_COLUMNS].equals(ids[ID_COLUMNS]):
        raise ValueError("Validation IDs/current-value cohort differs")
    for cohort, part in (("operational", validation), ("primary", validation.loc[validation.is_primary])):
        expected = manifest["membership"]["validation"][cohort]
        if len(part) != expected["samples"] or ids_digest(part.sample_id) != expected["ordered_sample_ids_sha256"]:
            raise ValueError("Validation membership differs from T05")
    availability = check_label_availability(train, validation)
    provenance.update(validation_files=infos, validation_membership=manifest["membership"]["validation"],
                      label_availability=availability)
    return train[needed].copy(), validation, provenance


def freeze_validation_ids(root, validation, provenance, path="reports/evaluation/validation_manifest.json"):
    """Anchor existing T05 ID files instead of making a parallel sample store."""
    root = Path(root).resolve()
    anchor = {"schema_version": "validation-cohorts-v1", "split": "validation", "test_locked": True,
              "t05_snapshot_id": provenance["t05_snapshot_id"], "files": provenance["validation_files"],
              "cohorts": provenance["validation_membership"], "order": "T05 station/input_timestamp order",
              "primary_filter": "is_primary == true", "operational_filter": "all retained T05 validation IDs",
              "comparison_rule": "same IDs/order; no dropping rows for missing features; report prediction coverage"}
    for cohort, subset in (("operational", validation), ("primary", validation.loc[validation.is_primary])):
        if len(subset) != anchor["cohorts"][cohort]["samples"] or ids_digest(subset.sample_id) != anchor["cohorts"][cohort]["ordered_sample_ids_sha256"]:
            raise ValueError("Cannot freeze an altered validation cohort")
    destination = project_path(root, path)
    if destination.exists():
        if read_json(destination) != anchor:
            raise ValueError("Frozen validation anchor differs; never silently replace comparison IDs")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: a concurrent different writer cannot overwrite an anchor.
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(anchor, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    return destination, anchor


def load_validation_history(root, evaluation, provenance):
    """Reuse T04 loader on the approved regular UCI prefix through last origin."""
    root = Path(root).resolve()
    manifest = read_json(project_path(root, provenance["split_manifest"]))
    quality_path, raw_path = root / manifest["t04_summary"], root / manifest["raw_manifest"]
    quality, raw = read_json(quality_path), read_json(raw_path)
    station_path = quality_path.parent / "stations.csv"
    stations = pd.read_csv(station_path, parse_dates=["timestamp_min"])
    expected = manifest["signature"]
    if (quality.get("status") != "passed" or quality.get("imputed") is not False or quality.get("outlier_removal") is not False
            or quality["merged_sha256"] != expected["merged_sha256"]
            or sha256(quality_path) != expected["quality_summary_sha256"] or sha256(raw_path) != expected["raw_manifest_sha256"]):
        raise ValueError("T04 provenance differs from T05")
    if not stations.missing_hours_internal.eq(0).all() or stations.timestamp_min.nunique() != 1:
        raise ValueError("UCI prefix loader requires audited regular station timelines")
    first, cutoff = stations.timestamp_min.iloc[0], evaluation.input_timestamp.max()
    if cutoff >= pd.Timestamp(expected["split"]["test_start"])-pd.Timedelta(hours=1):
        raise ValueError("Observation prefix would cross the authorized validation origin range")
    hours = int((cutoff-first)/pd.Timedelta(hours=1))+1
    if hours < 1:
        raise ValueError("Empty history prefix")
    paths = [project_path(root, info["path"]) for info in raw["files"]]
    hashes = {path.name: info["sha256"] for path, info in zip(paths, raw["files"])}
    if hashes != quality["raw_sha256"] or not set(evaluation.station).issubset(set(stations.station)):
        raise ValueError("Raw inventory differs")
    loaded = load_station_data(paths, rows_per_file=hours, expected_hashes=hashes)
    history = loaded.data[["station", "timestamp", "PM2.5"]].copy()
    for _, group in history.groupby("station"):
        if not pd.DatetimeIndex(group.timestamp).equals(pd.date_range(first, cutoff, freq="h")):
            raise ValueError("Raw prefix differs from audited chronological hourly grid")
    return history, {"raw_sha256": hashes, "rows": len(history), "rows_per_station": hours,
                     "first_timestamp": str(first), "last_timestamp": str(cutoff),
                     "values_scope": "observations through selected validation origins only",
                     "hash_scope": "full raw byte identity, no test CSV/IDs opened", "test_csv_accessed": False}
