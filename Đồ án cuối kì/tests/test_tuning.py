"""TEST_ONLY temporal search fixtures, never real data or official experiments."""

from copy import deepcopy
import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from beijing_air.eda import read_json
from beijing_air.initial_models import current_A
from beijing_air.samples import build_samples, temporal_split
from beijing_air.temporal_cv import expanding_folds
from beijing_air.tuning import aggregate_folds, choose_candidate, validate_search, ridge_pipeline
from test_features import observations
from test_initial_models import project as initial_project, baseline_project, runner as initial_runner

ROOT = Path(__file__).resolve().parents[1]


def module(name="run_tuning"):
    spec = importlib.util.spec_from_file_location(f"TEST_ONLY_{name}", ROOT / "scripts" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def small_cv(config, first="2014-01-01 12:00", hours=8):
    cfg = deepcopy(config)
    start = pd.Timestamp(first)
    cfg["temporal_cv"]["folds"] = [
        {"fold_id": i+1, "evaluation_start": str(start+pd.Timedelta(hours=hours*i)),
         "evaluation_end": str(start+pd.Timedelta(hours=hours*(i+1)))} for i in range(3)]
    return cfg


def small_samples():
    history = observations(periods=40)
    history = history.loc[~((history.station == "TEST_ONLY_A") & (history.timestamp == pd.Timestamp("2014-01-01 10:00")))]
    return temporal_split(build_samples(history).samples, validation_start="2015-03-01", test_start="2016-03-01").reset_index(drop=True)


def test_splitter_uses_whole_timestamps_across_stations_and_purges_exact_boundary():
    data = small_samples()
    cfg = small_cv(read_json(ROOT / "configs/default.json"))
    folds = expanding_folds(data, cfg)
    seen = set()
    for fold in folds:
        fit, evaluation, purged = (data.iloc[p] for p in (fold.fit, fold.evaluation, fold.purged))
        assert fit.target_timestamp.max() < evaluation.input_timestamp.min()
        assert set(fit.station) == set(evaluation.station) == {"TEST_ONLY_A", "TEST_ONLY_B"}
        assert not set(evaluation.sample_id) & seen
        seen.update(evaluation.sample_id)
        assert purged.target_timestamp.eq(evaluation.input_timestamp.min()).all()
        for stamp in evaluation.target_timestamp.unique():
            assert set(data.loc[data.target_timestamp.eq(stamp), "sample_id"]) == set(evaluation.loc[evaluation.target_timestamp.eq(stamp), "sample_id"])
    shuffled = data.sample(frac=1, random_state=42).reset_index(drop=True)
    for a, b in zip(folds, expanding_folds(shuffled, cfg)):
        assert set(data.iloc[a.fit].sample_id) == set(shuffled.iloc[b.fit].sample_id)
        assert set(data.iloc[a.evaluation].sample_id) == set(shuffled.iloc[b.evaluation].sample_id)
    assert set(folds[0].fit) < set(folds[1].fit) < set(folds[2].fit)


@pytest.mark.parametrize("bad", ["duplicate", "holdout", "overlap", "empty", "not_hourly", "station_absent"])
def test_splitter_fails_instead_of_moving_windows_or_leaking(bad):
    data, cfg = small_samples(), small_cv(read_json(ROOT / "configs/default.json"))
    if bad == "duplicate": data = pd.concat([data, data.iloc[[0]]])
    elif bad == "holdout": data.loc[0, "split"] = "validation"
    elif bad == "overlap": cfg["temporal_cv"]["folds"][1]["evaluation_start"] = cfg["temporal_cv"]["folds"][0]["evaluation_start"]
    elif bad == "empty": cfg = small_cv(cfg, first="2014-05-01")
    elif bad == "not_hourly": data.loc[0, "input_timestamp"] -= pd.Timedelta(hours=1)
    else: data = data.loc[~(data.station.eq("TEST_ONLY_B") & data.target_timestamp.ge("2014-01-01 12:00"))]
    with pytest.raises(ValueError): expanding_folds(data, cfg)


def test_evaluation_mutation_cannot_change_fitted_pipeline():
    cfg, data = small_cv(read_json(ROOT / "configs/default.json")), small_samples()
    fold = expanding_folds(data, cfg)[0]
    x = current_A(data, cfg)
    prep = read_json(ROOT / "configs/preprocessing.json")
    runner = module()
    _, before, _ = runner.evaluate_fold(ridge_pipeline(1, cfg, prep), x, data, fold.fit, fold.evaluation)
    changed = x.copy()
    changed.loc[x.index[fold.evaluation], "TEMP"] = 999999.
    changed.loc[x.index[fold.evaluation], "wd"] = "TEST_ONLY_NEW"
    labels = data.copy()
    labels.loc[fold.evaluation, "target_pm25"] = 999999.
    _, after, _ = runner.evaluate_fold(ridge_pipeline(1, cfg, prep), changed, labels, fold.fit, fold.evaluation)
    assert before == after


def test_pooled_ranking_is_not_unweighted_fold_mean_and_ties_or_null_R2_are_explicit():
    predictions = [pd.DataFrame({"sample_id": [f"TEST_ONLY_{i}_{j}" for j in range(n)], "y_true": np.ones(n), "y_pred": np.ones(n)+error})
                   for i, (n, error) in enumerate(((2, 0), (3, 0), (5, 10)))]
    aggregate = aggregate_folds(predictions)
    assert aggregate["pooled"]["MAE"] == 5 and aggregate["fold_mean"]["MAE"] == pytest.approx(10/3)
    assert aggregate["fold_std"]["MAE"] == pytest.approx(np.std([0, 0, 10], ddof=0))
    assert aggregate["fold_mean"]["R2"] is None and aggregate["R2_defined_folds"] == 0
    candidates = [{"alpha": a, "status": "completed", "fold_run_ids": ["TEST_ONLY"]*3, "summary": aggregate} for a in (1., 10.)]
    assert choose_candidate(candidates)["alpha"] == 10
    candidates[1]["status"] = "failed"
    assert choose_candidate(candidates)["alpha"] == 1
    with pytest.raises(ValueError): choose_candidate([])
    with pytest.raises(ValueError): aggregate_folds(predictions[:2])


@pytest.fixture
def project(initial_project):
    root = initial_project
    cfg = small_cv(read_json(root / "configs/default.json"), first="2015-02-27 12:00", hours=12)
    (root / "configs/default.json").write_text(json.dumps(cfg), encoding="utf-8")
    runner = initial_runner()
    runner.execute_model(root, model_name="ridge", mode="smoke", is_test=True)
    reference = runner.execute_model(root, model_name="ridge", mode="full", is_test=True)
    design = read_json(ROOT / "configs/tuning.json")
    design.update(reference_run_id=reference, alphas=[1., 10.])
    design["budget"].update(candidates=2, cv_fits=6)
    design["smoke"].update(train_rows_per_station=5, evaluation_rows_per_station=3)
    (root / "configs/tuning.json").write_text(json.dumps(design), encoding="utf-8")
    return root


def test_search_logging_selection_before_validation_recompute_reuse_and_budget(project, monkeypatch):
    runner = module()
    smoke = runner.execute_search(project, mode="smoke", is_test=True)
    paths, original = [], Path.open
    def spy(path, *args, **kwargs):
        paths.append(str(path))
        if path == project / "data/processed/samples_full/validation.csv":
            locks = list((project / "artifacts/experiments").glob("*/artifacts/search/selection.json"))
            assert any(read_json(p)["selection"]["selection_locked_before_validation"] for p in locks)
            # Smoke lock alone is insufficient: all six FULL CV fits must already end.
            with original(project / "experiments/experiment_log.csv", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            cv_rows = [r for r in rows if r["task_id"] == "TEST_ONLY_T11" and r["mode"] == "full" and json.loads(r["parameters"])["stage"] == "fold"]
            assert len(cv_rows) == 6 and all(r["status"] == "completed" for r in cv_rows)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", spy)
    full = runner.execute_search(project, mode="full", is_test=True)
    assert not any("DO_NOT_OPEN" in path for path in paths)
    result = read_json(project / "artifacts/experiments" / full / "artifacts/search/results.json")
    assert len(result["candidates"]) == 2 and result["official_full_search"] is False
    selected = choose_candidate(result["candidates"])
    assert selected["run_id"] == result["selection"]["selected_candidate_run_id"]
    for candidate in result["candidates"]:
        pred = [pd.read_csv(project / "artifacts/experiments" / rid / "artifacts/predictions/evaluation.csv.gz") for rid in candidate["fold_run_ids"]]
        assert aggregate_folds(pred)["pooled"]["MAE"] == pytest.approx(candidate["summary"]["pooled"]["MAE"])
    cfg = read_json(project / "artifacts/experiments" / full / "config.json")
    assert cfg["parameters"]["smoke_reference_run_id"] == smoke
    verifier = module("report_tuning")
    verifier.verify_search(project, smoke)
    verified, folds = verifier.verify_search(project, full)
    assert verified["parent_run_id"] == full and len(folds) == 6
    before = (project / "experiments/experiment_log.csv").read_bytes()
    assert runner.execute_search(project, mode="full", is_test=True) == full
    assert (project / "experiments/experiment_log.csv").read_bytes() == before
    design = read_json(project / "configs/tuning.json")
    design["alphas"] = [1., 100.]
    (project / "configs/tuning.json").write_text(json.dumps(design), encoding="utf-8")
    with pytest.raises(ValueError, match="budget"): runner.execute_search(project, mode="full", is_test=True)


def test_failed_candidates_and_folds_remain_in_log_but_are_not_selected(project, monkeypatch):
    runner = module()
    runner.execute_search(project, mode="smoke", is_test=True)
    original = runner.evaluate_fold
    def fail(pipe, *args):
        if pipe.named_steps["model"].alpha == 10:
            raise RuntimeError("TEST_ONLY candidate failure")
        return original(pipe, *args)
    monkeypatch.setattr(runner, "evaluate_fold", fail)
    full = runner.execute_search(project, mode="full", is_test=True)
    result = read_json(project / "artifacts/experiments" / full / "artifacts/search/results.json")
    failed = next(c for c in result["candidates"] if c["status"] == "failed")
    assert result["selection"]["alpha"] == 1 and len(failed["failed_fold_run_ids"]) == 3
    for run_id in [failed["run_id"], *failed["failed_fold_run_ids"]]:
        record = read_json(project / "artifacts/experiments" / run_id / "metadata.json")
        assert record["status"] == "failed" and record["error"] is not None
    assert "TEST_ONLY candidate failure" in read_json(project / "artifacts/experiments" / failed["failed_fold_run_ids"][0] / "metadata.json")["error"]["message"]
    module("report_tuning").verify_search(project, full)


def test_all_failed_smoke_never_opens_validation_and_full_requires_successful_smoke(project, monkeypatch):
    runner = module()
    with pytest.raises(ValueError, match="matching smoke"):
        runner.execute_search(project, mode="full", is_test=True)
    def fail(*args): raise RuntimeError("TEST_ONLY all failed")
    monkeypatch.setattr(runner, "evaluate_fold", fail)
    monkeypatch.setattr(runner, "selected_refit", lambda *a: pytest.fail("Cannot open validation without a complete candidate"))
    with pytest.raises(ValueError, match="No complete candidate"):
        runner.execute_search(project, mode="smoke", is_test=True)
    rows = pd.read_csv(project / "experiments/experiment_log.csv")
    assert rows.loc[rows.task_id.eq("TEST_ONLY_T11") & rows.parameters.map(lambda v: json.loads(v).get("stage") == "search"), "status"].eq("failed").all()


@pytest.mark.parametrize("bad", ["over_budget", "RF", "feature_B", "clipping", "duplicate", "bad_alpha"])
def test_search_policy_rejects_unbounded_or_changed_design(bad):
    design, prep = read_json(ROOT / "configs/tuning.json"), read_json(ROOT / "configs/preprocessing.json")
    if bad == "over_budget": design["budget"]["cv_fits"] = 100
    elif bad == "RF": design["model"] = "random_forest"
    elif bad == "feature_B": design["feature_set"] = "B"
    elif bad == "clipping": prep["prediction_postprocessing"]["negative_predictions"] = "clip"
    elif bad == "duplicate": design["alphas"] = [1, 1]
    else: design["alphas"] = [1, -1]
    with pytest.raises(ValueError): validate_search(design, prep)
