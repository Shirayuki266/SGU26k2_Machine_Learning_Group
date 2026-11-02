"""Recompute T11 CV/validation artifacts and before/after tables; never fit."""

import argparse
from copy import deepcopy
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from beijing_air.data import sha256
from beijing_air.eda import read_json
from beijing_air.initial_models import load_initial_data
from beijing_air.metrics import regression_metrics
from beijing_air.temporal_cv import expanding_folds, membership
from beijing_air.tuning import aggregate_folds, choose_candidate, load_cv_training


def close(actual, expected):
    if isinstance(actual, dict):
        assert actual.keys() == expected.keys()
        for key in actual:
            close(actual[key], expected[key])
    elif isinstance(actual, list):
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected): close(a, e)
    elif isinstance(actual, (float, int)) and not isinstance(actual, bool):
        assert np.isclose(actual, expected, rtol=1e-11, atol=1e-11), (actual, expected)
    else:
        assert actual == expected, (actual, expected)


def run_record(root, run_id, index):
    assert len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id)
    d = root / "artifacts/experiments" / run_id
    cfg, meta, metrics = (read_json(d / f"{name}.json") for name in ("config", "metadata", "metrics"))
    assert cfg["task_id"] in ("T11", "TEST_ONLY_T11") and meta["status"] in ("completed", "failed")
    row = index[run_id]
    assert row["status"] == meta["status"] and json.loads(row["metrics"]) == metrics
    for name in ("config", "metadata", "metrics", "notes"):
        expected = d / ("notes.md" if name == "notes" else f"{name}.json")
        assert (root / "experiments" / row[f"{name}_path"]).resolve() == expected
    for entry in meta["artifacts"]:
        p = (root / "experiments" / entry["path"]).resolve()
        assert p.is_relative_to(d) and p.stat().st_size == entry["size_bytes"] and sha256(p) == entry["sha256"]
    if meta["status"] == "failed": assert meta["error"] is not None
    return d, cfg, meta, metrics


def check_state(state, cfg, x_fit):
    assert state["pipeline_class"] == "sklearn.pipeline.Pipeline" and state["model_class"].endswith("Ridge")
    assert state["weights_saved"] is False and state["parameters"] == cfg["parameters"]["actual_model_parameters"]
    assert state["parameters"]["alpha"] == cfg["parameters"]["alpha"]
    assert state["input_feature_names"] == list(x_fit.columns) and len(x_fit.columns) == 20
    assert len(state["output_feature_names"]) == state["model_n_features_in"] == len(state["coef"])
    numeric = x_fit[state["numeric_features"]].astype(float)
    medians = numeric.median().fillna(0.)
    np.testing.assert_allclose(state["numeric_imputation_statistics"], medians, rtol=1e-10, atol=1e-10)
    imputed = numeric.fillna(medians)
    np.testing.assert_allclose(state["scaler_mean"], imputed.mean(), rtol=1e-10, atol=1e-10)


def verify_search(root, parent_id):
    root = Path(root).resolve()
    with (root / "experiments/experiment_log.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    index = {r["run_id"]: r for r in rows}
    assert len(index) == len(rows)
    directory, cfg, meta, metrics = run_record(root, parent_id, index)
    assert cfg["parameters"]["stage"] == "search" and meta["status"] == "completed"
    signature, mode = cfg["parameters"]["signature"], cfg["mode"]
    for name, digest in signature["source_sha256"].items():
        assert sha256(directory / "artifacts/source" / name) == digest
    data, x, provenance = load_cv_training(root)
    assert provenance == signature["provenance"] and membership(data) == cfg["data"]["train_membership"]
    configuration = deepcopy(read_json(root / "configs/default.json"))
    configuration["temporal_cv"] = signature["temporal_cv"]
    folds = expanding_folds(data, configuration)
    assert [f.audit for f in folds] == read_json(directory / "artifacts/data/folds.json")
    result = read_json(directory / "artifacts/search/results.json")
    selection = read_json(directory / "artifacts/search/selection.json")
    assert result["candidates"] == selection["candidates"] and result["selection"] == selection["selection"]
    candidates, fold_rows, attempted = [], [], 0
    alphas = signature["design"]["alphas"] if mode == "full" else signature["design"]["smoke"]["alphas"]
    assert [c["alpha"] for c in result["candidates"]] == alphas
    for candidate in result["candidates"]:
        _, ccfg, cmeta, cm = run_record(root, candidate["run_id"], index)
        assert ccfg["parent_run_id"] == parent_id and ccfg["parameters"] == {"stage": "candidate", "alpha": candidate["alpha"]}
        assert cmeta["status"] == candidate["status"] and len(candidate["fold_run_ids"]) == 3
        predictions, failures = [], []
        for fold, run_id in zip(folds, candidate["fold_run_ids"]):
            attempted += 1
            d, fc, fm, scores = run_record(root, run_id, index)
            assert fc["parent_run_id"] == candidate["run_id"] and fc["fold_id"] == fold.fold_id
            assert fc["parameters"]["source_parent_run_id"] == parent_id and fc["split"] == fold.audit
            fit, evaluation_positions = fold.fit, fold.evaluation
            if mode == "smoke":
                smoke = signature["design"]["smoke"]
                fit = data.iloc[fit].groupby("station", sort=True).head(smoke["train_rows_per_station"]).index.to_numpy()
                evaluation_positions = data.iloc[evaluation_positions].groupby("station", sort=True).head(smoke["evaluation_rows_per_station"]).index.to_numpy()
            expected = data.iloc[evaluation_positions]
            assert fc["data"] == {"fit": membership(data.iloc[fit]), "evaluation": membership(expected)}
            if fm["status"] == "failed":
                failures.append(run_id)
                continue
            pred = pd.read_csv(d / "artifacts/predictions/evaluation.csv.gz")
            assert pred.sample_id.tolist() == expected.sample_id.tolist() and pred.sample_id.is_unique
            assert pred.is_primary.all() and pred.run_id.eq(run_id).all() and pred.fold_id.eq(fold.fold_id).all()
            assert pred.alpha.eq(candidate["alpha"]).all() and pred.candidate_run_id.eq(candidate["run_id"]).all()
            np.testing.assert_allclose(pred.y_true, expected.target_pm25, rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(pred.residual, pred.y_pred-pred.y_true, rtol=1e-12, atol=1e-12)
            actual = regression_metrics(pred.y_true, pred.y_pred)
            actual["negative_predictions"] = int(pred.y_pred.lt(0).sum())
            close(actual, scores["evaluation"])
            assert scores["validation_csv_accessed"] is False and scores["test_csv_accessed"] is False
            check_state(read_json(d / "artifacts/model/fitted_pipeline_state.json"), fc, x.iloc[fit])
            predictions.append(pred)
            fold_rows.append({"candidate_run_id": candidate["run_id"], "alpha": candidate["alpha"], "fold_id": fold.fold_id,
                              "run_id": run_id, "fit_n": len(fit), "evaluation_n": len(expected),
                              **{k: actual[k] for k in ("MAE", "RMSE", "R2")}, **scores["timing_seconds"]})
        assert failures == candidate["failed_fold_run_ids"] == cm["failed_fold_run_ids"]
        if failures:
            assert candidate["status"] == "failed"
        else:
            summary = aggregate_folds(predictions)
            close(summary, candidate["summary"])
            close(summary, {k: cm[k] for k in summary})
        candidates.append(candidate)
    assert attempted == metrics["attempted_cv_fits"] == len(alphas)*3
    selected = choose_candidate(candidates)
    assert selected["run_id"] == result["selection"]["selected_candidate_run_id"] and selected["alpha"] == result["selection"]["alpha"]
    assert result["selection"]["selection_locked_before_validation"] is True and result["test_csv_accessed"] is False
    if mode == "full":
        d, rc, rm, rs = run_record(root, result["refit_run_id"], index)
        assert rc["parent_run_id"] == parent_id and rc["parameters"]["selected_candidate_run_id"] == selected["run_id"]
        assert rc["parameters"]["alpha"] == selected["alpha"] and rs["selection_source"] == "train_cv_only"
        assert datetime.fromisoformat(result["selection"]["locked_at"]) < datetime.fromisoformat(rm["started_at"])
        sets, matrices, _, anchor, _ = load_initial_data(root, mode="full", design=read_json(root / "configs/initial_models.json"))
        assert rc["data"]["validation_anchor"] == anchor
        check_state(read_json(d / "artifacts/model/fitted_pipeline_state.json"), rc, matrices["train"])
        for partition in ("train", "validation"):
            pred = pd.read_csv(d / f"artifacts/predictions/{partition}.csv.gz")
            assert pred.sample_id.tolist() == sets[partition].sample_id.tolist() and pred.sample_id.is_unique
            assert pred.run_id.eq(result["refit_run_id"]).all() and pred["split"].eq(partition).all()
            np.testing.assert_allclose(pred.y_true, sets[partition].target_pm25, rtol=1e-12, atol=1e-12)
            score = regression_metrics(pred.y_true, pred.y_pred)
            score["negative_predictions"] = int(pred.y_pred.lt(0).sum())
            close(score, rs[f"{partition}_primary"])
        assert rs["test_csv_accessed"] is False
    else:
        assert result["refit_run_id"] is None
    print(f"PASS T11/{mode} {parent_id}: hierarchy, failures, fold purge/IDs, train-only medians/scaler, metric aggregation/selection, hashes and CSV links")
    return result, pd.DataFrame(fold_rows)


def write_reports(root, result, fold_table):
    root = Path(root).resolve()
    assert result["mode"] == "full" and result["official_full_search"]
    parent = root / "artifacts/experiments" / result["parent_run_id"]
    cfg = read_json(parent / "config.json")
    rows = []
    for c in result["candidates"]:
        s = c.get("summary")
        rows.append({"alpha": c["alpha"], "run_id": c["run_id"], "status": c["status"],
                     "selected": c["run_id"] == result["selection"]["selected_candidate_run_id"],
                     **({f"pooled_{m}": s["pooled"][m] for m in ("MAE", "RMSE", "R2")} if s else {}),
                     **({f"fold_{stat}_{m}": s[f"fold_{stat}"][m] for stat in ("mean", "std") for m in ("MAE", "RMSE", "R2")} if s else {}),
                     "fit_seconds": float(fold_table.loc[fold_table.candidate_run_id.eq(c["run_id"]), "fit_pipeline"].sum())})
    candidate_table = pd.DataFrame(rows)
    references = [("Ridge T10", cfg["reference_run_id"], "validation_primary", "validation.csv.gz"),
                  ("Ridge T11 selected", result["refit_run_id"], "validation_primary", "validation.csv.gz")]
    # Persistence is a historical comparator, never a validation-based selector.
    old_cfg = read_json(root / "artifacts/experiments" / cfg["reference_run_id"] / "config.json")
    references.insert(0, ("Persistence T09", old_cfg["reference_run_id"], "validation_primary", "validation.csv"))
    comparison, frozen_ids = [], None
    for label, run_id, key, filename in references:
        directory = root / "artifacts/experiments" / run_id
        meta, scores = read_json(directory / "metadata.json"), read_json(directory / "metrics.json")
        assert meta["status"] == "completed"
        pred_path = directory / "artifacts/predictions" / filename
        artifact = next(a for a in meta["artifacts"] if a["path"].endswith("/predictions/"+filename))
        assert sha256(pred_path) == artifact["sha256"]
        pred = pd.read_csv(pred_path)
        pred = pred.loc[pred.is_primary]
        ids = pred.sample_id.tolist()
        if frozen_ids is None: frozen_ids = ids
        assert ids == frozen_ids
        actual = regression_metrics(pred.y_true, pred.y_pred)
        for metric in ("MAE", "RMSE", "R2"): close(actual[metric], scores[key][metric])
        comparison.append({"model": label, "run_id": run_id, "N": len(pred), **{m: actual[m] for m in ("MAE", "RMSE", "R2")},
                           "negative_predictions": int(pred.y_pred.lt(0).sum())})
    before_after = pd.DataFrame(comparison)
    output = root / "reports/tuning"
    for name, table in (("candidates", candidate_table), ("fold_metrics", fold_table), ("before_after", before_after)):
        table.to_csv(output / f"{name}.csv", index=False, na_rep="NA", encoding="utf-8", lineterminator="\n")
    os.environ["MPLCONFIGDIR"] = str(root / "artifacts/tuning_plot_cache")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].plot(candidate_table.alpha, candidate_table.pooled_MAE, "o-", label="Pooled CV MAE (selection)")
    axes[0].errorbar(candidate_table.alpha, candidate_table.fold_mean_MAE, yerr=candidate_table.fold_std_MAE, fmt="s--", label="Fold mean ± std (ddof=0)")
    axes[0].set(xscale="log", xlabel="Ridge alpha", ylabel="CV MAE (µg/m³)", title="Three expanding windows inside train; A fixed")
    axes[0].legend(fontsize=8)
    axes[1].bar(before_after.model, before_after.MAE, color=["#777777", "#287f8e", "#db8c33"])
    axes[1].set(ylabel="Validation MAE (µg/m³)", title=f"Same {len(frozen_ids):,} primary IDs; selected by CV")
    axes[1].tick_params(axis="x", labelsize=9)
    fig.tight_layout()
    target = root / "reports/figures/tuning/comparison.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=150)
    plt.close(fig)
    print(candidate_table.to_string(index=False))
    print(before_after.to_string(index=False))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", nargs="+")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    for run_id in args.run_id or []:
        verify_search(root, run_id)
    if args.write_report:
        run_id = read_json(root / "reports/tuning/full/run.json")["parent_run_id"]
        result, folds = verify_search(root, run_id)
        write_reports(root, result, folds)


if __name__ == "__main__":
    main()
