"""Verify T12 hierarchy, group selection, metrics and locked development decision."""

import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from beijing_air.ablation import load_train_B, choose_k, choose_deployment
from beijing_air.data import sha256
from beijing_air.eda import read_json
from beijing_air.evaluation import load_train_validation
from beijing_air.feature_selection import encoded_groups
from beijing_air.metrics import regression_metrics
from beijing_air.temporal_cv import expanding_folds, membership
from beijing_air.tuning import aggregate_folds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_tuning import close
from run_ablation import historical_prediction


def record(root, run_id, index):
    assert len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id)
    d = root / "artifacts/experiments" / run_id
    cfg, meta, scores = (read_json(d / f"{name}.json") for name in ("config", "metadata", "metrics"))
    assert cfg["task_id"] in ("T12", "TEST_ONLY_T12") and meta["status"] in ("completed", "failed")
    row = index[run_id]
    assert json.loads(row["metrics"]) == scores and row["status"] == meta["status"]
    for name in ("config", "metadata", "metrics", "notes"):
        assert (root / "experiments" / row[f"{name}_path"]).resolve() == d / ("notes.md" if name == "notes" else f"{name}.json")
    for info in meta["artifacts"]:
        p = (root / "experiments" / info["path"]).resolve()
        assert p.is_relative_to(d) and p.stat().st_size == info["size_bytes"] and sha256(p) == info["sha256"]
    if meta["status"] == "failed": assert meta["error"]
    return d, cfg, meta, scores


def check_state(state, xfit, *, alpha, k):
    assert state["raw_feature_names"] == xfit.columns.tolist() and len(xfit.columns) == 33
    assert state["parameters"]["alpha"] == alpha and state["weights_saved"] is False
    groups = encoded_groups(state["encoded_feature_names"], state["raw_feature_names"])
    assert groups.tolist() == state["column_groups"]
    numeric = xfit[state["numeric_features"]].astype(float)
    medians = numeric.median().fillna(0.)
    np.testing.assert_allclose(state["imputer_statistics"], medians, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(state["scaler_mean"], numeric.fillna(medians).mean(), rtol=1e-10, atol=1e-10)
    if k is not None:
        coef = np.asarray(state["pilot_coef"])
        assert state["pilot_parameters"]["alpha"] == alpha
        scores = {g: float(np.sqrt(np.mean(coef[groups == g]**2))) for g in state["raw_feature_names"]}
        close(scores, state["group_scores"])
        ranking = sorted(scores, key=lambda g: (-scores[g], state["raw_feature_names"].index(g)))
        chosen = set(ranking[:k])
        assert state["kept_groups"] == [g for g in state["raw_feature_names"] if g in chosen]
        assert state["dropped_groups"] == [g for g in state["raw_feature_names"] if g not in chosen]
    else:
        assert state["kept_groups"] == state["raw_feature_names"] and not state["dropped_groups"]
    kept = [name for name, g in zip(state["encoded_feature_names"], groups) if g in state["kept_groups"]]
    assert kept == state["model_feature_names"] and len(kept) == state["model_dimensions"] == len(state["coef"])


def verify(root, parent_id):
    root = Path(root).resolve()
    with (root / "experiments/experiment_log.csv").open(encoding="utf-8", newline="") as stream: rows = list(csv.DictReader(stream))
    index = {r["run_id"]: r for r in rows}
    assert len(index) == len(rows)
    directory, cfg, meta, metrics = record(root, parent_id, index)
    assert meta["status"] == "completed" and cfg["parameters"]["stage"] == "search"
    sig, mode = cfg["parameters"]["signature"], cfg["mode"]
    d = sig["design"]
    for name, digest in sig["source_sha256"].items(): assert sha256(directory / "artifacts/source" / name) == digest
    train, x, provenance = load_train_B(root)
    assert provenance == sig["provenance"] and membership(train) == cfg["data"]["train"]
    config = read_json(root / "configs/default.json")
    assert config["temporal_cv"] == sig["temporal_cv"]
    folds = expanding_folds(train, config)
    assert [f.audit for f in folds] == read_json(directory / "artifacts/data/folds.json")
    result = read_json(directory / "artifacts/search/results.json")
    locked = read_json(directory / "artifacts/search/selection.json")
    assert locked["selection"] == result["selection"] and locked["candidates"] == result["candidates"]
    assert [c["k_groups"] for c in result["candidates"]] == (d["selector"]["k_groups"] if mode == "full" else d["smoke"]["k_groups"])
    fold_rows, group_rows = [], []
    for c in result["candidates"]:
        _, cc, cm, cs = record(root, c["run_id"], index)
        assert cc["parent_run_id"] == parent_id and c["status"] == cm["status"] and len(c["fold_run_ids"]) == 3
        predictions, failed = [], []
        for fold, rid in zip(folds, c["fold_run_ids"]):
            path, fc, fm, fs = record(root, rid, index)
            assert fc["parent_run_id"] == c["run_id"] and fc["fold_id"] == fold.fold_id and fc["split"] == fold.audit
            fit, ev = fold.fit, fold.evaluation
            if mode == "smoke":
                fit = train.iloc[fit].groupby("station", sort=True).head(d["smoke"]["train_rows_per_station"]).index.to_numpy()
                ev = train.iloc[ev].groupby("station", sort=True).head(d["smoke"]["evaluation_rows_per_station"]).index.to_numpy()
            assert fc["data"] == {"fit": membership(train.iloc[fit]), "evaluation": membership(train.iloc[ev])}
            if fm["status"] == "failed": failed.append(rid); continue
            pred = pd.read_csv(path / "artifacts/predictions/evaluation.csv.gz")
            assert pred.sample_id.tolist() == train.iloc[ev].sample_id.tolist() and pred.sample_id.is_unique
            assert pred.run_id.eq(rid).all() and pred.fold_id.eq(fold.fold_id).all() and pred.k_groups.eq(c["k_groups"]).all()
            np.testing.assert_allclose(pred.y_true, train.iloc[ev].target_pm25, rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(pred.residual, pred.y_pred-pred.y_true, rtol=1e-12, atol=1e-12)
            close(regression_metrics(pred.y_true, pred.y_pred), fs["evaluation"])
            assert fs["validation_csv_accessed"] is False and fs["test_csv_accessed"] is False
            state = read_json(path / "artifacts/model/selection_state.json")
            check_state(state, x.iloc[fit], alpha=d["alpha"], k=c["k_groups"])
            fold_rows.append({"candidate_run_id": c["run_id"], "run_id": rid, "k_groups": c["k_groups"], "fold_id": fold.fold_id,
                              "fit_n": len(fit), "evaluation_n": len(ev), "model_dimensions": state["model_dimensions"],
                              **{key: fs["evaluation"][key] for key in ("MAE", "RMSE", "R2")}, **fs["timing_seconds"]})
            for raw in state["raw_feature_names"]:
                group_rows.append({"run_id": rid, "stage": "cv", "k_groups": c["k_groups"], "fold_id": fold.fold_id,
                                   "feature": raw, "kept": raw in state["kept_groups"], "score": state["group_scores"][raw]})
            predictions.append(pred)
        assert failed == c["failed_fold_run_ids"] == cs["failed_fold_run_ids"]
        if not failed:
            summary = aggregate_folds(predictions)
            close(summary, c["summary"]); close(summary, {key: cs[key] for key in summary})
    selected = choose_k(result["candidates"], d["selection"]["tolerance"])
    assert selected["k_groups"] == result["selection"]["k_groups"] and selected["run_id"] == result["selection"]["candidate_run_id"]
    assert result["selection"]["before_validation"] and result["test_csv_accessed"] is False
    comparisons = []
    if mode == "full":
        _, validation, _ = load_train_validation(root)
        validation = validation.loc[validation.is_primary]
        assert len(result["final_run_ids"]) == 2
        for variant, rid in result["final_run_ids"].items():
            path, vc, vm, vs = record(root, rid, index)
            assert vc["parent_run_id"] == parent_id and vc["feature_set"] == variant and vc["parameters"]["alpha"] == d["alpha"]
            assert datetime.fromisoformat(result["selection"]["locked_at"]) < datetime.fromisoformat(vm["started_at"])
            state = read_json(path / "artifacts/model/selection_state.json")
            check_state(state, x, alpha=d["alpha"], k=selected["k_groups"] if variant == "C" else None)
            for split, expected in (("train", train), ("validation", validation)):
                pred = pd.read_csv(path / f"artifacts/predictions/{split}.csv.gz")
                assert pred.sample_id.tolist() == expected.sample_id.tolist() and pred.sample_id.is_unique and pred.run_id.eq(rid).all()
                np.testing.assert_allclose(pred.y_true, expected.target_pm25, rtol=1e-12, atol=1e-12)
                actual = regression_metrics(pred.y_true, pred.y_pred)
                actual["negative_predictions"] = int(pred.y_pred.lt(0).sum())
                close(actual, vs[f"{split}_primary"])
            for raw in state["raw_feature_names"]:
                group_rows.append({"run_id": rid, "stage": variant, "k_groups": len(state["kept_groups"]), "fold_id": None,
                                   "feature": raw, "kept": raw in state["kept_groups"], "score": state["group_scores"][raw] if state["group_scores"] else None})
        for stored in result["comparison"]:
            _, pred = historical_prediction(root, stored["run_id"])
            assert pred.sample_id.tolist() == validation.sample_id.tolist()
            np.testing.assert_allclose(pred.y_true, validation.target_pm25, rtol=1e-12, atol=1e-12)
            score = regression_metrics(pred.y_true, pred.y_pred)
            for key in score: close(score[key], stored[key])
            assert int(pred.y_pred.lt(0).sum()) == stored["negative_predictions"]
            comparisons.append(stored)
        frozen = read_json(directory / "artifacts/selection/frozen_model.json")
        winner = choose_deployment(comparisons, d)
        assert frozen["selected_run_id"] == winner["run_id"] and frozen["selected_variant"] == winner["variant"]
        assert frozen == read_json(root / "reports/ablation/frozen_model.json") and frozen["validation_results"] == result["comparison"]
        assert frozen["test_locked"] is True and frozen["test_evaluated"] is False and frozen["weights_artifact"] is None
        assert frozen["selection"] == d["selection"] and frozen["postprocessing"] == sig["preprocessing"]["prediction_postprocessing"]
        assert frozen["data"]["train"] == membership(train) and frozen["data"]["validation"] == membership(validation)
        winner_cfg = read_json(root / "artifacts/experiments" / winner["run_id"] / "config.json")
        assert frozen["model"]["name"] == winner_cfg["model"] and frozen["model"]["seed"] == winner_cfg["seed"]
        assert frozen["preprocessing"] == winner_cfg["preprocessing"]
        if winner["variant"] in ("B", "C"):
            state = read_json(root / "artifacts/experiments" / winner["run_id"] / "artifacts/model/selection_state.json")
            assert frozen["model"]["parameters"] == state["parameters"] and frozen["features"]["fitted_train_state"] == state
        else:
            params = winner_cfg["parameters"]
            expected = params.get("actual_model_parameters", params.get("signature", {}).get("effective_model_parameters", params))
            assert frozen["model"]["parameters"] == expected
        if frozen["features"]["feature_set"] == "C":
            assert frozen["features"]["selector"]["selected_k_groups"] == selected["k_groups"]
    else: assert not result["final_run_ids"] and not result["comparison"]
    assert metrics["attempted_cv_pipeline_fits"] == len(result["candidates"])*3
    print(f"PASS T12/{mode} {parent_id}: source/artifacts/CSV, IDs/purge, fold-fit preprocessing/group ranking, CV metrics, A/B/C and frozen selection")
    return result, pd.DataFrame(fold_rows), pd.DataFrame(group_rows)


def write_reports(root, result, folds, groups):
    root = Path(root)
    assert result["official_full"] and result["mode"] == "full"
    output = root / "reports/ablation"
    candidates = []
    for c in result["candidates"]:
        score = c.get("summary")
        candidates.append({"run_id": c["run_id"], "k_groups": c["k_groups"], "status": c["status"],
                           "selected": c["run_id"] == result["selection"]["candidate_run_id"],
                           **({f"pooled_{m}": score["pooled"][m] for m in ("MAE", "RMSE", "R2")} if score else {}),
                           **({f"fold_{stat}_{m}": score[f"fold_{stat}"][m] for stat in ("mean", "std") for m in ("MAE", "RMSE", "R2")} if score else {})})
    cv = pd.DataFrame(candidates)
    table = pd.DataFrame(result["comparison"])
    for i, row in table.iterrows():
        directory = root / "artifacts/experiments" / row.run_id
        path = directory / "artifacts/model/selection_state.json"
        if path.exists():
            state = read_json(path)
            table.loc[i, "raw_groups"] = len(state["kept_groups"])
            table.loc[i, "model_dimensions"] = state["model_dimensions"]
            table.loc[i, "fit_seconds"] = read_json(directory / "metrics.json")["timing_seconds"]["fit_pipeline"]
        else:
            path = directory / "artifacts/model/fitted_pipeline_state.json"
            if path.exists():
                state = read_json(path)
                table.loc[i, "raw_groups"] = len(state["input_feature_names"])
                table.loc[i, "model_dimensions"] = state["model_n_features_in"]
            # Timing stays NA: these are reused historic runs, not timed T12 fits.
    for name, frame in (("candidates", cv), ("fold_metrics", folds), ("selected_features", groups), ("comparison", table)):
        frame.to_csv(output / f"{name}.csv", index=False, na_rep="NA", encoding="utf-8", lineterminator="\n")
    os.environ["MPLCONFIGDIR"] = str(root / "artifacts/ablation_plot_cache")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    axes[0].plot(cv.k_groups, cv.pooled_MAE, "o-")
    axes[0].set(xlabel="Kept raw feature groups", ylabel="Pooled CV MAE (µg/m³)", title="C: three train-only temporal folds")
    abc = table.set_index("variant").loc[["A", "B", "C"]]
    axes[1].bar(abc.index, abc.MAE)
    axes[1].set(ylabel="Validation MAE (µg/m³)", title="A/B/C, same Ridge alpha=0.1 and IDs")
    axes[2].bar(table.variant, table.MAE)
    axes[2].set(ylabel="Validation MAE (µg/m³)", title="Deployment pool incl. historical comparators")
    axes[2].tick_params(axis="x", rotation=25, labelsize=8)
    fig.tight_layout()
    target = root / "reports/figures/ablation/comparison.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=150); plt.close(fig)
    print(cv.to_string(index=False))
    print(table[["variant", "MAE", "RMSE", "R2", "raw_groups", "model_dimensions", "fit_seconds"]].to_string(index=False))


def main():
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", nargs="+")
    p.add_argument("--write-report", action="store_true")
    args = p.parse_args()
    for rid in args.run_id or []: verify(root, rid)
    if args.write_report:
        rid = read_json(root / "reports/ablation/full/run.json")["parent_run_id"]
        result, folds, groups = verify(root, rid)
        write_reports(root, result, folds, groups)


if __name__ == "__main__": main()
