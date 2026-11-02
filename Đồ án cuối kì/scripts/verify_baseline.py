"""Verify T09 runs without creating experiments; optionally bundle the ledger."""

import argparse
import csv
from dataclasses import asdict
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
import sys
import zipfile

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from beijing_air.baseline import fit_persistence, predict_persistence
from beijing_air.data import sha256
from beijing_air.eda import read_json
from beijing_air.evaluation import load_train_validation, load_validation_history
from beijing_air.metrics import evaluate_predictions, grouped_metrics

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import source_files


def close_metrics(actual, expected):
    assert set(actual) == set(expected)
    for key, value in actual.items():
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            assert np.isclose(value, expected[key], rtol=1e-12, atol=1e-12), key
        else:
            assert value == expected[key], key


def verify_run(root, run_id):
    root = Path(root).resolve()
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Invalid run ID")
    directory = root / "artifacts/experiments" / run_id
    config, metadata, recorded = [read_json(directory / f"{name}.json") for name in ("config", "metadata", "metrics")]
    assert metadata["run_id"] == run_id and metadata["status"] == "completed" and metadata["error"] is None
    assert config["task_id"] in ("T09", "TEST_ONLY_T09") and config["model"] == "persistence"
    assert metadata["started_at"] and metadata["ended_at"] and metadata["duration_seconds"] >= 0
    assert config["seed"] is None and config["parameters"]["randomness_used"] is False
    assert recorded["test_csv_accessed"] is False
    signature = config["parameters"]["signature"]
    assert {name: sha256(path) for name, path in source_files().items()} == signature["source_sha256"]
    for info in metadata["artifacts"]:
        path = (root / "experiments" / info["path"]).resolve()
        assert path.is_relative_to(directory.resolve())
        assert path.is_file() and path.stat().st_size == info["size_bytes"] and sha256(path) == info["sha256"]
    with (root / "experiments/experiment_log.csv").open(encoding="utf-8", newline="") as stream:
        matches = [row for row in csv.DictReader(stream) if row["run_id"] == run_id]
    assert len(matches) == 1 and matches[0]["status"] == "completed"
    for name in ("config", "metrics", "metadata", "notes"):
        path = (root / "experiments" / matches[0][f"{name}_path"]).resolve()
        assert path == directory / ("notes.md" if name == "notes" else f"{name}.json")
    assert json.loads(matches[0]["metrics"]) == recorded
    assert json.loads(matches[0]["artifacts"]) == metadata["artifacts"]
    train, validation, provenance = load_train_validation(root, config["data"]["provenance"]["split_manifest"])
    assert provenance == config["data"]["provenance"]
    anchor = read_json(directory / "artifacts/data/validation_manifest.json")
    assert anchor == read_json(root / "reports/evaluation/validation_manifest.json")
    assert anchor["cohorts"] == provenance["validation_membership"]
    if config["mode"] == "smoke":
        validation = validation.groupby("station", sort=True).head(signature["baseline_config"]["smoke_rows_per_station"])
    validation = validation.reset_index(drop=True)
    ids = pd.read_csv(directory / "artifacts/data/evaluation_ids.csv", parse_dates=["input_timestamp", "target_timestamp"])
    assert_frame_equal(ids, validation[ids.columns].reset_index(drop=True), check_dtype=False)
    predictions = pd.read_csv(directory / "artifacts/predictions/validation.csv",
                              parse_dates=["input_timestamp", "target_timestamp", "last_observed_timestamp"])
    assert predictions.sample_id.tolist() == validation.sample_id.tolist()
    assert predictions.run_id.eq(run_id).all() and predictions["split"].eq("validation").all()
    np.testing.assert_allclose(predictions.y_true, validation.target_pm25, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(predictions.residual, predictions.y_pred-predictions.y_true, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(predictions.abs_error, predictions.residual.abs(), rtol=1e-12, atol=1e-12)
    state = fit_persistence(train)
    assert asdict(state) == read_json(directory / "artifacts/model/baseline_state.json")
    history, scope = load_validation_history(root, validation, provenance)
    assert scope == config["data"]["history_scope"]
    recomputed = predict_persistence(state, validation, history, max_history_age_hours=signature["baseline_config"]["max_history_age_hours"])
    assert_frame_equal(predictions[recomputed.columns], recomputed, check_dtype=False, rtol=1e-12, atol=1e-12)
    actual = evaluate_predictions(predictions, validation.sample_id)
    for cohort, values in actual.items():
        close_metrics(values, recorded[f"validation_{cohort}"])
    table = pd.read_csv(directory / "artifacts/tables/metrics.csv")
    for row in table.to_dict("records"):
        for metric in ("MAE", "RMSE", "R2", "fallback_rate", "n_total", "n_scored"):
            expected = actual[row["cohort"]][metric]
            assert (pd.isna(row[metric]) and expected is None) or np.isclose(row[metric], expected, rtol=1e-12, atol=1e-12)
    for column, name in (("station", "station_metrics"), ("target_month", "month_metrics")):
        expected = grouped_metrics(predictions, column)
        saved = pd.read_csv(directory / f"artifacts/tables/{name}.csv")
        expected_csv = pd.read_csv(StringIO(expected.to_csv(index=False, na_rep="NA")))
        assert_frame_equal(saved, expected_csv, check_dtype=False, rtol=1e-12, atol=1e-12)
    print(f"PASS {config['mode']} {run_id}: IDs, causal predictions, medians, metrics, CSV links and all artifact hashes")
    return {"run_id": run_id, "mode": config["mode"], "metrics": actual}


def package_ledger(root, destination):
    """Bundle real run trees + CSV; do not invent or import run history."""
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if not destination.is_relative_to(root) or destination.exists():
        raise ValueError("Bundle must be a new path inside this project")
    index = root / "experiments/experiment_log.csv"
    with index.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or len({r["run_id"] for r in rows}) != len(rows):
        raise ValueError("Invalid experiment index")
    paths = [index]
    for row in rows:
        if row["task_id"] not in ("T09", "TEST_ONLY_T09") or row["status"] not in ("completed", "failed", "interrupted"):
            raise ValueError("T09 bundle requires a terminal T09-only ledger; do not overwrite other task histories")
        run_id = row["run_id"]
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Invalid indexed run ID")
        paths.extend(p for p in (root / "artifacts/experiments" / run_id).rglob("*") if p.is_file())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(paths):
            if not path.resolve().is_relative_to(root):
                raise ValueError("Run artifact escapes project")
            archive.write(path, path.relative_to(root).as_posix())
    contents = {p.relative_to(root).as_posix(): sha256(p) for p in paths}
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == set(contents) and archive.testzip() is None
        for name, digest in contents.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    summary = {"bundle": destination.relative_to(root).as_posix(), "sha256": sha256(destination),
               "bytes": destination.stat().st_size, "run_ids": [r["run_id"] for r in rows], "files": contents,
               "note": "Snapshot of actual CSV and run artifacts; restore to a new clone, never overwrite a newer ledger."}
    destination.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(f"PASS bundle: {len(paths)} verified files, {destination.stat().st_size} bytes")
    return summary


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", nargs="+", required=True)
    parser.add_argument("--bundle", help="New project-relative ZIP path; includes the entire T09 ledger and run trees")
    args = parser.parse_args()
    for run_id in args.run_id:
        verify_run(root, run_id)
    if args.bundle:
        package_ledger(root, root / args.bundle)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
