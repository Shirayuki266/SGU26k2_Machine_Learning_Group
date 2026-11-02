"""Build T05 sample snapshots from approved T04 outputs; no fit or evaluation."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
from uuid import uuid4

import pandas as pd

from beijing_air.data import RAW_COLUMNS, sha256
from beijing_air import samples as sample_module
from beijing_air.samples import (
    COHORTS, ID_COLUMNS, SPLITS, build_samples, check_label_availability,
    summarize_splits, temporal_split,
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def relative(root, path):
    return path.resolve().relative_to(root.resolve()).as_posix()


def describe_file(root, staged, final):
    return {"path": relative(root, final), "sha256": sha256(staged), "bytes": staged.stat().st_size}


def ids_digest(values):
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


@contextmanager
def staging_directory(parent, prefix):
    # Inherit the output parent's permissions. TemporaryDirectory's private
    # directory ACL would otherwise remain private after publishing by rename.
    path = parent / f"{prefix}{uuid4().hex}"
    path.mkdir()  # One attempt: permission errors fail immediately on Windows.
    try:
        yield path
    finally:
        if path.exists():
            if path.is_symlink() or path.resolve().parent != parent.resolve():
                raise ValueError("Refusing cleanup outside the staging parent")
            shutil.rmtree(path)


def print_summary(manifest, *, reused=False):
    print("Verified existing T05 snapshot" if reused else "Published T05 snapshot")
    print(f"Snapshot: {manifest['snapshot_id']}; mode={manifest['mode']}; not a model run")
    counts = manifest["totals"]
    print(f"Origins={counts['input_rows']}; operational={counts['retained_operational']}; "
          f"primary={counts['retained_primary']}; excluded={counts['excluded_total']}")
    for row in manifest["split_summary"]:
        print(f"{row['cohort']}/{row['split']}: n={row['samples']}; "
              f"target=[{row['target_timestamp_min']}, {row['target_timestamp_max']}]")


def verify_existing(root, dataset_dir, report_dir, signature):
    manifest_path = report_dir / "split_manifest.json"
    if not dataset_dir.exists() and not report_dir.exists():
        return None
    if not dataset_dir.is_dir() or not manifest_path.is_file():
        raise ValueError("Incomplete existing output; review it before running again (no automatic overwrite)")
    manifest = read_json(manifest_path)
    if manifest.get("status") != "complete" or manifest.get("signature") != signature:
        raise ValueError("Existing snapshot has different input/config/code; refusing overwrite")
    expected_files = {f"{split}_{kind}" for split in SPLITS for kind in ("samples", "ids")} | {
        "excluded_samples", "exclusion_summary.csv", "split_summary.csv", "station_split_summary.csv"}
    if manifest.get("snapshot_id") != canonical_hash(signature) or set(manifest.get("files", {})) != expected_files:
        raise ValueError("Existing snapshot manifest is incomplete or inconsistent")
    for info in manifest["files"].values():
        path = (root / info["path"]).resolve()
        if not (path.is_relative_to(dataset_dir) or path.is_relative_to(report_dir)):
            raise ValueError("Artifact path escapes snapshot directories")
        if not path.is_file() or path.stat().st_size != info["bytes"] or sha256(path) != info["sha256"]:
            raise ValueError(f"Existing artifact checksum differs: {info['path']}")
    return manifest


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "configs/default.json")
    parser.add_argument("--mode", choices=["smoke", "full"])
    parser.add_argument("--output-tag", help="New snapshot suffix, e.g. reproduce; keeps existing reports/data")
    args = parser.parse_args()
    if args.output_tag is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.output_tag):
        raise ValueError("output-tag must be 1-64 letters/digits/underscores/hyphens, starting with a letter/digit")
    config = read_json(args.config)
    mode = args.mode or config["mode"]
    if mode not in ("smoke", "full"):
        raise ValueError("Unsupported mode")
    if config["horizon_hours"] != 1 or config["problem"]["current_observation_available"] is not True:
        raise ValueError("T05 requires horizon=1 and current observations available before forecasting")
    problem_contract = {
        "task_type": "regression", "target_column": "PM2.5", "target_unit": "ug/m3",
        "group_column": "station", "input_time_column": "input_timestamp",
        "target_time_column": "target_timestamp", "station_scope": "observed_stations",
        "current_observation_available": True, "forecast_strategy": "rolling_one_hour",
    }
    if config["problem"] != problem_contract:
        raise ValueError("Unsupported PM2.5 problem contract; refusing to silently build a different target")
    split_config = config["split"]
    if split_config["timestamp_column"] != "target_timestamp" or split_config["timestamp_convention"] != "source_local_naive":
        raise ValueError("Unsupported split timestamp contract")
    construction = config["sample_construction"]
    expected = {
        "target_value_column": "target_pm25", "sample_id_scheme": "pm25-h1-v1",
        "target_missing_policy": "drop", "origin_missing_policy": "retain_operational_flag_primary",
        "holdout_label_rule": "at_or_before_first_origin",
    }
    if construction != expected:
        raise ValueError("Unsupported sample_construction contract")
    processed = (root / config["paths"]["processed_data"]).resolve()
    if not processed.is_relative_to(root):
        raise ValueError("processed_data must be inside this project")
    source = processed / f"merged_unimputed_{mode}.csv"
    quality_path = root / "reports" / f"quality_{mode}" / "summary.json"
    quality = read_json(quality_path)
    if (quality.get("status") != "passed" or not quality.get("merged_output_written")
            or quality.get("imputed") is not False or quality.get("outlier_removal") is not False
            or quality.get("mode") != mode):
        raise ValueError("Expected approved, unimputed T04 data for this mode")
    source_hash = sha256(source)
    if source_hash != quality["merged_sha256"]:
        raise ValueError("Merged input checksum differs from T04 audit")
    raw_manifest_path = root / "reports/data_manifest.json"
    raw_manifest = read_json(raw_manifest_path)
    if {Path(item["path"]).name: item["sha256"] for item in raw_manifest["files"]} != quality["raw_sha256"]:
        raise ValueError("T04 raw snapshot differs from the source manifest")
    signature = {
        "merged_sha256": source_hash, "quality_summary_sha256": sha256(quality_path),
        "raw_manifest_sha256": sha256(raw_manifest_path), "mode": mode, "seed": config["seed"],
        "output_tag": args.output_tag,
        "horizon_hours": config["horizon_hours"], "problem": problem_contract,
        "split": split_config, "sample_construction": construction,
        "module_sha256": sha256(Path(sample_module.__file__)), "script_sha256": sha256(Path(__file__)),
    }
    suffix = f"_{mode}" + (f"_{args.output_tag}" if args.output_tag else "")
    dataset_dir = processed / f"samples{suffix}"
    report_dir = root / "reports" / f"splits{suffix}"
    if not dataset_dir.resolve().is_relative_to(root) or not report_dir.resolve().is_relative_to(root):
        raise ValueError("Output directory escapes project")
    existing = verify_existing(root, dataset_dir, report_dir, signature)
    if existing is not None:
        print_summary(existing, reused=True)
        return
    frame = pd.read_csv(source, parse_dates=["timestamp"])
    expected_columns = [column for column in RAW_COLUMNS if column != "No"] + ["source_file", "source_row", "timestamp"]
    if list(frame.columns) != expected_columns or len(frame) != quality["output_rows"]:
        raise ValueError("T04 input schema/count differs from the audit")
    result = build_samples(frame, horizon_hours=config["horizon_hours"])
    samples = temporal_split(result.samples, validation_start=split_config["validation_start"],
                             test_start=split_config["test_start"])
    summary = summarize_splits(samples)
    by_station = summarize_splits(samples, by_station=True, station_names=result.station_audit["station"])
    if mode == "full" and (by_station["samples"].eq(0).any() or samples.empty):
        raise ValueError("Full snapshot requires every source station in every split/cohort; review coverage")
    availability = {}
    for cohort in COHORTS:
        selected = samples if cohort == "operational" else samples.loc[samples["is_primary"]]
        for name, fit_names, evaluation_name in (
            ("train_to_validation", ["train"], "validation"),
            ("train_validation_to_test_prospective", ["train", "validation"], "test"),
        ):
            fit = selected.loc[selected["split"].isin(fit_names)]
            evaluation = selected.loc[selected["split"].eq(evaluation_name)]
            key = f"{cohort}/{name}"
            availability[key] = (
                {"status": "not_evaluated_empty_partition", "fitted": False}
                if fit.empty or evaluation.empty else check_label_availability(fit, evaluation)
            )
    # No published manifest exists until both staged directories are complete.
    # A crash between renames is rejected as incomplete by verify_existing.
    processed.mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    with staging_directory(processed, f".samples-{mode}-") as data_stage, \
            staging_directory(root / "reports", f".splits-{mode}-") as report_stage:
        (data_stage / "sample_ids").mkdir()
        files, membership = {}, {}
        for split in SPLITS:
            selected = samples.loc[samples["split"].eq(split)]
            for name, content, staged, final in (
                (f"{split}_samples", selected, data_stage / f"{split}.csv", dataset_dir / f"{split}.csv"),
                (f"{split}_ids", selected[ID_COLUMNS], data_stage / "sample_ids" / f"{split}.csv", dataset_dir / "sample_ids" / f"{split}.csv"),
            ):
                content.to_csv(staged, index=False, na_rep="NA", date_format="%Y-%m-%d %H:%M:%S", lineterminator="\n")
                files[name] = describe_file(root, staged, final)
            membership[split] = {
                cohort: {"samples": len(group), "ordered_sample_ids_sha256": ids_digest(group["sample_id"])}
                for cohort in COHORTS
                for group in [selected if cohort == "operational" else selected.loc[selected["is_primary"]]]
            }
        excluded_path = data_stage / "excluded_samples.csv"
        result.exclusions.to_csv(excluded_path, index=False, date_format="%Y-%m-%d %H:%M:%S", lineterminator="\n")
        files["excluded_samples"] = describe_file(root, excluded_path, dataset_dir / excluded_path.name)
        for name, table in (("exclusion_summary.csv", result.station_audit), ("split_summary.csv", summary),
                            ("station_split_summary.csv", by_station)):
            staged = report_stage / name
            table.to_csv(staged, index=False, lineterminator="\n")
            files[name] = describe_file(root, staged, report_dir / name)
        # Recheck the exact inputs used, not a later mutated source snapshot.
        if sha256(source) != source_hash or sha256(quality_path) != signature["quality_summary_sha256"] or sha256(raw_manifest_path) != signature["raw_manifest_sha256"]:
            raise ValueError("Inputs changed during sample construction")
        manifest = {
            "schema_version": 1, "task_id": "T05", "artifact_type": "data_preparation_audit",
            "snapshot_id": canonical_hash(signature), "status": "complete", "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(), "signature": signature,
            "source": relative(root, source), "raw_manifest": relative(root, raw_manifest_path),
            "t04_summary": relative(root, quality_path), "config": relative(root, args.config),
            "python_version": platform.python_version(), "pandas_version": pd.__version__,
            "input_scope": "full T04 observations" if mode == "full" else "T04 smoke prefix; terminal exclusions are prefix-relative",
            "totals": result.totals, "split_summary": json.loads(summary.to_json(orient="records")),
            "membership": membership, "label_availability": availability, "files": files,
            "test_use": "target construction and count/date audit only; no exploration, fit or metrics",
            "model_experiment_run": False,
        }
        (report_stage / "split_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.rename(data_stage, dataset_dir)
        os.rename(report_stage, report_dir)
    print_summary(manifest)


if __name__ == "__main__":
    main()
