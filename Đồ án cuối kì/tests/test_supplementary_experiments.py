"""Fixture-only tests for T17b; no project dataset or saved run is opened."""

import numpy as np
import pandas as pd
import pytest

from beijing_air.supplementary_experiments import (
    _run_stack_validation,
    _rolling_mean_predictions,
    _yesterday_predictions,
    _require_restored_run_bundles,
    choose_by_cv,
    expand_candidates,
    fit_stack_predictions,
    ids_digest,
    pooled_fold_metrics,
)


def test_predeclared_candidate_budget_and_unique_ids():
    design = {
        "random_forest": [{"candidate_id": "rf", "parameters": {}, "feature_set": "A"}],
        "hist_gradient_boosting": [{"candidate_id": "hgb", "parameters": {}, "feature_set": "B"}],
        "linear": [{"candidate_id": "linear", "model": "lasso", "parameters": {}, "feature_set": "B"}],
        "decision_tree": [{"candidate_id": "tree", "parameters": {}, "feature_set": "B"}],
        "baselines": [{"candidate_id": "baseline", "model": "rolling_mean_3h", "feature_set": "B"}],
    }

    candidates = expand_candidates(design)

    assert [item["candidate_id"] for item in candidates] == ["rf", "hgb", "linear", "tree", "baseline"]
    assert candidates[-1]["parameters"] == {}
    with pytest.raises(ValueError, match="unique"):
        expand_candidates({**design, "baselines": [{"candidate_id": "rf", "model": "x"}]})


def test_pooled_metrics_weight_samples_not_folds():
    fold_one = pd.DataFrame({
        "sample_id": ["a", "b"], "y_true": [0.0, 0.0], "y_pred": [2.0, 2.0],
    })
    fold_two = pd.DataFrame({
        "sample_id": ["c", "d", "e"], "y_true": [0.0, 0.0, 0.0],
        "y_pred": [0.0, 0.0, 0.0],
    })

    result = pooled_fold_metrics([fold_one, fold_two, fold_two.assign(
        sample_id=["f", "g", "h"]
    )])

    assert result["pooled"]["MAE"] == pytest.approx(4 / 8)
    assert result["pooled"]["RMSE"] == pytest.approx(np.sqrt(8 / 8))
    assert result["fold_mean"]["MAE"] == pytest.approx(2 / 3)
    assert result["std_ddof"] == 0


def test_choose_by_cv_ignores_validation_metrics_and_uses_stable_tie_order():
    candidates = [
        {"candidate_id": "first", "status": "completed",
         "cv": {"pooled": {"MAE": 2.0}}, "validation_mae": 100.0},
        {"candidate_id": "second", "status": "completed",
         "cv": {"pooled": {"MAE": 2.0}}, "validation_mae": 0.0},
        {"candidate_id": "failed", "status": "failed",
         "cv": {"pooled": {"MAE": 0.0}}},
    ]

    assert choose_by_cv(candidates)["candidate_id"] == "first"


def test_three_hour_baseline_uses_causal_rolling_value_and_falls_back_to_current():
    samples = pd.DataFrame({"sample_id": ["a", "b"], "PM2.5": [10.0, 20.0]})
    features = pd.DataFrame({"pm25_roll_mean_3h": [7.0, np.nan]}, index=["a", "b"])

    assert _rolling_mean_predictions(samples, features).tolist() == [7.0, 20.0]


def test_yesterday_baseline_uses_target_hour_previous_day_or_current_fallback():
    samples = pd.DataFrame({
        "station": ["s", "s"],
        "input_timestamp": pd.to_datetime(["2015-03-02 10:00", "2015-03-02 11:00"]),
        "target_timestamp": pd.to_datetime(["2015-03-02 11:00", "2015-03-02 12:00"]),
        "PM2.5": [12.0, 14.0],
    })
    lookup = {
        ("s", pd.Timestamp("2015-03-01 11:00")): 8.0,
    }

    assert _yesterday_predictions(samples, lookup).tolist() == [8.0, 14.0]


def test_stack_fits_on_oof_labels_and_never_uses_validation_labels():
    oof_one = pd.DataFrame({
        "sample_id": ["a", "b", "c"], "y_true": [2.0, 4.0, 6.0],
        "y_pred": [1.0, 2.0, 3.0],
    })
    oof_two = oof_one.assign(y_pred=[2.0, 4.0, 6.0])
    validation_one = pd.DataFrame({
        "sample_id": ["v1", "v2"], "y_true": [100.0, 100.0],
        "y_pred": [5.0, 7.0],
    })
    validation_two = validation_one.assign(y_pred=[6.0, 8.0])

    reference, prediction, params = fit_stack_predictions(
        [oof_one, oof_two], [validation_one, validation_two], alpha=1.0
    )

    changed_validation_labels = [
        validation_one.assign(y_true=[-999.0, 999.0]),
        validation_two.assign(y_true=[-999.0, 999.0]),
    ]
    _, same_prediction, _ = fit_stack_predictions(
        [oof_one, oof_two], changed_validation_labels, alpha=1.0
    )
    assert reference.sample_id.tolist() == ["v1", "v2"]
    assert np.array_equal(prediction, same_prediction)
    assert params["alpha"] == 1.0


def test_stack_rejects_misaligned_base_ids():
    base = pd.DataFrame({"sample_id": ["a", "b"], "y_true": [1.0, 2.0], "y_pred": [1.0, 2.0]})
    other = base.assign(sample_id=["a", "c"])
    with pytest.raises(ValueError, match="IDs/targets differ"):
        fit_stack_predictions([base, other], [base, base], alpha=1.0)


def test_stack_validation_logs_oof_fit_ids_and_validation_counts(tmp_path):
    class Run:
        run_id = "stack-run"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def log_metrics(self, metrics, split=None):
            pass

        def log_artifact(self, path, name):
            assert path.is_file()

        def finish_run(self, **kwargs):
            pass

    class Logger:
        def start_run(self, **kwargs):
            self.arguments = kwargs
            return Run()

    oof = pd.DataFrame({
        "sample_id": ["a", "b", "c"], "y_true": [2.0, 4.0, 6.0],
        "y_pred": [1.0, 2.0, 3.0],
    })
    validation = pd.DataFrame({
        "sample_id": ["v1", "v2"], "y_true": [5.0, 7.0], "y_pred": [4.0, 6.0],
    })
    selected = [
        {"candidate_run_id": "base-one", "oof": oof, "validation": validation},
        {"candidate_run_id": "base-two", "oof": oof.assign(y_pred=[2.0, 4.0, 6.0]),
         "validation": validation.assign(y_pred=[6.0, 8.0])},
    ]
    logger = Logger()

    result = _run_stack_validation(
        logger, type("Parent", (), {"run_id": "parent-run"})(), selected, None,
        {"ensemble": {"stack_alpha": 1.0}, "seed": 42, "budget": {}}, tmp_path,
    )

    assert logger.arguments["split"]["stack_fit_sample_ids_sha256"] == ids_digest(["a", "b", "c"])
    assert logger.arguments["sample_counts"] == {"oof_fit": 3, "validation": 2}
    assert result["run_id"] == "stack-run"


def test_missing_indexed_run_bundle_is_reported_before_logging(tmp_path):
    ledger_dir = tmp_path / "experiments"
    ledger_dir.mkdir()
    (ledger_dir / "experiment_log.csv").write_text(
        "run_id,task_id\nmissing-run,T09\n", encoding="utf-8"
    )
    run_dir = tmp_path / "artifacts" / "experiments" / "missing-run"
    run_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="missing-run.*T09"):
        _require_restored_run_bundles(tmp_path)
