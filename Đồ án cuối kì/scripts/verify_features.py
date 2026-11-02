"""Recompute T07 train features/audits and reproduce a label-free forecast."""

import argparse
from io import StringIO
from pathlib import Path
import sys

import pandas as pd
from pandas.testing import assert_frame_equal

from beijing_air import features as feature_module
from beijing_air.data import sha256
from beijing_air.eda import load_training_data, project_path, read_json
from beijing_air.features import build_features, features_for_prediction, missing_summary

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_features import load_train_history
from build_samples import canonical_hash


def csv_form(table, *, index=False):
    return pd.read_csv(StringIO(table.to_csv(index=index, na_rep="NA")))


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="reports/features_full")
    args = parser.parse_args()
    manifest = read_json(project_path(root, args.report) / "feature_manifest.json")
    signature = manifest["signature"]
    config = read_json(root / "configs/default.json")
    assert manifest["status"] == "complete" and manifest["task_id"] == "T07"
    assert not manifest["fit_performed"] and not manifest["model_experiment_run"] and not manifest["test_csv_accessed"]
    assert manifest["snapshot_id"] == canonical_hash(signature)
    assert signature["features"] == config["features"] and signature["split"] == config["split"]
    assert signature["module_sha256"] == sha256(Path(feature_module.__file__))
    assert signature["script_sha256"] == sha256(root / "scripts/build_features.py")
    expected_files = {"train_A": "train_A.csv", "train_B": "train_B.csv", "sample_metadata": "sample_metadata.csv",
                      "feature_registry": "feature_registry.csv", "missing_summary": "missing_summary.csv",
                      "station_missing_summary": "station_missing_summary.csv"}
    assert set(manifest["files"]) == set(expected_files)
    for name, info in manifest["files"].items():
        path = project_path(root, info["path"])
        assert path.name == expected_files[name]
        assert path.stat().st_size == info["bytes"] and sha256(path) == info["sha256"], path
    train, provenance = load_training_data(root, signature["train_provenance"]["split_manifest"])
    assert provenance == signature["train_provenance"]
    if manifest["mode"] == "smoke":
        train = train.groupby("station", sort=True).head(signature["smoke_rows_per_station"]).reset_index(drop=True)
    history, scope = load_train_history(root, train, read_json(project_path(root, provenance["split_manifest"])))
    assert scope == signature["history_scope"]
    result = build_features(history, train, config=config)
    assert len(result.features) == manifest["rows"] and train.is_primary.sum() == manifest["primary_rows"]
    assert result.features.index.tolist() == train.sample_id.tolist() and manifest["sample_membership_unchanged"]
    for name in ("A", "B"):
        saved = pd.read_csv(project_path(root, manifest["files"][f"train_{name}"]["path"]))
        expected = csv_form(result.select(name), index=True)
        assert_frame_equal(saved, expected, check_dtype=False, rtol=1e-9, atol=1e-9)
        assert len(saved.columns)-1 == manifest["feature_counts"][name]
    assert_frame_equal(pd.read_csv(project_path(root, manifest["files"]["sample_metadata"]["path"])),
                       csv_form(result.sample_metadata, index=True), check_dtype=False)
    for name, computed in (("feature_registry", result.registry), ("missing_summary", missing_summary(result)),
                           ("station_missing_summary", missing_summary(result, by_station=True))):
        saved = pd.read_csv(project_path(root, manifest["files"][name]["path"]))
        assert_frame_equal(saved, csv_form(computed), check_dtype=False, rtol=1e-10, atol=1e-10)
    # Each station's last train sample is reproduced with only its 25-hour
    # observation buffer. No target value or observed row at t+1 is provided.
    for row in train.groupby("station", sort=True).tail(1).itertuples():
        buffer = history.loc[history.station.eq(row.station) & history.timestamp.between(
            row.input_timestamp-pd.Timedelta(hours=24), row.input_timestamp)]
        single = features_for_prediction(buffer, station=row.station, origin=row.input_timestamp, config=config)
        assert_frame_equal(single.features, result.features.loc[[row.sample_id]], check_dtype=False, rtol=1e-8, atol=1e-7)
    print(f"PASS: {len(train)} train IDs; A/B matrices and all missing/registry tables recomputed; {train.station.nunique()} label-free forecasts reproduced")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
