"""TEST_ONLY T10 fixtures: no real data, model runs, holdouts or tuning."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from beijing_air.eda import read_json, ids_digest
from beijing_air.features import build_features
from beijing_air.initial_models import current_A, load_initial_data, fitted_summary, validate_design
from beijing_air.metrics import regression_metrics
from beijing_air.samples import build_samples, temporal_split
from test_baseline import project as baseline_project, runner as baseline_runner
from test_features import observations


ROOT = Path(__file__).resolve().parents[1]


def runner():
    spec = importlib.util.spec_from_file_location("TEST_ONLY_initial_runner", ROOT / "scripts/run_initial_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(baseline_project):
    root = baseline_project
    baseline = baseline_runner()
    smoke = baseline.execute_run(root, mode="smoke", is_test=True)
    full = baseline.execute_run(root, mode="full", reference_run_id=smoke, is_test=True)
    design = read_json(ROOT / "configs/initial_models.json")
    design["baseline_reference_run_id"] = full
    design["models"]["random_forest"].update(n_estimators=3, max_depth=3)
    design["smoke"].update(train_rows_per_station=10, validation_rows_per_station=10)
    (root / "configs/initial_models.json").write_text(json.dumps(design), encoding="utf-8")
    return root


def test_A_from_current_origins_matches_T07_full_history_despite_gaps():
    config = read_json(ROOT / "configs/default.json")
    history = observations()
    history = history.loc[history.timestamp.ne(pd.Timestamp("2014-01-01 07:00"))]
    samples = temporal_split(build_samples(history).samples, validation_start="2015-03-01", test_start="2016-03-01")
    samples = samples.loc[samples.is_primary]
    expected = build_features(history, samples, config=config).select("A")
    actual = current_A(samples, config)
    assert_frame_equal(actual, expected)
    assert actual.shape[1] == 20
    assert not any(name.startswith("pm25_lag_") or name.startswith("pm25_roll_") for name in actual)
    changed_labels = samples.copy()
    changed_labels["target_pm25"] = 999999.
    assert_frame_equal(actual, current_A(changed_labels, config))


def test_full_and_smoke_membership_no_subsampling_full_and_no_test_reads(project, monkeypatch):
    opened, original = [], Path.open
    def spy(path, *args, **kwargs):
        opened.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", spy)
    design = read_json(project / "configs/initial_models.json")
    full, full_x, _, anchor, _ = load_initial_data(project, mode="full", design=design)
    smoke, smoke_x, _, _, _ = load_initial_data(project, mode="smoke", design=design)
    manifest = read_json(project / "reports/splits_full/split_manifest.json")
    for split in ("train", "validation"):
        assert len(full[split]) == manifest["membership"][split]["primary"]["samples"]
        assert ids_digest(full[split].sample_id) == manifest["membership"][split]["primary"]["ordered_sample_ids_sha256"]
        assert len(smoke[split]) == 20 and smoke_x[split].index.tolist() == smoke[split].sample_id.tolist()
        assert full_x[split].columns.tolist() == smoke_x[split].columns.tolist()
    assert ids_digest(full["validation"].sample_id) == anchor["cohorts"]["primary"]["ordered_sample_ids_sha256"]
    assert not any("DO_NOT_OPEN" in path for path in opened)


@pytest.mark.parametrize("model", ["ridge", "random_forest"])
def test_smoke_full_real_logger_pipeline_state_metrics_and_reuse(project, model):
    module = runner()
    smoke = module.execute_model(project, model_name=model, mode="smoke", is_test=True)
    full = module.execute_model(project, model_name=model, mode="full", is_test=True)
    directory = project / "artifacts/experiments" / full
    config, record, scores = (read_json(directory / f"{name}.json") for name in ("config", "metadata", "metrics"))
    assert config["task_id"] == "TEST_ONLY_T10" and config["is_test"] is True
    assert config["parameters"]["smoke_reference_run_id"] == smoke and record["status"] == "completed"
    assert scores["official_full_result"] is False and scores["test_csv_accessed"] is False
    for split in ("train", "validation"):
        pred = pd.read_csv(directory / f"artifacts/predictions/{split}.csv.gz")
        actual = regression_metrics(pred.y_true, pred.y_pred)
        for key in ("MAE", "RMSE", "R2"):
            assert actual[key] == pytest.approx(scores[f"{split}_primary"][key])
        assert pred.sample_id.is_unique and pred.is_primary.all() and pred.run_id.eq(full).all()
    state = read_json(directory / "artifacts/model/fitted_pipeline_state.json")
    assert len(state["input_feature_names"]) == 20
    assert state["model_n_features_in"] == len(state["output_feature_names"])
    assert state["weights_saved"] is False
    if model == "random_forest":
        assert state["n_estimators_fitted"] == 3 and state["maximum_tree_depth"] <= 3
    else:
        assert len(state["coef"]) == state["model_n_features_in"]
    spec = importlib.util.spec_from_file_location("TEST_ONLY_initial_report", ROOT / "scripts/report_initial_models.py")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    verified_config, _, _ = report.verify_run(project, full)
    assert verified_config["is_test"] is True
    before = (project / "experiments/experiment_log.csv").read_bytes()
    assert module.execute_model(project, model_name=model, mode="full", is_test=True) == full
    assert (project / "experiments/experiment_log.csv").read_bytes() == before
    design = read_json(project / "configs/initial_models.json")
    design["models"][model]["alpha" if model == "ridge" else "min_samples_leaf"] = 4
    (project / "configs/initial_models.json").write_text(json.dumps(design), encoding="utf-8")
    with pytest.raises(ValueError, match="budget"):
        module.execute_model(project, model_name=model, mode="full", is_test=True)
    design["models"][model]["alpha" if model == "ridge" else "min_samples_leaf"] = 1.0 if model == "ridge" else 2
    (project / "configs/initial_models.json").write_text(json.dumps(design), encoding="utf-8")
    with (directory / "artifacts/predictions/validation.csv.gz").open("ab") as stream:
        stream.write(b"TEST_ONLY_changed")
    with pytest.raises(ValueError, match="artifact is missing/changed"):
        module.execute_model(project, model_name=model, mode="full", is_test=True)


def test_full_requires_matching_smoke_before_new_experiment(project):
    before = (project / "experiments/experiment_log.csv").read_bytes()
    with pytest.raises(ValueError, match="completed matching smoke"):
        runner().execute_model(project, model_name="ridge", mode="full", is_test=True)
    assert (project / "experiments/experiment_log.csv").read_bytes() == before


def test_fit_failure_is_logged_and_old_baseline_history_survives(project, monkeypatch):
    module = runner()
    def fail(*args): raise RuntimeError("TEST_ONLY fit failure")
    monkeypatch.setattr(module, "fitted_summary", fail)
    with pytest.raises(RuntimeError, match="fit failure"):
        module.execute_model(project, model_name="ridge", mode="smoke", is_test=True)
    rows = pd.read_csv(project / "experiments/experiment_log.csv")
    assert len(rows) == 3 and rows.loc[rows.task_id.eq("TEST_ONLY_T09"), "status"].eq("completed").all()
    failed = rows.loc[rows.task_id.eq("TEST_ONLY_T10")].iloc[0]
    assert failed.status == "failed"
    assert "TEST_ONLY fit failure" in read_json(project / "experiments" / failed.metadata_path)["error"]["message"]


@pytest.mark.parametrize("kind", ["feature_B", "too_many_trees", "unbounded_depth", "parallel", "tuning", "clipping", "weights"])
def test_design_rejects_scope_or_resource_drift(kind):
    design = read_json(ROOT / "configs/initial_models.json")
    prep = read_json(ROOT / "configs/preprocessing.json")
    if kind == "feature_B": design["feature_set"] = "B"
    elif kind == "too_many_trees": design["models"]["random_forest"]["n_estimators"] = 300
    elif kind == "unbounded_depth": design["models"]["random_forest"]["max_depth"] = None
    elif kind == "parallel": design["models"]["random_forest"]["n_jobs"] = -1
    elif kind == "tuning": design["budget"]["tuning"] = True
    elif kind == "clipping": prep["prediction_postprocessing"]["negative_predictions"] = "clip"
    else: design["save_model_weights"] = True
    with pytest.raises(ValueError): validate_design(design, prep)
