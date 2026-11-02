"""TEST_ONLY grouped selection/ablation fixtures, no project holdout I/O."""

from copy import deepcopy
import csv
import importlib.util
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from sklearn.base import clone
from sklearn.exceptions import NotFittedError

from beijing_air import features as feature_module
from beijing_air.ablation import B_from_pm_history, load_train_B, choose_k, choose_deployment, validate_ablation
from beijing_air.data import load_station_data, sha256
from beijing_air.eda import read_json, load_training_data
from beijing_air.evaluation import load_train_validation
from beijing_air.experiment_logging import ExperimentLogger
from beijing_air.feature_selection import make_ablation_pipeline, selection_state, encoded_groups
from beijing_air.features import build_features
from beijing_air.initial_models import prediction_frame
from beijing_air.samples import build_samples, temporal_split
from test_features import observations
from test_initial_models import project as initial_project, baseline_project, runner as initial_runner
from test_tuning import small_cv

ROOT = Path(__file__).resolve().parents[1]


def module(name="run_ablation"):
    spec = importlib.util.spec_from_file_location("TEST_ONLY_"+name, ROOT / "scripts" / (name+".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def example():
    cfg = read_json(ROOT / "configs/default.json")
    obs = observations(periods=70)
    obs.loc[obs.station.eq("TEST_ONLY_A") & obs.timestamp.eq("2014-01-02"), "PM2.5"] = np.nan
    obs = obs.loc[obs.timestamp.ne(pd.Timestamp("2014-01-01 10:00"))]
    data = temporal_split(build_samples(obs).samples, validation_start="2015-03-01", test_start="2016-03-01")
    data = data.loc[data.is_primary].reset_index(drop=True)
    return obs, data, build_features(obs, data, config=cfg).select("B"), cfg


def test_pm_history_with_current_measurements_matches_full_T07_and_future_mutation_is_causal():
    obs, data, expected, cfg = example()
    actual = B_from_pm_history(obs[["station", "timestamp", "PM2.5"]], data, cfg)
    assert_frame_equal(actual, expected)
    cutoff = pd.Timestamp("2014-01-02")
    changed = obs.copy()
    changed.loc[changed.timestamp.gt(cutoff), "PM2.5"] = 999999.
    earlier = data.loc[data.input_timestamp.le(cutoff)]
    assert_frame_equal(B_from_pm_history(changed, earlier, cfg), expected.loc[earlier.sample_id])
    assert actual.isna().any().any() and len(actual) == len(data)


def test_group_selector_train_only_whole_one_hot_indicator_groups_and_serialization(tmp_path):
    _, data, x, cfg = example()
    prep = read_json(ROOT / "configs/preprocessing.json")
    fit = np.flatnonzero(data.input_timestamp.lt("2014-01-02 12:00"))
    ev = np.flatnonzero(data.input_timestamp.ge("2014-01-02 12:00"))
    pipe = make_ablation_pipeline("C", cfg, prep, k_groups=12)
    y = data.set_index("sample_id").target_pm25
    pipe.fit(x.iloc[fit], y.iloc[fit])
    before = selection_state(pipe)
    changed = x.iloc[ev].copy()
    changed["wd"], changed["TEMP"] = "TEST_ONLY_NEW", 999999.
    changed["pm25_lag_24h"] = np.nan
    pipe.predict(changed)
    assert selection_state(pipe) == before
    twin = clone(pipe).fit(x.iloc[fit], y.iloc[fit])
    assert selection_state(twin) == before
    selector = pipe.named_steps["select"]
    assert len(selector.selected_groups_) == 12 and len(selector.dropped_groups_) == 21
    groups = encoded_groups(selector.feature_names_in_, selector.raw_features)
    for group in selector.raw_features:
        selected = selector.support_[groups == group]
        assert selected.all() or not selected.any()
    fresh = clone(pipe)
    with pytest.raises(NotFittedError): fresh.predict(changed)
    file = tmp_path / "TEST_ONLY_grouped.joblib"
    joblib.dump(pipe, file)
    loaded = joblib.load(file)
    np.testing.assert_allclose(loaded.predict(changed), pipe.predict(changed))
    assert loaded[:-1].get_feature_names_out().tolist() == before["model_feature_names"]
    assert before["model_dimensions"] == len(before["coef"]) == len(before["model_feature_names"])


def test_ranking_ties_and_deployment_pool_are_explicit():
    records = [{"status": "completed", "fold_run_ids": ["TEST_ONLY"]*3, "k_groups": k, "summary": {"pooled": {"MAE": 1.}}} for k in (12, 20)]
    assert choose_k(records)["k_groups"] == 12
    records[0]["status"] = "failed"
    assert choose_k(records)["k_groups"] == 20
    with pytest.raises(ValueError): choose_k([])
    d = read_json(ROOT / "configs/ablation.json")
    candidates = [{"variant": name, "MAE": 1.} for name in d["selection"]["deployment_pool"]]
    assert choose_deployment(candidates, d)["variant"] == "A"
    with pytest.raises(ValueError): choose_deployment(candidates[:-1], d)


@pytest.fixture
def project(initial_project):
    root = initial_project
    cfg = small_cv(read_json(root / "configs/default.json"), first="2015-02-27 12:00", hours=12)
    (root / "configs/default.json").write_text(json.dumps(cfg), encoding="utf-8")
    initial = initial_runner()
    initial.execute_model(root, model_name="random_forest", mode="smoke", is_test=True)
    rf = initial.execute_model(root, model_name="random_forest", mode="full", is_test=True)
    runner = module()
    train, validation, provenance = load_train_validation(root)
    # Genuine TEST_ONLY Ridge alpha0.1 reference fit; no invented official run.
    raw_train, train_prov = load_training_data(root)
    raw_validation = pd.read_csv(root / "data/processed/samples_full/validation.csv", parse_dates=["input_timestamp", "target_timestamp"])
    history = load_station_data(sorted((root / "data/raw").glob("*.csv"))).data
    all_train_b = build_features(history, raw_train, config=cfg).select("B")
    dataset = root / "data/processed/features_full"
    report = root / "reports/features_full"
    dataset.mkdir(); report.mkdir()
    file = dataset / "train_B.csv"
    all_train_b.to_csv(file)
    manifest = {"task_id": "T07", "mode": "full", "status": "complete", "fit_performed": False, "snapshot_id": "TEST_ONLY_T07",
                "signature": {"train_provenance": train_prov, "features": cfg["features"], "module_sha256": sha256(Path(feature_module.__file__))},
                "files": {"train_B": {"path": file.relative_to(root).as_posix(), "sha256": sha256(file), "bytes": file.stat().st_size}}}
    (report / "feature_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    tp = raw_train.loc[raw_train.is_primary].reset_index(drop=True)
    vp = raw_validation.loc[raw_validation.is_primary].reset_index(drop=True)
    xa = build_features(history, tp, config=cfg).select("A")
    va = build_features(history, vp, config=cfg).select("A")
    pipe = make_ablation_pipeline("A", cfg, read_json(root / "configs/preprocessing.json"))
    with ExperimentLogger(project_root=root).start_run(task_id="TEST_ONLY_T11", mode="full", model="ridge", feature_set="A", kind="train", is_test=True,
        parameters={"alpha": 0.1, "actual_model_parameters": pipe.named_steps["model"].get_params()}, data={"provenance": provenance},
        preprocessing=read_json(root / "configs/preprocessing.json"), seed=None, source="TEST_ONLY_actual_reference_fit") as run:
        pipe.fit(xa, tp.set_index("sample_id").target_pm25)
        pred = prediction_frame(vp, pipe.predict(va), run.run_id, "ridge")
        work = root / "artifacts/TEST_ONLY_reference"; work.mkdir()
        runner.save_predictions(run, work, pred, "validation")
        reference = run.run_id
        run.finish_run(notes="TEST_ONLY genuine reference model fit on fixture train; no project model history.")
    d = read_json(ROOT / "configs/ablation.json")
    d.update(reference_A_run_id=reference, t11_search_run_id="TEST_ONLY_UNUSED")
    d["historical_comparators"] = {"random_forest_A": rf, "persistence": read_json(root / "configs/initial_models.json")["baseline_reference_run_id"]}
    d["selector"]["k_groups"] = [12, 20]
    d["budget"].update(selector_candidates=2, cv_pipeline_fits=6, cv_pilot_estimator_fits=6, total_estimator_fits=15)
    d["smoke"].update(train_rows_per_station=5, evaluation_rows_per_station=3)
    (root / "configs/ablation.json").write_text(json.dumps(d), encoding="utf-8")
    return root


def test_smoke_full_common_ids_selection_before_validation_and_frozen_config(project, monkeypatch):
    runner = module()
    smoke = runner.execute_ablation(project, mode="smoke", is_test=True)
    original, opened = Path.open, []
    def spy(path, *args, **kwargs):
        opened.append(str(path))
        if path == project / "data/processed/samples_full/validation.csv":
            with original(project / "experiments/experiment_log.csv", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            folds = [r for r in rows if r["task_id"] == "TEST_ONLY_T12" and r["mode"] == "full" and json.loads(r["parameters"])["stage"] == "fold"]
            assert len(folds) == 6 and all(r["status"] == "completed" for r in folds)
            search = next(r for r in rows if r["task_id"] == "TEST_ONLY_T12" and r["mode"] == "full" and json.loads(r["parameters"])["stage"] == "search")
            locked = read_json(project / "artifacts/experiments" / search["run_id"] / "artifacts/search/selection.json")
            assert locked["selection"]["before_validation"] and len(locked["candidates"]) == 2
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", spy)
    full = runner.execute_ablation(project, mode="full", is_test=True)
    result = read_json(project / "artifacts/experiments" / full / "artifacts/search/results.json")
    assert len(result["final_run_ids"]) == 2 and len(result["comparison"]) == 5
    assert not any("DO_NOT_OPEN" in p for p in opened)
    frozen = read_json(project / "reports/ablation/frozen_model.json")
    assert frozen["test_evaluated"] is False and frozen["deployment_ready_weights"] is False
    assert frozen["selected_variant"] == choose_deployment(result["comparison"], read_json(project / "configs/ablation.json"))["variant"]
    verifier = module("report_ablation")
    verifier.verify(project, smoke)
    checked, folds, groups = verifier.verify(project, full)
    assert checked["parent_run_id"] == full and len(folds) == 6 and len(groups) > 0
    before = (project / "experiments/experiment_log.csv").read_bytes()
    assert runner.execute_ablation(project, mode="full", is_test=True) == full
    assert (project / "experiments/experiment_log.csv").read_bytes() == before
    d = read_json(project / "configs/ablation.json"); d["selector"]["k_groups"] = [12, 21]
    d["smoke"]["k_groups"] = [21]
    (project / "configs/ablation.json").write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="budget"): runner.execute_ablation(project, mode="full", is_test=True)


def test_failed_candidate_is_logged_excluded_and_no_full_without_matching_smoke(project, monkeypatch):
    runner = module()
    with pytest.raises(ValueError, match="matching.*smoke"): runner.execute_ablation(project, mode="full", is_test=True)
    runner.execute_ablation(project, mode="smoke", is_test=True)
    original = runner.fit_predict
    def fail(pipe, *args):
        if "select" in pipe.named_steps and pipe.named_steps["select"].k_groups == 20:
            raise RuntimeError("TEST_ONLY selector candidate failure")
        return original(pipe, *args)
    monkeypatch.setattr(runner, "fit_predict", fail)
    full = runner.execute_ablation(project, mode="full", is_test=True)
    result = read_json(project / "artifacts/experiments" / full / "artifacts/search/results.json")
    failed = next(r for r in result["candidates"] if r["status"] == "failed")
    assert result["selection"]["k_groups"] == 12 and len(failed["failed_fold_run_ids"]) == 3
    for rid in [failed["run_id"], *failed["failed_fold_run_ids"]]:
        record = read_json(project / "artifacts/experiments" / rid / "metadata.json")
        assert record["status"] == "failed" and record["error"]
    module("report_ablation").verify(project, full)


def test_all_failed_smoke_keeps_errors_and_does_not_load_validation(project, monkeypatch):
    runner = module()
    def fail(*args): raise RuntimeError("TEST_ONLY all selectors failed")
    monkeypatch.setattr(runner, "fit_predict", fail)
    monkeypatch.setattr(runner, "load_validation_B", lambda *args: pytest.fail("Validation must stay closed"))
    with pytest.raises(ValueError, match="No complete"):
        runner.execute_ablation(project, mode="smoke", is_test=True)
    rows = pd.read_csv(project / "experiments/experiment_log.csv")
    actual = rows.loc[rows.task_id.eq("TEST_ONLY_T12")]
    assert len(actual) == 5 and actual.status.eq("failed").all()


@pytest.mark.parametrize("bad", ["budget", "more_candidates", "RF", "alpha", "clipping", "bad_k"])
def test_design_rejects_scope_drift(bad):
    d, prep = read_json(ROOT / "configs/ablation.json"), read_json(ROOT / "configs/preprocessing.json")
    if bad == "budget": d["budget"]["total_estimator_fits"] = 999
    elif bad == "more_candidates": d["selector"]["k_groups"] = [1, 2, 3, 4]
    elif bad == "RF": d["model"] = "random_forest"
    elif bad == "alpha": d["alpha"] = 1
    elif bad == "clipping": prep["prediction_postprocessing"]["negative_predictions"] = "clip"
    else: d["selector"]["k_groups"] = [0, 20]
    with pytest.raises(ValueError): validate_ablation(d, prep)
