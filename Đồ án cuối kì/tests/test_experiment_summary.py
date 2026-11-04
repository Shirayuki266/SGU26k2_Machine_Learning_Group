"""TEST_ONLY ledgers/predictions; no training, project data or model loading."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from beijing_air.experiment_summary import Reader, GROUPS, build_summary, export_summary, pooled_folds
from beijing_air.metrics import regression_metrics


def frame(error=1., n=4, prefix="TEST_ONLY_VAL"):
    return pd.DataFrame({"sample_id": [prefix+str(i) for i in range(n)],
                         "y_true": np.arange(n, dtype=float)+10,
                         "y_pred": np.arange(n, dtype=float)+10+error, "is_primary": True})


class TEST_ONLY_Log:
    def __init__(self, root):
        self.root, self.rows = root, []

    def add(self, rid, task="T10", model="ridge", fs="A", parameters=None, metrics=None,
            predictions=None, parent="", reference="", mode="full", status="completed", fold=""):
        folder = self.root/"artifacts/experiments"/rid
        folder.mkdir(parents=True, exist_ok=True)
        metric_file = folder/"metrics.json"
        metric_file.write_text(json.dumps(metrics or {}), encoding="utf-8")
        artifacts = []
        for part, data in (predictions or {}).items():
            path = folder/"artifacts/predictions"/(part+".csv")
            path.parent.mkdir(parents=True, exist_ok=True)
            data.to_csv(path, index=False)
            artifacts.append({"path": "../"+path.relative_to(self.root).as_posix(),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        self.rows.append({"run_id": rid, "task_id": task, "model": model, "feature_set": fs,
            "parameters": json.dumps(parameters or {}), "metrics": json.dumps(metrics or {}),
            "metrics_path": "../"+metric_file.relative_to(self.root).as_posix(),
            "artifacts": json.dumps(artifacts), "preprocessing": "{}", "mode": mode,
            "status": status, "is_test": "false", "fold_id": str(fold),
            "parent_run_id": parent, "reference_run_id": reference, "error": "TEST_ONLY failure" if status == "failed" else ""})

    def save(self):
        path = self.root/"experiments/experiment_log.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        keys = list(self.rows[0]) if self.rows else ["run_id"]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=keys)
            writer.writeheader(); writer.writerows(self.rows)
        return path


def validation_metrics(data):
    return {"validation_primary": regression_metrics(data.y_true, data.y_pred)}


@pytest.fixture
def log(tmp_path):
    log = TEST_ONLY_Log(tmp_path)
    baseline, ridge, forest = frame(2), frame(1), frame(.5)
    log.add("TEST_BASE", task="T09", model="persistence", metrics=validation_metrics(baseline), predictions={"validation": baseline})
    log.add("TEST_RIDGE", parameters={"actual_model_parameters": {"alpha": 1.}},
            metrics=validation_metrics(ridge), predictions={"validation": ridge})
    log.add("TEST_RF", model="random_forest", parameters={"actual_model_parameters": {"n_estimators": 80}},
            metrics=validation_metrics(forest), predictions={"validation": forest})
    log.add("TEST_T13_PARENT", task="T13", model="locked_final_comparison",
            parameters={"design": {"development_selected_run_id": "TEST_RF"}})
    test = frame(100, prefix="TEST_ONLY_TEST_ARTIFACT")
    log.add("TEST_T13_RF", task="T13", model="random_forest", reference="TEST_RF", parent="TEST_T13_PARENT",
            parameters={"stage": "final_refit_test", "locked_parameters": {"n_estimators": 80}},
            metrics={"test_primary": regression_metrics(test.y_true, test.y_pred)}, predictions={"test": test})
    return log


def build(log, **kwargs):
    log.save()
    reader = Reader(log.root)
    rows, evidence = build_summary(reader, **kwargs)
    return reader, rows, evidence


def test_group_order_and_best_use_validation_not_test_and_keep_lock(log):
    supplementary = frame(.1)
    log.add("TEST_NEW", task="T17b", model="hist_gradient_boosting", metrics=validation_metrics(supplementary),
            predictions={"validation": supplementary})
    reader, rows, evidence = build(log)
    actual = [GROUPS.index(r["group"]) for r in rows]
    assert actual == sorted(actual)
    assert [r["run_id"] for r in rows if r["best_validation"]] == ["TEST_NEW"]
    assert [r["run_id"] for r in rows if r["locked"]] == ["TEST_RF"]
    forest = next(r for r in rows if r["run_id"] == "TEST_RF")
    assert forest["test_run_id"] == "TEST_T13_RF" and forest["test_mae"] == 100
    new = next(r for r in rows if r["run_id"] == "TEST_NEW")
    assert new["test_run_id"] is None and "ứng viên, chưa đánh giá độc lập" in new["notes"]
    assert all(r["test_run_id"] != r["run_id"] for r in rows if r["test_run_id"])


def test_delta_requires_identical_ids_truth_and_coverage(log):
    wrong = frame(.01, prefix="TEST_OTHER_IDS")
    log.add("TEST_WRONG_IDS", task="T17b", metrics=validation_metrics(wrong), predictions={"validation": wrong})
    _, rows, _ = build(log)
    ridge = next(r for r in rows if r["run_id"] == "TEST_RIDGE")
    assert ridge["mae_reduction_pct"] == pytest.approx(50.)
    mismatch = next(r for r in rows if r["run_id"] == "TEST_WRONG_IDS")
    assert mismatch["mae_reduction_pct"] is None and not mismatch["best_validation"]


def test_persistence_test_is_separate_run_not_a_fitted_pipeline(log):
    data = frame(2, prefix="TEST_ONLY_TEST_ARTIFACT")
    log.add("TEST_T13_BASE", task="T13", model="persistence", reference="TEST_BASE", parent="TEST_T13_PARENT",
            parameters={"stage": "final_refit_test", "locked_parameters": {"rule": "PM2.5(t+1)=PM2.5(t)"}},
            metrics={"test_primary": regression_metrics(data.y_true, data.y_pred)}, predictions={"test": data})
    _, rows, _ = build(log)
    baseline = next(r for r in rows if r["run_id"] == "TEST_BASE")
    assert baseline["test_run_id"] == "TEST_T13_BASE"
    assert "quy tắc không fit" in baseline["notes"]
    assert "fitted model khác" not in baseline["notes"]


def test_inconsistent_metric_kept_and_reported_without_highlight(log):
    ridge = next(r for r in log.rows if r["run_id"] == "TEST_RIDGE")
    metrics = json.loads(ridge["metrics"])
    metrics["validation_primary"]["MAE"] = .001
    ridge["metrics"] = json.dumps(metrics)
    (log.root/"artifacts/experiments/TEST_RIDGE/metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    _, rows, evidence = build(log)
    actual = next(r for r in rows if r["run_id"] == "TEST_RIDGE")
    assert actual["validation_mae"] == .001 and not actual["best_validation"]
    assert actual["mae_reduction_pct"] is None
    assert any(c["run_id"] == "TEST_RIDGE" and c["status"] == "KHÁC" and
               c["check"].startswith("validation predictions") for c in evidence["checks"])


def test_pooled_oof_unequal_fold_sizes_and_population_std():
    a, b = frame(1, n=1, prefix="TEST_F1_"), frame(3, n=3, prefix="TEST_F2_")
    values = [regression_metrics(f.y_true, f.y_pred) for f in (a, b)]
    result = pooled_folds(values, [a, b])
    assert result["MAE"] == 2.5 and result["MAE"] != np.mean([1., 3.])
    assert result["RMSE"] == pytest.approx(np.sqrt(7)) and result["RMSE"] != 2
    assert result["fold_mean"]["MAE"] == 2 and result["fold_std"]["MAE"] == 1
    assert result["source"] == "saved_OOF_predictions"
    # Authoritative OOF preferred over inconsistent supplied fold summaries.
    result2 = pooled_folds([{"MAE": 999}, {}], [a, b])
    assert result2["MAE"] == result["MAE"]


def test_weighted_fallback_and_missing_counts_never_equal_weights():
    metrics = [{"MAE": 1., "RMSE": 1., "n_scored": 1}, {"MAE": 3., "RMSE": 3., "n_scored": 3}]
    result = pooled_folds(metrics)
    assert result["MAE"] == 2.5 and result["RMSE"] == pytest.approx(np.sqrt(7))
    assert result["source"] == "weighted_fold_metrics"
    assert pooled_folds([{"MAE": 1., "RMSE": 1.}, {"MAE": 3., "RMSE": 3.}]) is None
    assert pooled_folds([]) is None


def test_duplicate_oof_ids_are_not_silently_aggregated():
    data = frame()
    with pytest.raises(ValueError, match="overlap"):
        pooled_folds([{}, {}], [data, data])


def test_cv_candidate_joins_only_matching_validation_configuration(log):
    log.add("TEST_SEARCH", task="T11", parameters={"stage": "search"})
    ids = []
    for i, n in enumerate((1, 2, 3)):
        data = frame(i+1, n=n, prefix=f"TEST_FOLD_{i}_")
        rid = "TEST_FOLD_"+str(i); ids.append(rid)
        log.add(rid, task="T11", parameters={"stage": "fold", "alpha": 1.}, parent="TEST_CANDIDATE", fold=i+1,
                metrics={"evaluation": regression_metrics(data.y_true, data.y_pred)}, predictions={"evaluation": data})
    log.add("TEST_CANDIDATE", task="T11", parameters={"stage": "candidate", "alpha": 1.}, parent="TEST_SEARCH",
            reference="TEST_RIDGE", metrics={"fold_run_ids": ids})
    _, rows, evidence = build(log, include_plans=False)
    ridge = next(r for r in rows if r["run_id"] == "TEST_RIDGE")
    assert ridge["cv_run_id"] == "TEST_CANDIDATE"
    assert ridge["cv_pooled_mae"] == pytest.approx(14/6)
    assert not any(r["run_id"] == "TEST_CANDIDATE" for r in rows)
    assert len(evidence["runs"]) == len(log.rows)


def test_missing_metrics_and_failed_candidate_retained_without_highlight(log):
    log.add("TEST_MISSING", task="T17b")
    log.add("TEST_FAILED", task="T11", parameters={"stage": "candidate", "alpha": 100.}, status="failed")
    log.save()
    (log.root/"artifacts/experiments/TEST_MISSING/metrics.json").unlink()
    reader = Reader(log.root)
    rows, evidence = build_summary(reader)
    missing = next(r for r in rows if r["run_id"] == "TEST_MISSING")
    failed = next(r for r in rows if r["run_id"] == "TEST_FAILED")
    assert missing["validation_mae"] is None and missing["mae_reduction_pct"] is None
    assert failed["status"] == "failed" and failed["cv_pooled_mae"] is None and not failed["best_validation"]
    assert evidence["warnings"]
    assert any(r["has_error"] for r in evidence["runs"])


def test_non_t13_test_artifacts_forbidden_and_wrong_parameters_not_attributed(log):
    log.save()
    reader = Reader(log.root)
    records = reader.load()
    arbitrary = next(r for r in records if r.id == "TEST_RIDGE")
    arbitrary.artifacts = next(r for r in records if r.id == "TEST_T13_RF").artifacts
    with pytest.raises(ValueError):
        reader.prediction(arbitrary, "test")
    t13 = next(r for r in log.rows if r["run_id"] == "TEST_T13_RF")
    t13["parameters"] = json.dumps({"stage": "final_refit_test", "locked_parameters": {"n_estimators": 999}})
    _, rows, _ = build(log)
    assert next(r for r in rows if r["run_id"] == "TEST_RF")["test_run_id"] is None


def test_plans_blank_and_empty_log_graceful(tmp_path):
    empty = TEST_ONLY_Log(tmp_path)
    _, rows, evidence = build(empty)
    assert len(rows) == 2 and evidence["ledger_rows"] == 0
    assert all(r["status"] == "not_run" and r["run_id"] is None and r["test_mae"] is None and
               r["validation_mae"] is None and not r["best_validation"] for r in rows)


def test_empty_log_without_plans_exports_headers_and_explanatory_image(tmp_path):
    log = TEST_ONLY_Log(tmp_path)
    reader, rows, evidence = build(log, include_plans=False)
    export_summary(reader, rows, evidence)
    data = pd.read_csv(tmp_path/"reports/tables/experiment_summary.csv")
    assert data.empty and "Validation MAE" in data.columns
    assert (tmp_path/"reports/tables/experiment_summary.png").stat().st_size > 1000


def test_exports_byte_identical_unicode_and_honest_checks(log):
    reader, rows, evidence = build(log)
    ledger = reader.ledger.read_bytes()
    first = export_summary(reader, rows, evidence)
    directory = log.root/"reports/tables"
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    # Fresh reader simulates a second CLI process, not reuse of in-memory frames.
    second_reader = Reader(log.root)
    second_rows, second_evidence = build_summary(second_reader)
    second = export_summary(second_reader, second_rows, second_evidence)
    assert first["generated_at"] == second["generated_at"]
    assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    assert reader.ledger.read_bytes() == ledger
    assert "Đã khóa" in (directory/"experiment_summary.md").read_text(encoding="utf-8")
    assert all(str(log.root) not in p.read_text(encoding="utf-8-sig") for p in directory.glob("*.csv"))
    assert any(c["status"] == "KHÁC" for c in evidence["checks"])  # Synthetic values differ from real checkpoints.
    assert not first["raw_test_samples_read"] and first["new_experiment_runs"] == 0
