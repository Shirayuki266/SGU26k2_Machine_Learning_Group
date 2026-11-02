"""T09 persistence smoke/full on frozen validation IDs; never open test."""

import argparse
import csv
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
from time import perf_counter

import numpy as np
import pandas as pd

from beijing_air import baseline, evaluation, metrics
from beijing_air.data import sha256
from beijing_air.eda import read_json
from beijing_air.evaluation import freeze_validation_ids, load_train_validation, load_validation_history
from beijing_air.experiment_logging import ExperimentLogger
from beijing_air.metrics import evaluate_predictions, grouped_metrics


def source_files():
    return {"baseline.py": Path(baseline.__file__), "evaluation.py": Path(evaluation.__file__),
            "metrics.py": Path(metrics.__file__), "run_baseline.py": Path(__file__).resolve()}


def policy(config, baseline_config, preprocessing_config):
    if (baseline_config["schema_version"] != "t09-persistence-v1"
            or baseline_config["age_limit_inclusive"] is not True
            or type(baseline_config["max_history_age_hours"]) is not int or baseline_config["max_history_age_hours"] < 1
            or baseline_config["train_statistic"] != "median"
            or baseline_config["train_statistic_scope"] != "T05_operational_train_origins"
            or baseline_config["headline_cohort"] != "primary"
            or baseline_config["residual_definition"] != "y_pred_minus_y_true"
            or type(baseline_config["smoke_rows_per_station"]) is not int or baseline_config["smoke_rows_per_station"] < 1
            or baseline_config["budget"] != {"smoke_before_full": True, "max_full_runs": 1}):
        raise ValueError("Unsupported baseline policy")
    if config["evaluation"]["baseline_fallback_order"] != ["last_observed_same_station", "training_station_median", "training_global_median", "unavailable"]:
        raise ValueError("Fallback order differs from agreed protocol")
    if preprocessing_config["prediction_postprocessing"] != {
        "negative_predictions": "identity", "applies_to": ["persistence", "ridge", "random_forest"]
    }:
        raise ValueError("Expected shared identity prediction policy")


def check_budget(logger, mode, reference_run_id, signature, task_id):
    rows = []
    if logger.csv_path.exists():
        with logger.csv_path.open(encoding="utf-8", newline="") as stream:
            rows = [row for row in csv.DictReader(stream) if row["task_id"] == task_id and row["model"] == "persistence"]
    if mode == "full":
        if any(row["mode"] == "full" for row in rows):
            raise ValueError("T09 full-run budget already used; verify the existing run, do not rerun")
        match = next((r for r in rows if r["run_id"] == reference_run_id and r["mode"] == "smoke" and r["status"] == "completed"), None)
        if match is None:
            raise ValueError("Full requires a completed smoke reference_run_id")
        config_path = logger.experiment_dir / match["config_path"]
        if read_json(config_path)["parameters"]["signature"] != signature:
            raise ValueError("Code/config/data differs from smoke; run smoke for this version first")
    elif reference_run_id is not None:
        raise ValueError("Initial smoke has no reference run")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def diagnostic_plot(predictions, station_table, month_table, path, mode):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    data = predictions.loc[predictions.is_primary & predictions.y_pred.notna()]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes[0, 0].hist(data.residual, bins=80, log=True, color="#287f8e")
    axes[0, 0].set(xlabel="Prediction - observed PM2.5 (µg/m³)", ylabel="Count (log scale)", title="Primary residuals; all tails retained")
    h = axes[0, 1].hexbin(data.y_true, data.y_pred, gridsize=45, mincnt=1, bins="log", cmap="viridis")
    fig.colorbar(h, ax=axes[0, 1], label="Pair count (log scale)")
    upper = max(data.y_true.max(), data.y_pred.max())
    axes[0, 1].plot([0, upper], [0, upper], "r--", linewidth=1)
    axes[0, 1].set(xlabel="Observed PM2.5(t+1) (µg/m³)", ylabel="Prediction (µg/m³)", title="Persistence vs observed")
    station = station_table.loc[station_table.cohort.eq("primary")]
    axes[1, 0].bar(station.station, station.MAE, color="#287f8e")
    axes[1, 0].tick_params(axis="x", rotation=40)
    axes[1, 0].set(xlabel="Station", ylabel="MAE (µg/m³)", title="Primary errors by station")
    monthly = month_table.loc[month_table.cohort.eq("primary")]
    axes[1, 1].plot(monthly.target_month, monthly.MAE, "o-", label="MAE")
    axes[1, 1].plot(monthly.target_month, monthly.RMSE, "o-", label="RMSE")
    axes[1, 1].tick_params(axis="x", rotation=40)
    axes[1, 1].set(xlabel="Target month", ylabel="Error (µg/m³)", title="Primary errors by forecast month")
    axes[1, 1].legend()
    fig.suptitle(f"T09 persistence — {mode.upper()} validation (primary cohort)")
    fig.tight_layout(rect=(0, 0, 1, .96))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def execute_run(root, *, mode, reference_run_id=None, split_manifest="reports/splits_full/split_manifest.json", is_test=False):
    root = Path(root).resolve()
    if mode not in ("smoke", "full") or (is_test and not root.name.startswith("TEST_ONLY")):
        raise ValueError("Invalid mode/test-only project")
    preflight_start = perf_counter()
    config, baseline_config = read_json(root / "configs/default.json"), read_json(root / "configs/baseline.json")
    preprocessing_config = read_json(root / "configs/preprocessing.json")
    policy(config, baseline_config, preprocessing_config)
    train, all_validation, provenance = load_train_validation(root, split_manifest)
    anchor_path, anchor = freeze_validation_ids(root, all_validation, provenance)
    selected = all_validation if mode == "full" else all_validation.groupby("station", sort=True).head(baseline_config["smoke_rows_per_station"]).reset_index(drop=True)
    selected = selected.reset_index(drop=True)
    history, history_scope = load_validation_history(root, selected, provenance)
    code = {name: sha256(path) for name, path in source_files().items()}
    signature = {"baseline_config": baseline_config, "split_manifest_sha256": provenance["split_manifest_sha256"],
                 "anchor_sha256": sha256(anchor_path), "source_sha256": code,
                 "prediction_policy": preprocessing_config["prediction_postprocessing"],
                 "fallback_order": config["evaluation"]["baseline_fallback_order"]}
    logger = ExperimentLogger(project_root=root)
    task_id = "TEST_ONLY_T09" if is_test else "T09"
    check_budget(logger, mode, reference_run_id, signature, task_id)
    if selected.empty or not selected.is_primary.any():
        raise ValueError("Evaluation cohort is empty")
    counts = {"train_operational": len(train), "validation_operational": len(selected), "validation_primary": int(selected.is_primary.sum())}
    time_ranges = {name: {f"{col}_{op}": str(getattr(frame[col], op)()) for col in ("input_timestamp", "target_timestamp") for op in ("min", "max")}
                   for name, frame in (("train", train), ("validation", selected))}
    with logger.start_run(
        task_id=task_id, reference_run_id=reference_run_id, mode=mode, kind="baseline", model="persistence",
        objective="Xác định mốc MAE/RMSE/R² cho PM2.5 đúng t+1, cùng trạm, trên validation IDs cố định.",
        hypothesis="PM2.5(t) là mốc dự báo một giờ cần kiểm chứng; chưa yêu cầu Ridge/RF phải thắng.",
        change="Initial smoke execution" if mode == "smoke" else "Expand verified smoke protocol to full validation; smoke/full metrics are not directly comparable.",
        parameters={"signature": signature, "project_config": config, "configured_seed": config["seed"], "randomness_used": False},
        feature_set="PM2.5(t); bounded same-station history only on missing current value",
        preprocessing={"applied": False, "fallback_statistics": "train-origin medians only", "config": preprocessing_config},
        data={"provenance": provenance, "history_scope": history_scope, "validation_anchor": anchor},
        split={**config["split"], "evaluation": "validation", "headline_cohort": "primary"},
        time_ranges=time_ranges, sample_counts=counts, seed=None, budget=baseline_config["budget"], is_test=is_test, source="executed_script",
        notes="Protocol fixed before scoring. Smoke is execution-only; full primary is the headline. No test access; no prediction clipping.",
    ) as run:
        work = root / "artifacts/baseline_work" / run.run_id
        work.mkdir(parents=True, exist_ok=False)
        os.environ["MPLCONFIGDIR"] = str(work / "matplotlib")
        for name, path in source_files().items():
            run.log_artifact(path, name=f"source/{name}")
        run.log_artifact(anchor_path, name="data/validation_manifest.json")
        selected.loc[:, ["sample_id", "station", "input_timestamp", "target_timestamp", "is_primary"]].to_csv(
            work / "evaluation_ids.csv", index=False, encoding="utf-8", lineterminator="\n")
        run.log_artifact(work / "evaluation_ids.csv", name="data/evaluation_ids.csv")
        timings = {"preflight": perf_counter()-preflight_start}
        started = perf_counter()
        state = baseline.fit_persistence(train)
        timings["fallback_statistics_fit"] = perf_counter()-started
        write_json(work / "baseline_state.json", asdict(state))
        run.log_artifact(work / "baseline_state.json", name="model/baseline_state.json")
        started = perf_counter()
        predictions = baseline.predict_persistence(state, selected, history, max_history_age_hours=baseline_config["max_history_age_hours"])
        timings["predict"] = perf_counter()-started
        current = selected["PM2.5"].notna()
        np.testing.assert_allclose(predictions.loc[current, "y_pred"], selected.loc[current, "PM2.5"], rtol=1e-12, atol=1e-12)
        # Label values are attached only after predictions have been produced.
        predictions["y_true"] = selected.target_pm25.to_numpy()
        predictions["residual"] = predictions.y_pred-predictions.y_true
        predictions["abs_error"] = predictions.residual.abs()
        predictions["squared_error"] = predictions.residual**2
        predictions["run_id"] = run.run_id
        predictions["target_month"] = predictions.target_timestamp.dt.to_period("M").astype(str)
        started = perf_counter()
        scores = evaluate_predictions(predictions, selected.sample_id)
        timings["evaluate"] = perf_counter()-started
        for cohort, values in scores.items():
            run.log_metrics(values, split=f"validation_{cohort}")
        metric_table = pd.DataFrame([{"run_id": run.run_id, "mode": mode, "split": "validation", "cohort": k, **v} for k, v in scores.items()])
        fallback_rows = []
        for cohort, subset in (("primary", predictions.loc[predictions.is_primary]), ("operational", predictions)):
            for source, n in subset.prediction_source.value_counts().sort_index().items():
                fallback_rows.append({"cohort": cohort, "prediction_source": source, "samples": int(n), "fraction": int(n)/len(subset)})
        station_table, month_table = grouped_metrics(predictions, "station"), grouped_metrics(predictions, "target_month")
        outputs = {"predictions/validation.csv": predictions, "tables/metrics.csv": metric_table,
                   "tables/fallback.csv": pd.DataFrame(fallback_rows), "tables/station_metrics.csv": station_table,
                   "tables/month_metrics.csv": month_table,
                   "tables/largest_errors.csv": predictions.loc[predictions.is_primary].nlargest(20, "abs_error")}
        for name, frame in outputs.items():
            path = work / Path(name).name
            frame.to_csv(path, index=False, na_rep="NA", encoding="utf-8", lineterminator="\n")
            run.log_artifact(path, name=name)
        started = perf_counter()
        diagnostic_plot(predictions, station_table, month_table, work / "validation_errors.png", mode)
        run.log_artifact(work / "validation_errors.png", name="figures/validation_errors.png")
        timings["diagnostics_and_plot"] = perf_counter()-started
        run.log_metrics({"timing_seconds": timings, "test_csv_accessed": False, "official_full_result": mode == "full" and not is_test})
        primary, operational = scores["primary"], scores["operational"]
        notes = (f"{'TEST_ONLY fixture. ' if is_test else ''}{'SMOKE — execution check, not official research numbers.' if mode == 'smoke' else 'FULL — headline primary cohort.'}\n\n"
                 f"Primary N={primary['n_total']}, MAE={primary['MAE']:.6f}, RMSE={primary['RMSE']:.6f}, R²={primary['R2']}. "
                 f"Operational N={operational['n_total']}, MAE={operational['MAE']:.6f}, RMSE={operational['RMSE']:.6f}, R²={operational['R2']}.\n\n"
                 f"Fallback={operational['fallback_count']}/{operational['n_total']} ({operational['fallback_rate']:.4%}); "
                 f"coverage={operational['coverage']:.4%}; history limit <= {baseline_config['max_history_age_hours']}h, otherwise train medians. "
                 "Primary has no missing-current fallback; do not mix denominators. Numeric units µg/m³.\n\n"
                 "No randomness (actual seed null; project seed retained in config). No test, clipping, learned model or threshold tuning. "
                 "Compare T10 Ridge/RF A on identical primary validation IDs; improvement is a research question, not a required outcome.")
        run.finish_run(notes=notes, decision="T10: initial Ridge and Random Forest A on frozen IDs, same metrics/prediction policy; log all outcomes.")
    # Small, reviewable copies; full predictions and source stay in logger artifacts.
    report = root / "reports/baseline" / mode / run.run_id
    report.mkdir(parents=True, exist_ok=False)
    for name in ("metrics.csv", "fallback.csv", "station_metrics.csv", "month_metrics.csv", "largest_errors.csv"):
        shutil.copyfile(work / name, report / name)
    shutil.copyfile(run.directory / "notes.md", report / "notes.md")
    figure = root / "reports/figures/baseline" / f"{mode}_{run.run_id}_validation_errors.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(work / "validation_errors.png", figure)
    write_json(report / "run.json", {"run_id": run.run_id, "mode": mode, "status": "completed",
                                      "official": mode == "full" and not is_test, "directory": run.directory.relative_to(root).as_posix(),
                                      "config_sha256": sha256(run.directory / "config.json"),
                                      "metrics_sha256": sha256(run.directory / "metrics.json"), "source_sha256": code})
    print(f"{task_id} {mode}: run_id={run.run_id}; completed; official={mode == 'full' and not is_test}")
    print(metric_table[["cohort", "n_total", "MAE", "RMSE", "R2", "fallback_rate"]].to_string(index=False))
    return run.run_id


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--reference-run-id")
    parser.add_argument("--split-manifest", default="reports/splits_full/split_manifest.json")
    parser.add_argument("--test-only", action="store_true", help="Only accepted inside TEST_ONLY project fixtures")
    args = parser.parse_args()
    execute_run(Path(__file__).resolve().parents[1], mode=args.mode, reference_run_id=args.reference_run_id,
                split_manifest=args.split_manifest, is_test=args.test_only)


if __name__ == "__main__":
    main()
