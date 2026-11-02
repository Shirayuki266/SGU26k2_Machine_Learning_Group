"""Verify recorded T10 artifacts and compare real full runs, without model fits."""

import argparse
import csv
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from beijing_air.data import sha256
from beijing_air.eda import read_json, ids_digest
from beijing_air.evaluation import load_train_validation
from beijing_air.metrics import regression_metrics


def verify_run(root, run_id):
    root = Path(root).resolve()
    if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
        raise ValueError("Invalid run ID")
    directory = root / "artifacts/experiments" / run_id
    cfg, record, scores = [read_json(directory / f"{name}.json") for name in ("config", "metadata", "metrics")]
    assert cfg["task_id"] in ("T10", "TEST_ONLY_T10") and record["status"] == "completed"
    assert cfg["feature_set"] == "A" and scores["test_csv_accessed"] is False
    for info in record["artifacts"]:
        path = (root / "experiments" / info["path"]).resolve()
        assert path.is_relative_to(directory) and path.stat().st_size == info["size_bytes"] and sha256(path) == info["sha256"]
    for name, digest in cfg["parameters"]["signature"]["source_sha256"].items():
        assert sha256(directory / "artifacts/source" / name) == digest
    with (root / "experiments/experiment_log.csv").open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["run_id"] == run_id]
    assert len(rows) == 1 and json.loads(rows[0]["metrics"]) == scores
    for name in ("config", "metadata", "metrics", "notes"):
        path = (root / "experiments" / rows[0][f"{name}_path"]).resolve()
        assert path == directory / ("notes.md" if name == "notes" else f"{name}.json")
    state = read_json(directory / "artifacts/model/fitted_pipeline_state.json")
    assert state["weights_saved"] is False and state["pipeline_class"] == "sklearn.pipeline.Pipeline"
    assert len(state["input_feature_names"]) == 20 and state["model_n_features_in"] == len(state["output_feature_names"])
    assert state["parameters"] == cfg["parameters"]["signature"]["effective_model_parameters"]
    if cfg["model"] == "random_forest":
        assert state["model_class"].endswith("RandomForestRegressor")
        assert state["n_estimators_fitted"] == state["parameters"]["n_estimators"]
        assert state["maximum_tree_depth"] <= state["parameters"]["max_depth"] <= 12
    else:
        assert state["model_class"].endswith("Ridge") and len(state["coef"]) == state["model_n_features_in"]
    train, validation, provenance = load_train_validation(root)
    assert provenance == cfg["data"]["provenance"]
    anchor = read_json(root / "reports/evaluation/validation_manifest.json")
    assert anchor == cfg["data"]["validation_anchor"]
    for name, data in (("train", train), ("validation", validation)):
        expected = data.loc[data.is_primary]
        if cfg["mode"] == "smoke":
            expected = expected.groupby("station", sort=True).head(cfg["parameters"]["signature"]["design"]["smoke"][f"{name}_rows_per_station"])
        pred = pd.read_csv(directory / f"artifacts/predictions/{name}.csv.gz")
        assert pred.sample_id.tolist() == expected.sample_id.tolist() and pred.sample_id.is_unique and pred.is_primary.all()
        assert pred.run_id.eq(run_id).all() and pred.model.eq(cfg["model"]).all() and pred["split"].eq(name).all()
        assert ids_digest(pred.sample_id) == cfg["data"]["selected_membership"][name]["ordered_ids_sha256"]
        assert len(pred) == cfg["sample_counts"][name]
        np.testing.assert_allclose(pred.y_true, expected.target_pm25, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(pred.residual, pred.y_pred-pred.y_true, rtol=1e-12, atol=1e-12)
        calculated = regression_metrics(pred.y_true, pred.y_pred)
        for key, value in calculated.items():
            recorded = scores[f"{name}_primary"][key]
            if isinstance(value, (int, float)):
                assert np.isclose(value, recorded, rtol=1e-12, atol=1e-12), key
            else:
                assert value == recorded
        assert int(pred.y_pred.lt(0).sum()) == scores[f"{name}_primary"]["negative_predictions"]
        if name == "validation":
            baseline_dir = root / "artifacts/experiments" / cfg["reference_run_id"]
            baseline = pd.read_csv(baseline_dir / "artifacts/predictions/validation.csv")
            matched = baseline.loc[baseline.is_primary].set_index("sample_id").loc[pred.sample_id]
            np.testing.assert_allclose(matched.y_true, pred.y_true, rtol=1e-12, atol=1e-12)
            ref = regression_metrics(matched.y_true, matched.y_pred)
            for metric in ("MAE", "RMSE", "R2"):
                assert np.isclose(ref[metric], scores["validation_baseline"][metric], rtol=1e-12, atol=1e-12)
    assert np.isclose(scores["generalization_gap_MAE"], scores["validation_primary"]["MAE"]-scores["train_primary"]["MAE"])
    print(f"PASS {cfg['model']}/{cfg['mode']} {run_id}: train/validation IDs, metric recomputation, pipeline summary, artifact/CSV hashes")
    return cfg, scores, record


def build_comparison(root):
    root = Path(root).resolve()
    results, references = [], set()
    for model in ("ridge", "random_forest"):
        pointer = read_json(root / "reports/initial_models/full" / model / "run.json")
        cfg, scores, record = verify_run(root, pointer["run_id"])
        assert cfg["mode"] == "full" and not cfg["is_test"]
        references.add(cfg["reference_run_id"])
        results.append({"model": model, "run_id": pointer["run_id"], "train_n": scores["train_primary"]["n_total"],
                        "validation_n": scores["validation_primary"]["n_total"],
                        **{f"train_{k}": scores["train_primary"][k] for k in ("MAE", "RMSE", "R2")},
                        **{f"validation_{k}": scores["validation_primary"][k] for k in ("MAE", "RMSE", "R2")},
                        "generalization_gap_MAE": scores["generalization_gap_MAE"],
                        "delta_MAE_vs_persistence": scores["validation_delta_MAE_vs_persistence"],
                        "fit_seconds": scores["timing_seconds"]["fit_pipeline"],
                        "predict_validation_seconds": scores["timing_seconds"]["predict_validation"],
                        "duration_seconds": record["duration_seconds"],
                        "negative_validation_predictions": scores["validation_primary"]["negative_predictions"]})
    if len(references) != 1:
        raise ValueError("Models refer to different persistence baselines")
    reference = references.pop()
    baseline_dir = root / "artifacts/experiments" / reference
    cfg, ref = read_json(baseline_dir / "config.json"), read_json(baseline_dir / "metrics.json")
    assert cfg["task_id"] == "T09" and cfg["mode"] == "full"
    baseline_values = ref["validation_primary"]
    baseline_pred = pd.read_csv(baseline_dir / "artifacts/predictions/validation.csv")
    baseline_primary = baseline_pred.loc[baseline_pred.is_primary]
    recalculated = regression_metrics(baseline_primary.y_true, baseline_primary.y_pred)
    for key in ("MAE", "RMSE", "R2"):
        assert np.isclose(recalculated[key], baseline_values[key], rtol=1e-12, atol=1e-12)
    assert all(row["validation_n"] == baseline_values["n_total"] for row in results)
    baseline_row = {"model": "persistence", "run_id": reference, "train_n": None,
                    "validation_n": baseline_values["n_total"],
                    **{f"train_{k}": None for k in ("MAE", "RMSE", "R2")},
                    **{f"validation_{k}": baseline_values[k] for k in ("MAE", "RMSE", "R2")},
                    "generalization_gap_MAE": None, "delta_MAE_vs_persistence": 0., "fit_seconds": None,
                    "predict_validation_seconds": None, "duration_seconds": None,
                    "negative_validation_predictions": int(baseline_primary.y_pred.lt(0).sum())}
    table = pd.DataFrame([baseline_row, *results])
    directory = root / "reports/initial_models"
    table.to_csv(directory / "comparison.csv", index=False, na_rep="NA", encoding="utf-8", lineterminator="\n")
    os.environ["MPLCONFIGDIR"] = str(root / "artifacts/initial_models_plot_cache")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, metric in zip(axes[0], ("MAE", "RMSE")):
        ax.bar(table.model, table[f"validation_{metric}"], color=["#777777", "#287f8e", "#db8c33"])
        ax.set(ylabel=f"Validation {metric} (µg/m³)", title=f"Same {baseline_values['n_total']:,} primary IDs")
    fitted = table.loc[table.model.ne("persistence")]
    positions = np.arange(len(fitted))
    axes[1, 0].bar(positions-.18, fitted.train_MAE, width=.36, label="In-sample train")
    axes[1, 0].bar(positions+.18, fitted.validation_MAE, width=.36, label="Validation")
    axes[1, 0].set(xticks=positions, xticklabels=fitted.model, ylabel="MAE (µg/m³)", title="Temporal generalization gap (not CV)")
    axes[1, 0].legend()
    axes[1, 1].bar(fitted.model, fitted.fit_seconds)
    axes[1, 1].set(ylabel="Pipeline fit wall time (seconds)", title="One BLAS thread, RF n_jobs=1")
    fig.suptitle("T10 initial feature A models — full primary train/validation")
    fig.tight_layout(rect=(0, 0, 1, .96))
    figure = root / "reports/figures/initial_models/comparison.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure, dpi=150)
    plt.close(fig)
    print(table.to_string(index=False))
    return table


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", nargs="+")
    parser.add_argument("--write-comparison", action="store_true")
    args = parser.parse_args()
    for run_id in args.run_id or []:
        verify_run(root, run_id)
    if args.write_comparison:
        build_comparison(root)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
