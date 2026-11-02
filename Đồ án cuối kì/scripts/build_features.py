"""Build T07 train A/B from verified T05 IDs and T04 observation prefixes.

Only train is materialized here. Future tasks can call the pure module for
rolling origins with an explicitly authorized history; no holdout CSV is read.
"""

import argparse
import json
from pathlib import Path
import platform
import re
import sys
from datetime import datetime, timezone

import pandas as pd
from pandas.testing import assert_frame_equal

from beijing_air import features as feature_module
from beijing_air.data import MEASUREMENTS, load_station_data, sha256
from beijing_air.eda import load_training_data, project_path
from beijing_air.features import build_features, missing_summary
# Portable Python's isolated _pth omits the script directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_samples import canonical_hash, describe_file, read_json, staging_directory


def load_train_history(root, train, split_manifest):
    """Reuse T04 loader on bounded raw prefixes, restoring dropped-origin history.

    The approved UCI snapshot has complete hourly keys in each station file.
    Its T04 count/date audit establishes the prefix length; fail if that
    precondition changes. Hash entire files for identity only; values entering
    a DataFrame stop at the last requested train origin. No raw audit is saved
    again, and original merged data/raw/audits remain untouched.
    """
    quality_path = root / "reports/quality_full/summary.json"
    raw_path = root / "reports/data_manifest.json"
    stations_path = root / "reports/quality_full/stations.csv"
    quality, raw = read_json(quality_path), read_json(raw_path)
    station_audit = pd.read_csv(stations_path, parse_dates=["timestamp_min", "timestamp_max"])
    expected = split_manifest["signature"]
    if (quality.get("status") != "passed" or quality.get("imputed") is not False
            or quality.get("outlier_removal") is not False
            or quality["merged_sha256"] != expected["merged_sha256"]
            or sha256(quality_path) != expected["quality_summary_sha256"]
            or sha256(raw_path) != expected["raw_manifest_sha256"]):
        raise ValueError("Approved T04/T05 source provenance differs")
    if not station_audit.missing_hours_internal.eq(0).all() or station_audit.timestamp_min.nunique() != 1:
        raise ValueError("Bounded UCI prefix loading requires the approved regular T04 timeline; supply vetted history to module instead")
    start, cutoff = station_audit.timestamp_min.iloc[0], train.input_timestamp.max()
    hours = int((cutoff-start)/pd.Timedelta(hours=1))+1
    if hours < 1 or cutoff >= pd.Timestamp(expected["split"]["validation_start"])-pd.Timedelta(hours=1):
        raise ValueError("History must stop at the requested train origin")
    paths = [project_path(root, info["path"]) for info in raw["files"]]
    hashes = {path.name: info["sha256"] for path, info in zip(paths, raw["files"])}
    if hashes != quality["raw_sha256"] or set(train.station) != set(station_audit.station):
        raise ValueError("Station inventory differs from approved snapshot")
    loaded = load_station_data(paths, rows_per_file=hours, expected_hashes=hashes)
    history = loaded.data
    for station, group in history.groupby("station", sort=True):
        times = pd.DatetimeIndex(group.timestamp)
        if not times.equals(pd.date_range(start, cutoff, freq="h")):
            raise ValueError(f"Raw file is not the audited chronological prefix: {station}")
    return history, {"method": "T04_load_station_data_bounded_prefix", "raw_sha256": hashes,
                     "raw_values_scope": "train_origin_prefix_only; full raw files hashed for identity",
                     "quality_summary_sha256": sha256(quality_path), "stations_audit_sha256": sha256(stations_path),
                     "rows_per_station": hours, "observation_rows": len(history),
                     "first_timestamp": str(start), "last_timestamp": str(cutoff)}


def verify_existing(root, report, dataset, signature):
    if not report.exists() and not dataset.exists():
        return None
    path = report / "feature_manifest.json"
    if not path.is_file() or not dataset.is_dir():
        raise ValueError("Incomplete existing features; inspect or use a new output tag")
    manifest = read_json(path)
    expected_files = {"train_A", "train_B", "sample_metadata", "feature_registry", "missing_summary", "station_missing_summary"}
    if (manifest.get("status") != "complete" or manifest.get("signature") != signature
            or manifest.get("snapshot_id") != canonical_hash(signature)
            or set(manifest.get("files", {})) != expected_files):
        raise ValueError("Existing features have different input/config/code; use a new output tag")
    for info in manifest["files"].values():
        artifact = project_path(root, info["path"])
        if not (artifact.is_relative_to(report) or artifact.is_relative_to(dataset)):
            raise ValueError("Feature artifact escapes its snapshot")
        if artifact.stat().st_size != info["bytes"] or sha256(artifact) != info["sha256"]:
            raise ValueError("Existing feature artifact checksum differs")
    print(f"Verified existing T07 {manifest['mode']} features; {manifest['rows']} samples; no overwrite")
    return manifest


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--split-manifest", default="reports/splits_full/split_manifest.json")
    parser.add_argument("--output-tag")
    args = parser.parse_args()
    if args.output_tag is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.output_tag):
        raise ValueError("Invalid output tag")
    config = read_json(root / "configs/default.json")
    train, provenance = load_training_data(root, args.split_manifest)
    if provenance["source_mode"] != "full":
        raise ValueError("T07 requires the verified full train snapshot, even for smoke prefix checks")
    if args.mode == "smoke":
        train = train.groupby("station", sort=True).head(336).reset_index(drop=True)
    split_manifest = read_json(project_path(root, args.split_manifest))
    history, history_scope = load_train_history(root, train, split_manifest)
    signature = {"task_id": "T07", "schema_version": "t07-ab-v1", "mode": args.mode,
                 "output_tag": args.output_tag, "features": config["features"], "seed": config["seed"],
                 "horizon_hours": config["horizon_hours"], "split": config["split"],
                 "smoke_rows_per_station": 336 if args.mode == "smoke" else None,
                 "train_provenance": provenance, "history_scope": history_scope,
                 "module_sha256": sha256(Path(feature_module.__file__)), "script_sha256": sha256(Path(__file__))}
    suffix = args.mode + (f"_{args.output_tag}" if args.output_tag else "")
    report = root / "reports" / f"features_{suffix}"
    dataset = root / config["paths"]["processed_data"] / f"features_{suffix}"
    dataset = project_path(root, dataset)
    if verify_existing(root, report, dataset, signature):
        return
    result = build_features(history, train, config=config)
    # Compare raw current values against the approved T05 origins, not labels.
    current = MEASUREMENTS + ["station", "wd"]
    assert_frame_equal(result.features[current].reset_index(drop=True), train[current].reset_index(drop=True),
                       check_dtype=False, check_names=False, rtol=1e-12, atol=1e-12)
    with staging_directory(dataset.parent, ".features-") as staged_data, staging_directory(report.parent, ".features-") as staged_report:
        files = {}
        for name in ("A", "B"):
            path = staged_data / f"train_{name}.csv"
            result.select(name).to_csv(path, index=True, na_rep="NA", encoding="utf-8", lineterminator="\n")
            files[f"train_{name}"] = describe_file(root, path, dataset / path.name)
        metadata_path = staged_data / "sample_metadata.csv"
        result.sample_metadata.to_csv(metadata_path, index=True, encoding="utf-8", lineterminator="\n")
        files["sample_metadata"] = describe_file(root, metadata_path, dataset / metadata_path.name)
        for name, table in (("feature_registry", result.registry), ("missing_summary", missing_summary(result)),
                            ("station_missing_summary", missing_summary(result, by_station=True))):
            path = staged_report / f"{name}.csv"
            table.to_csv(path, index=False, na_rep="NA", encoding="utf-8", lineterminator="\n")
            files[name] = describe_file(root, path, report / path.name)
        manifest = {"task_id": "T07", "artifact_type": "causal_feature_preparation", "schema_version": "t07-ab-v1",
                    "status": "complete", "model_experiment_run": False, "mode": args.mode,
                    "created_at": datetime.now(timezone.utc).isoformat(), "signature": signature,
                    "snapshot_id": canonical_hash(signature), "rows": len(train), "primary_rows": int(train.is_primary.sum()),
                    "feature_counts": {name: len(result.select(name).columns) for name in ("A", "B")},
                    "input_timestamp_min": str(train.input_timestamp.min()), "input_timestamp_max": str(train.input_timestamp.max()),
                    "target_timestamp_min": str(train.target_timestamp.min()), "target_timestamp_max": str(train.target_timestamp.max()),
                    "python_version": platform.python_version(), "pandas_version": pd.__version__,
                    "sample_membership_unchanged": result.features.index.tolist() == train.sample_id.tolist(),
                    "test_csv_accessed": False, "fit_performed": False, "files": files}
        (staged_report / "feature_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")
        staged_data.rename(dataset)
        staged_report.rename(report)
    print(f"Published T07 {args.mode}: {manifest['rows']} samples, {manifest['feature_counts']}; no model run")
    print(f"Snapshot: {manifest['snapshot_id']}")


if __name__ == "__main__":
    main()
