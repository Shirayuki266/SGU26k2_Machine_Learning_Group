"""T10 fixed initial A models: smoke then one full/model, no test or tuning."""

import argparse
import csv
from pathlib import Path
import sys
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from beijing_air import initial_models, features, preprocessing, metrics, evaluation
from beijing_air.data import sha256
from beijing_air.eda import read_json, ids_digest
from beijing_air.experiment_logging import ExperimentLogger
from beijing_air.initial_models import (
    available_memory_mb, validate_design, load_initial_data, effective_pipeline,
    fitted_summary, prediction_frame,
)
from beijing_air.metrics import regression_metrics


def source_files():
    return {"initial_models.py": Path(initial_models.__file__), "features.py": Path(features.__file__),
            "preprocessing.py": Path(preprocessing.__file__), "metrics.py": Path(metrics.__file__),
            "evaluation.py": Path(evaluation.__file__), "run_initial_models.py": Path(__file__).resolve()}


def write_json(path, value):
    import json
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def baseline_reference(root, run_id, selected_validation):
    directory = root / "artifacts/experiments" / run_id
    config, metadata = read_json(directory / "config.json"), read_json(directory / "metadata.json")
    if config["model"] != "persistence" or config["mode"] != "full" or metadata["status"] != "completed":
        raise ValueError("Reference must be a completed full persistence run")
    path = directory / "artifacts/predictions/validation.csv"
    info = next(a for a in metadata["artifacts"] if a["path"].endswith("/predictions/validation.csv"))
    if sha256(path) != info["sha256"]:
        raise ValueError("Baseline reference predictions changed")
    predictions = pd.read_csv(path)
    predictions = predictions.loc[predictions.is_primary].set_index("sample_id")
    if not predictions.index.is_unique:
        raise ValueError("Duplicate baseline ID")
    matched = predictions.loc[selected_validation.sample_id]
    np.testing.assert_allclose(matched.y_true, selected_validation.target_pm25, rtol=1e-12, atol=1e-12)
    return {"run_id": run_id, "predictions_sha256": info["sha256"],
            "metrics": regression_metrics(matched.y_true, matched.y_pred)}


def check_budget(logger, task_id, model_name, mode, signature):
    records = []
    if logger.csv_path.exists():
        with logger.csv_path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if row["task_id"] == task_id and row["model"] == model_name:
                    config = read_json(logger.experiment_dir / row["config_path"])
                    records.append((row, config))
    for row, cfg in records:
        if row["mode"] == mode and row["status"] == "completed" and cfg["parameters"]["signature"] == signature:
            metadata = read_json(logger.experiment_dir / row["metadata_path"])
            for info in metadata["artifacts"]:
                path = (logger.experiment_dir / info["path"]).resolve()
                if not path.is_relative_to(logger.artifact_dir) or not path.is_file() or sha256(path) != info["sha256"]:
                    raise ValueError("Existing matching run artifact is missing/changed; inspect instead of refitting")
            return row["run_id"], None
    if mode == "full":
        if any(row["mode"] == "full" for row, _ in records):
            raise ValueError("Initial full/model budget already used; inspect existing artifacts, never erase history")
        smoke = next((row["run_id"] for row, cfg in reversed(records) if row["mode"] == "smoke"
                      and row["status"] == "completed" and cfg["parameters"]["signature"] == signature), None)
        if smoke is None:
            raise ValueError("Full requires a completed matching smoke for this model/config/data/code")
        return None, smoke
    return None, None


def execute_model(root, *, model_name, mode, is_test=False):
    root = Path(root).resolve()
    if mode not in ("smoke", "full") or (is_test and not root.name.startswith("TEST_ONLY")):
        raise ValueError("Invalid mode/test fixture project")
    started = perf_counter()
    config = read_json(root / "configs/default.json")
    design, prep = read_json(root / "configs/initial_models.json"), read_json(root / "configs/preprocessing.json")
    validate_design(design, prep)
    free_mb = available_memory_mb()
    if not is_test and free_mb is not None and free_mb < design["resources"]["minimum_free_memory_mb"]:
        raise MemoryError("Insufficient free RAM for the agreed full dataset; no automatic subsampling")
    selected, x, provenance, anchor, anchor_sha = load_initial_data(root, mode=mode, design=design)
    reference = baseline_reference(root, design["baseline_reference_run_id"], selected["validation"])
    pipeline, effective = effective_pipeline(model_name, config, design, prep)
    code = {name: sha256(path) for name, path in source_files().items()}
    signature = {"design": design, "model": model_name, "effective_model_parameters": pipeline.named_steps["model"].get_params(),
                 "features": config["features"]["A"], "preprocessing": prep, "source_sha256": code,
                 "provenance": provenance, "anchor_sha256": anchor_sha,
                 "baseline_predictions_sha256": reference["predictions_sha256"]}
    logger = ExperimentLogger(project_root=root)
    task_id = "TEST_ONLY_T10" if is_test else "T10"
    existing, smoke = check_budget(logger, task_id, model_name, mode, signature)
    if existing:
        print(f"Verified matching existing {model_name}/{mode} run {existing}; no new fit/run")
        return existing
    membership = {name: {"rows": len(frame), "ordered_ids_sha256": ids_digest(frame.sample_id),
                         "first_target": str(frame.target_timestamp.min()), "last_target": str(frame.target_timestamp.max())}
                  for name, frame in selected.items()}
    if mode == "full" and membership["validation"]["ordered_ids_sha256"] != anchor["cohorts"]["primary"]["ordered_sample_ids_sha256"]:
        raise ValueError("Full validation is not the frozen primary cohort")
    preflight_seconds = perf_counter()-started
    actual_seed = design["models"][model_name].get("random_state")
    with logger.start_run(
        task_id=task_id, reference_run_id=reference["run_id"], mode=mode, kind="train", model=model_name,
        objective="Benchmark initial A models against persistence on identical primary validation IDs.",
        hypothesis="Current measurements/weather/calendar may improve persistence, but no model is required to win.",
        change="Initial fixed configuration; RF bounded for resources, not selected from validation scores.",
        parameters={"signature": signature, "effective_project_config": effective, "smoke_reference_run_id": smoke,
                    "configured_seed": config["seed"], "weights_saved": False},
        feature_set="A", preprocessing=prep,
        data={"provenance": provenance, "validation_anchor": anchor, "selected_membership": membership,
              "selection": "all primary IDs" if mode == "full" else design["smoke"]},
        split={**config["split"], "training": "train primary only", "evaluation": "validation primary only"},
        sample_counts={name: len(frame) for name, frame in selected.items()},
        seed=actual_seed, budget=design["budget"], is_test=is_test, source="executed_script",
        notes="Fixed before metrics. Smoke is execution-only; full uses every primary train/validation row. No test, clipping or tuning.",
    ) as run:
        work = root / "artifacts/initial_models_work" / run.run_id
        work.mkdir(parents=True, exist_ok=False)
        for name, path in source_files().items():
            run.log_artifact(path, name=f"source/{name}")
        write_json(work / "membership.json", {"selected": membership, "anchor": anchor})
        run.log_artifact(work / "membership.json", name="data/membership.json")
        for name in ("train", "validation"):
            if x[name].index.tolist() != selected[name].sample_id.tolist():
                raise ValueError("Feature/target IDs not aligned")
        timings = {"preflight_before_run": preflight_seconds}
        with threadpool_limits(limits=design["resources"]["blas_threads"]):
            clock = perf_counter()
            pipeline.fit(x["train"], selected["train"].set_index("sample_id").target_pm25)
            timings["fit_pipeline"] = perf_counter()-clock
            summary = fitted_summary(pipeline, model_name)
            before_predict = summary["fitted_object_hash"]
            scores = {}
            for name in ("train", "validation"):
                clock = perf_counter()
                prediction = pipeline.predict(x[name])
                timings[f"predict_{name}"] = perf_counter()-clock
                frame = prediction_frame(selected[name], prediction, run.run_id, model_name)
                scores[name] = regression_metrics(frame.y_true, frame.y_pred)
                scores[name]["negative_predictions"] = int(frame.y_pred.lt(0).sum())
                run.log_metrics(scores[name], split=f"{name}_primary")
                path = work / f"{name}.csv.gz"
                frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n",
                             compression={"method": "gzip", "compresslevel": 6, "mtime": 0})
                run.log_artifact(path, name=f"predictions/{name}.csv.gz")
            if joblib.hash(pipeline) != before_predict:
                raise ValueError("Prediction changed fitted pipeline state")
        write_json(work / "fitted_pipeline_state.json", summary)
        run.log_artifact(work / "fitted_pipeline_state.json", name="model/fitted_pipeline_state.json")
        run.log_metrics({"timing_seconds": timings, "available_memory_mb_before_data": free_mb,
                         "official_full_result": mode == "full" and not is_test, "test_csv_accessed": False,
                         "validation_baseline": reference["metrics"],
                         "generalization_gap_MAE": scores["validation"]["MAE"]-scores["train"]["MAE"],
                         "validation_delta_MAE_vs_persistence": scores["validation"]["MAE"]-reference["metrics"]["MAE"]})
        write_json(work / "metrics_table.json", {"model": model_name, "mode": mode, "run_id": run.run_id,
                                                "train": scores["train"], "validation": scores["validation"], "timing_seconds": timings})
        run.log_artifact(work / "metrics_table.json", name="tables/metrics.json")
        notes = (f"{'TEST_ONLY ' if is_test else ''}{mode.upper()} {model_name}, feature A, primary only. "
                 f"Train N={len(selected['train'])}, validation N={len(selected['validation'])}. "
                 f"MAE train={scores['train']['MAE']:.6f}, validation={scores['validation']['MAE']:.6f}; "
                 f"validation RMSE={scores['validation']['RMSE']:.6f}, R2={scores['validation']['R2']}. "
                 f"Persistence MAE on exactly these IDs={reference['metrics']['MAE']:.6f}; "
                 f"delta={scores['validation']['MAE']-reference['metrics']['MAE']:.6f}. "
                 "Train error is in-sample, not CV. No clipping, test or tuning. "
                 "Weights intentionally not saved; fitted state is a summary, not a deployable model. "
                 "Evaluate gap/cost before proposing future T11/T12; no requirement to beat persistence.")
        run.finish_run(notes=notes, decision="Report initial outcome including worse scores; future tuning/ablation only when explicitly assigned.")
    report = root / "reports/initial_models" / mode / model_name
    report.mkdir(parents=True, exist_ok=False)
    write_json(report / "run.json", {"run_id": run.run_id, "mode": mode, "model": model_name,
                                     "official": mode == "full" and not is_test, "weights_saved": False})
    (report / "notes.md").write_text(notes+"\n", encoding="utf-8", newline="\n")
    print(f"{task_id} {mode} {model_name}: completed {run.run_id}; train={membership['train']['rows']}, validation={membership['validation']['rows']}")
    print({"train": scores["train"], "validation": scores["validation"], "timing": timings})
    return run.run_id


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--model", choices=["ridge", "random_forest", "all"], default="all")
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args()
    for model in (["ridge", "random_forest"] if args.model == "all" else [args.model]):
        execute_model(root, model_name=model, mode=args.mode, is_test=args.test_only)


if __name__ == "__main__":
    main()
