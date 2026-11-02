"""TEST_ONLY causal/metric/logger fixtures. No project data or official runs."""

from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from beijing_air.baseline import fit_persistence, predict_persistence
from beijing_air.data import MEASUREMENTS, RAW_COLUMNS, load_station_data, sha256
from beijing_air.eda import ids_digest, read_json
from beijing_air.evaluation import freeze_validation_ids, load_train_validation
from beijing_air.metrics import evaluate_predictions, regression_metrics
from beijing_air.samples import ID_COLUMNS, _sample_id, build_samples, temporal_split


ROOT = Path(__file__).resolve().parents[1]


def request(station, origin, *, primary=None):
    origin = pd.Timestamp(origin)
    target = origin+pd.Timedelta(hours=1)
    result = {"station": station, "input_timestamp": origin, "target_timestamp": target,
              "sample_id": _sample_id(station, origin, target)}
    if primary is not None:
        result["is_primary"] = primary
    return result


def history(station, start, values):
    return pd.DataFrame({"station": station, "timestamp": pd.date_range(start, periods=len(values), freq="h"),
                         "PM2.5": pd.Series(values, dtype=float)})


def training():
    return pd.concat([history("TEST_ONLY_A", "2014-01-01", [10, 20, 30]),
                      history("TEST_ONLY_B", "2014-01-01", [100, 200, 300])], ignore_index=True).rename(
                          columns={"timestamp": "input_timestamp"}).assign(split="train")


def test_persistence_and_exact_age_limit_not_row_count():
    observed = history("TEST_ONLY_A", "2015-01-01", [9]+[None]*26)
    queries = pd.DataFrame([request("TEST_ONLY_A", "2015-01-01"), request("TEST_ONLY_A", "2015-01-02"),
                            request("TEST_ONLY_A", "2015-01-02 01:00")])
    result = predict_persistence(fit_persistence(training()), queries, observed, max_history_age_hours=24)
    assert result.y_pred.tolist() == [9., 9., 20.]
    assert result.prediction_source.tolist() == ["persistence", "last_observed_same_station", "training_station_median"]
    assert result.history_age_hours.tolist() == [0., 24., 25.]
    assert result.fallback.tolist() == [False, True, True]
    # Remove most intermediate hours: a 25h-old reading must not become 1h old.
    gap = observed.iloc[[0, 25]]
    assert predict_persistence(fit_persistence(training()), queries.iloc[[2]], gap).y_pred.iloc[0] == 20.


def test_no_cross_station_and_station_then_global_train_medians():
    observed = pd.concat([history(s, "2015-01-01", [None]) for s in ["TEST_ONLY_A", "TEST_ONLY_B", "TEST_ONLY_NEW"]], ignore_index=True)
    queries = pd.DataFrame([request(s, "2015-01-01") for s in observed.station])
    result = predict_persistence(fit_persistence(training()), queries, observed)
    assert result.y_pred.tolist() == [20., 200., 65.]
    assert result.prediction_source.tolist() == ["training_station_median", "training_station_median", "training_global_median"]


def test_future_changes_and_request_labels_never_change_past_predictions():
    observed = history("TEST_ONLY_A", "2015-01-01", [10, None, 20, None, 40])
    queries = pd.DataFrame([request("TEST_ONLY_A", "2015-01-01 01:00"), request("TEST_ONLY_A", "2015-01-01 03:00")])
    state = fit_persistence(training())
    before = predict_persistence(state, queries, observed)
    changed = observed.copy()
    changed.loc[changed.timestamp.gt(pd.Timestamp("2015-01-01 01:00")), "PM2.5"] = 9999
    queries["target_pm25"] = 99999999
    after = predict_persistence(state, queries, changed)
    assert_frame_equal(before.iloc[[0]], after.iloc[[0]])
    assert before.y_pred.iloc[1] != after.y_pred.iloc[1]
    assert asdict(state)["station_medians"] == {"TEST_ONLY_A": 20., "TEST_ONLY_B": 200.}


def test_unavailable_is_reported_when_no_training_or_history_value():
    train = training()
    train["PM2.5"] = np.nan
    state = fit_persistence(train)
    observed = history("TEST_ONLY_A", "2015-01-01", [None])
    predicted = predict_persistence(state, pd.DataFrame([request("TEST_ONLY_A", "2015-01-01")]), observed)
    assert predicted.y_pred.isna().all() and predicted.prediction_source.eq("unavailable").all()
    result = regression_metrics([1.], predicted.y_pred, allow_unavailable=True)
    assert result["coverage"] == 0 and result["MAE"] is None and result["unavailable"] == 1


@pytest.mark.parametrize("bad", ["holdout_statistics", "duplicate_id", "missing_origin", "primary_flag", "negative", "age"])
def test_invalid_or_leaking_contract_is_rejected(bad):
    train = training()
    observed = history("TEST_ONLY_A", "2015-01-01", [10.])
    queries = pd.DataFrame([request("TEST_ONLY_A", "2015-01-01", primary=True)])
    if bad == "holdout_statistics":
        with pytest.raises(ValueError): fit_persistence(train.assign(split="validation"))
        return
    state = fit_persistence(train)
    if bad == "duplicate_id": queries = pd.concat([queries, queries], ignore_index=True)
    elif bad == "missing_origin": observed["timestamp"] -= pd.Timedelta(hours=1)
    elif bad == "primary_flag": queries["is_primary"] = False
    elif bad == "negative": observed["PM2.5"] = -1.
    with pytest.raises(ValueError):
        predict_persistence(state, queries, observed, max_history_age_hours=0 if bad == "age" else 24)


def test_shared_metrics_known_values_and_negative_r2():
    result = regression_metrics([1, 2, 3], [1, 2, 5])
    assert result["MAE"] == pytest.approx(2/3)
    assert result["RMSE"] == pytest.approx(np.sqrt(4/3))
    assert result["R2"] == pytest.approx(-1.)
    assert result["n_total"] == result["n_scored"] == 3 and result["coverage"] == 1
    assert regression_metrics([1, 2], [1, 2])["R2"] == 1.


@pytest.mark.parametrize("truth,predicted,reason", [([1], [2], "fewer_than_two_predictions"),
                                                  ([1, 1], [1, 1], "constant_target"), ([], [], "no_scored_predictions")])
def test_undefined_metrics_are_null_not_fabricated(truth, predicted, reason):
    result = regression_metrics(truth, predicted)
    assert result["R2"] is None and result["r2_undefined_reason"] == reason
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("truth,predicted", [([1, np.nan], [1, 1]), ([1], [np.inf]), ([1, 2], [1]), ([[1]], [[1]]), ([1], [np.nan])])
def test_metric_input_errors_do_not_silently_drop_rows(truth, predicted):
    with pytest.raises(ValueError): regression_metrics(truth, predicted)


def test_metric_ids_and_cohort_denominators_are_explicit():
    predictions = pd.DataFrame({"sample_id": ["TEST_ONLY_1", "TEST_ONLY_2"], "is_primary": [True, False],
                                "y_true": [10., 100.], "y_pred": [12., 40.], "prediction_source": ["persistence", "training_station_median"]})
    results = evaluate_predictions(predictions, predictions.sample_id)
    assert results["primary"]["MAE"] == 2 and results["operational"]["MAE"] == 31
    assert results["primary"]["fallback_rate"] == 0 and results["operational"]["fallback_rate"] == .5
    with pytest.raises(ValueError): evaluate_predictions(predictions, predictions.sample_id[::-1])
    with pytest.raises(ValueError): evaluate_predictions(pd.concat([predictions, predictions.iloc[[0]]]), predictions.sample_id)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "TEST_ONLY_baseline_project"
    for path in ("configs", "data/raw", "data/processed/samples_full/sample_ids", "reports/splits_full", "reports/quality_full"):
        (root / path).mkdir(parents=True, exist_ok=True)
    for name in ("default.json", "baseline.json", "preprocessing.json"):
        shutil.copyfile(ROOT / "configs" / name, root / "configs" / name)
    paths = []
    for number, station in enumerate(["TEST_ONLY_A", "TEST_ONLY_B"]):
        records = []
        for i, time in enumerate(pd.date_range("2015-02-27", periods=120, freq="h")):
            row = dict.fromkeys(RAW_COLUMNS, 1.)
            row.update(No=i+1, year=time.year, month=time.month, day=time.day, hour=time.hour,
                       station=station, wd="N", TEMP=10., DEWP=5., PRES=1010.)
            row["PM2.5"] = None if i in (27, 50) else 10.+i+100*number
            records.append(row)
        path = root / "data/raw" / f"PRSA_Data_{station}_20130301-20170228.csv"
        pd.DataFrame(records, columns=RAW_COLUMNS).to_csv(path, index=False, na_rep="NA")
        paths.append(path)
    merged = load_station_data(paths)
    raw_path, quality_path = root / "reports/data_manifest.json", root / "reports/quality_full/summary.json"
    raw_path.write_text(json.dumps({"files": [{"path": p.relative_to(root).as_posix(), "sha256": sha256(p)} for p in paths]}), encoding="utf-8")
    quality = {**merged.summary, "status": "passed", "merged_sha256": "TEST_ONLY_NO_MERGED_READ"}
    quality_path.write_text(json.dumps(quality), encoding="utf-8")
    merged.stations.to_csv(root / "reports/quality_full/stations.csv", index=False)
    samples = temporal_split(build_samples(merged.data).samples, validation_start="2015-03-01", test_start="2016-03-01")
    files, membership = {}, {}
    for split in ("train", "validation"):
        subset = samples.loc[samples.split.eq(split)]
        for kind, frame in (("samples", subset), ("ids", subset[ID_COLUMNS])):
            path = root / "data/processed/samples_full" / ("sample_ids" if kind == "ids" else "") / f"{split}.csv"
            frame.to_csv(path, index=False, na_rep="NA")
            files[f"{split}_{kind}"] = {"path": path.relative_to(root).as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size}
        membership[split] = {}
        for name, group in (("operational", subset), ("primary", subset.loc[subset.is_primary])):
            membership[split][name] = {"samples": len(group), "ordered_sample_ids_sha256": ids_digest(group.sample_id)}
    files["test_samples"] = {"path": "TEST_ONLY_DO_NOT_OPEN/test.csv"}
    files["test_ids"] = {"path": "TEST_ONLY_DO_NOT_OPEN/test_ids.csv"}
    manifest = {"task_id": "T05", "mode": "full", "status": "complete", "snapshot_id": "TEST_ONLY",
                "t04_summary": "reports/quality_full/summary.json", "raw_manifest": "reports/data_manifest.json",
                "files": files, "membership": membership,
                "signature": {"split": read_json(root / "configs/default.json")["split"],
                              "merged_sha256": quality["merged_sha256"], "quality_summary_sha256": sha256(quality_path),
                              "raw_manifest_sha256": sha256(raw_path)}}
    (root / "reports/splits_full/split_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def runner():
    spec = importlib.util.spec_from_file_location("TEST_ONLY_baseline_runner", ROOT / "scripts/run_baseline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validation_anchor_only_reads_train_and_validation_never_test(project, monkeypatch):
    opened, original = [], Path.open
    def spy(path, *args, **kwargs):
        opened.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", spy)
    _, validation, provenance = load_train_validation(project)
    path, anchor = freeze_validation_ids(project, validation, provenance)
    before = path.read_bytes()
    freeze_validation_ids(project, validation, provenance)
    assert path.read_bytes() == before and anchor["test_locked"]
    assert not any("DO_NOT_OPEN" in p for p in opened)
    with pytest.raises(ValueError): freeze_validation_ids(project, validation.iloc[:-1], provenance)


def test_real_logger_fixture_smoke_full_budget_predictions_and_metric_recompute(project):
    execute = runner().execute_run
    smoke_id = execute(project, mode="smoke", is_test=True)
    full_id = execute(project, mode="full", reference_run_id=smoke_id, is_test=True)
    directory = project / "artifacts/experiments" / full_id
    config, metadata, stored = (read_json(directory / f"{name}.json") for name in ("config", "metadata", "metrics"))
    assert config["is_test"] is True and config["task_id"] == "TEST_ONLY_T09" and metadata["status"] == "completed"
    assert stored["official_full_result"] is False
    assert config["seed"] is None and config["reference_run_id"] == smoke_id
    predictions = pd.read_csv(directory / "artifacts/predictions/validation.csv")
    actual = evaluate_predictions(predictions, predictions.sample_id)
    assert stored["validation_primary"] == actual["primary"]
    assert stored["validation_operational"] == actual["operational"]
    assert predictions.run_id.eq(full_id).all() and predictions.fallback.sum() > 0
    for info in metadata["artifacts"]:
        path = project / "experiments" / info["path"]
        assert sha256(path) == info["sha256"] and path.stat().st_size == info["size_bytes"]
    index = pd.read_csv(project / "experiments/experiment_log.csv")
    assert len(index) == 2 and index.run_id.is_unique
    verifier_spec = importlib.util.spec_from_file_location("TEST_ONLY_baseline_verifier", ROOT / "scripts/verify_baseline.py")
    verifier = importlib.util.module_from_spec(verifier_spec)
    verifier_spec.loader.exec_module(verifier)
    verifier.verify_run(project, full_id)
    bundle = verifier.package_ledger(project, project / "reports/TEST_ONLY_runs.zip")
    assert set(bundle["run_ids"]) == {smoke_id, full_id} and bundle["bytes"] > 0
    with pytest.raises(ValueError, match="budget"):
        execute(project, mode="full", reference_run_id=smoke_id, is_test=True)


def test_failure_in_experiment_keeps_error_and_source_artifacts(project, monkeypatch):
    module = runner()
    def fail(*args): raise RuntimeError("TEST_ONLY expected scoring failure")
    monkeypatch.setattr(module, "evaluate_predictions", fail)
    with pytest.raises(RuntimeError, match="expected scoring failure"):
        module.execute_run(project, mode="smoke", is_test=True)
    path = next((project / "artifacts/experiments").glob("*/metadata.json"))
    metadata = read_json(path)
    assert metadata["status"] == "failed" and metadata["error"]["type"] == "RuntimeError"
    assert metadata["artifacts"] and metadata["ended_at"] is not None
