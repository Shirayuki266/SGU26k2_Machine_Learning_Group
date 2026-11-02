"""T11 bounded Ridge CV: train-only search, then one selected validation refit."""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import sys
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from beijing_air import tuning, temporal_cv, initial_models, features, preprocessing, metrics, eda, samples, evaluation
from beijing_air.data import sha256
from beijing_air.eda import read_json, ids_digest
from beijing_air.experiment_logging import ExperimentLogger
from beijing_air.initial_models import available_memory_mb, fitted_summary, prediction_frame, load_initial_data
from beijing_air.metrics import regression_metrics
from beijing_air.temporal_cv import expanding_folds, membership
from beijing_air.tuning import validate_search, load_cv_training, ridge_pipeline, aggregate_folds, choose_candidate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_initial_models import write_json


class CandidateFailed(RuntimeError):
    pass


def source_files():
    modules = (tuning, temporal_cv, initial_models, features, preprocessing, metrics, eda, samples, evaluation)
    result = {Path(m.__file__).name: Path(m.__file__) for m in modules}
    result["run_tuning.py"] = Path(__file__).resolve()
    result["run_initial_models.py"] = Path(__file__).with_name("run_initial_models.py")
    return result


def verified_tree(root, run_id):
    directory = root / "artifacts/experiments" / run_id
    cfg, meta = read_json(directory / "config.json"), read_json(directory / "metadata.json")
    for artifact in meta["artifacts"]:
        path = (root / "experiments" / artifact["path"]).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or sha256(path) != artifact["sha256"]:
            raise ValueError("Recorded run artifact missing/changed; inspect instead of refitting")
    return cfg, meta


def search_guard(root, logger, task, mode, signature):
    rows = []
    if logger.csv_path.exists():
        with logger.csv_path.open(encoding="utf-8", newline="") as stream:
            rows = [r for r in csv.DictReader(stream) if r["task_id"] == task and r["kind"] == "tuning"
                    and read_json(root / "experiments" / r["config_path"])["parameters"].get("stage") == "search"]
    for row in rows:
        cfg = read_json(root / "experiments" / row["config_path"])
        if row["mode"] == mode and row["status"] == "completed" and cfg["parameters"]["signature"] == signature:
            verified_tree(root, row["run_id"])
            result = read_json(root / "artifacts/experiments" / row["run_id"] / "artifacts/search/results.json")
            for candidate in result["candidates"]:
                verified_tree(root, candidate["run_id"])
                for fold_id in candidate["fold_run_ids"]:
                    verified_tree(root, fold_id)
            if result["refit_run_id"]:
                verified_tree(root, result["refit_run_id"])
            return row["run_id"], None
    if mode == "full":
        if any(r["mode"] == "full" for r in rows):
            raise ValueError("T11 full-search budget already used, including failures; no automatic retries")
        smoke = next((r["run_id"] for r in reversed(rows) if r["mode"] == "smoke" and r["status"] == "completed"
                      and read_json(root / "experiments" / r["config_path"])["parameters"]["signature"] == signature), None)
        if not smoke:
            raise ValueError("Full T11 requires a completed matching smoke")
        return None, smoke
    return None, None


def save_artifact(run, work, value, filename, name):
    path = work / filename
    write_json(path, value)
    run.log_artifact(path, name=name)


def save_predictions(run, work, frame, partition):
    path = work / f"{partition}.csv.gz"
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n",
                 compression={"method": "gzip", "compresslevel": 6, "mtime": 0})
    run.log_artifact(path, name=f"predictions/{partition}.csv.gz")


def evaluate_fold(pipe, x, data, fit_positions, eval_positions):
    """Only the fit partition is passed to fit; every caller builds a fresh pipe."""
    clock = perf_counter()
    pipe.fit(x.iloc[fit_positions], data.iloc[fit_positions].set_index("sample_id").target_pm25)
    fit_seconds = perf_counter()-clock
    state = fitted_summary(pipe, "ridge")
    clock = perf_counter()
    prediction = pipe.predict(x.iloc[eval_positions])
    timing = {"fit_pipeline": fit_seconds, "predict_evaluation": perf_counter()-clock}
    if joblib.hash(pipe) != state["fitted_object_hash"]:
        raise ValueError("Prediction changed fitted state")
    return prediction, state, timing


def selected_refit(root, logger, parent, selected, common, config, prep, train_membership):
    # This is the first call that opens project validation samples in this search.
    initial_design = read_json(root / "configs/initial_models.json")
    data, x, provenance, anchor, _ = load_initial_data(root, mode="full", design=initial_design)
    if membership(data["train"]) != train_membership:
        raise ValueError("Refit train differs from CV train")
    parameters = {"stage": "selected_refit", "alpha": selected["alpha"], "selected_candidate_run_id": selected["run_id"],
                  "selection_locked_before_validation": True, "actual_model_parameters": ridge_pipeline(selected["alpha"], config, prep).named_steps["model"].get_params()}
    with logger.start_run(**common, parent_run_id=parent.run_id, kind="train", mode="full",
                          parameters=parameters, data={"provenance": provenance, "validation_anchor": anchor},
                          split={"fit": "all primary train", "evaluation": "frozen primary validation", "test_locked": True},
                          sample_counts={s: len(d) for s, d in data.items()}) as run:
        work = root / "artifacts/tuning_work" / run.run_id
        work.mkdir(parents=True, exist_ok=False)
        pipe = ridge_pipeline(selected["alpha"], config, prep)
        clock = perf_counter()
        pipe.fit(x["train"], data["train"].set_index("sample_id").target_pm25)
        times = {"fit_pipeline": perf_counter()-clock}
        state = fitted_summary(pipe, "ridge")
        for partition in ("train", "validation"):
            clock = perf_counter()
            pred = prediction_frame(data[partition], pipe.predict(x[partition]), run.run_id, "ridge")
            times[f"predict_{partition}"] = perf_counter()-clock
            score = regression_metrics(pred.y_true, pred.y_pred)
            score["negative_predictions"] = int(pred.y_pred.lt(0).sum())
            run.log_metrics(score, split=f"{partition}_primary")
            save_predictions(run, work, pred, partition)
        if joblib.hash(pipe) != state["fitted_object_hash"]:
            raise ValueError("Holdout prediction mutated fitted state")
        save_artifact(run, work, state, "fitted_pipeline_state.json", "model/fitted_pipeline_state.json")
        run.log_metrics({"timing_seconds": times, "test_csv_accessed": False, "selection_source": "train_cv_only"})
        run.finish_run(notes=f"Selected only by pooled train CV MAE: alpha={selected['alpha']}; one refit on full primary train, validation once. No clipping, test or serialized weights.")
    return run.run_id


def execute_search(root, *, mode, is_test=False):
    root = Path(root).resolve()
    if mode not in ("smoke", "full") or (is_test and not root.name.startswith("TEST_ONLY")):
        raise ValueError("Invalid mode/test fixture")
    config, design, prep = (read_json(root / "configs" / f"{n}.json") for n in ("default", "tuning", "preprocessing"))
    validate_search(design, prep)
    free_mb = available_memory_mb()
    if not is_test and free_mb is not None and free_mb < design["resources"]["minimum_free_memory_mb"]:
        raise MemoryError("Insufficient RAM; no automatic subsampling or budget change")
    data, x, provenance = load_cv_training(root)
    folds = expanding_folds(data, config)
    reference_dir = root / "artifacts/experiments" / design["reference_run_id"]
    # Config/metadata only: historical validation predictions are unnecessary for CV.
    ref_cfg, ref_meta = read_json(reference_dir / "config.json"), read_json(reference_dir / "metadata.json")
    if (ref_cfg["model"] != "ridge" or ref_cfg["mode"] != "full" or ref_cfg["feature_set"] != "A"
            or ref_meta["status"] != "completed" or ref_cfg["data"]["provenance"]["t05_snapshot_id"] != provenance["t05_snapshot_id"]
            or ref_cfg["preprocessing"] != prep or ref_cfg["parameters"]["signature"]["effective_model_parameters"]["alpha"] != 1.0
            or ref_cfg["parameters"]["signature"]["features"] != config["features"]["A"]):
        raise ValueError("Expected matching completed T10 Ridge alpha1/A reference")
    code = {name: sha256(path) for name, path in source_files().items()}
    signature = {"design": design, "temporal_cv": config["temporal_cv"], "split": config["split"],
                 "features": config["features"]["A"], "preprocessing": prep, "provenance": provenance,
                 "reference_config_sha256": sha256(root / "artifacts/experiments" / design["reference_run_id"] / "config.json"),
                 "source_sha256": code}
    logger = ExperimentLogger(project_root=root)
    task = "TEST_ONLY_T11" if is_test else "T11"
    existing, smoke = search_guard(root, logger, task, mode, signature)
    if existing:
        print(f"Verified completed matching search {existing}; no new fits/runs", flush=True)
        return existing
    common = {"task_id": task, "reference_run_id": design["reference_run_id"], "model": "ridge", "feature_set": "A",
              "preprocessing": prep, "seed": None, "is_test": is_test, "source": "executed_script",
              "objective": "Select Ridge alpha by purged temporal CV within train; evaluate validation only after selection.",
              "hypothesis": design["hypothesis"], "budget": design["budget"]}
    with logger.start_run(**common, mode=mode, kind="tuning", parameters={"stage": "search", "signature": signature, "smoke_reference_run_id": smoke},
                          data={"provenance": provenance, "train_membership": membership(data)}, split=config["temporal_cv"]) as parent:
        work = root / "artifacts/tuning_work" / parent.run_id
        work.mkdir(parents=True, exist_ok=False)
        for name, path in source_files().items():
            parent.log_artifact(path, name=f"source/{name}")
        save_artifact(parent, work, [f.audit for f in folds], "folds.json", "data/folds.json")
        records = []
        alphas = design["alphas"] if mode == "full" else design["smoke"]["alphas"]
        with threadpool_limits(limits=design["resources"]["blas_threads"]):
            for alpha in alphas:
                candidate = logger.start_run(**common, parent_run_id=parent.run_id, mode=mode, kind="tuning", parameters={"stage": "candidate", "alpha": alpha})
                record = {"run_id": candidate.run_id, "alpha": alpha, "status": "running", "fold_run_ids": [], "failed_fold_run_ids": []}
                predictions, total_times = [], {"fit_pipeline": 0., "predict_evaluation": 0.}
                try:
                    with candidate:
                        for fold in folds:
                            fit, evaluation_positions = fold.fit, fold.evaluation
                            if mode == "smoke":
                                fit = data.iloc[fit].groupby("station", sort=True).head(design["smoke"]["train_rows_per_station"]).index.to_numpy()
                                evaluation_positions = data.iloc[evaluation_positions].groupby("station", sort=True).head(design["smoke"]["evaluation_rows_per_station"]).index.to_numpy()
                            fold_run = logger.start_run(**common, parent_run_id=candidate.run_id, fold_id=fold.fold_id, mode=mode, kind="tuning",
                                                        parameters={"stage": "fold", "alpha": alpha, "source_parent_run_id": parent.run_id,
                                                                    "actual_model_parameters": ridge_pipeline(alpha, config, prep).named_steps["model"].get_params()},
                                                        data={"fit": membership(data.iloc[fit]), "evaluation": membership(data.iloc[evaluation_positions])},
                                                        split=fold.audit, sample_counts={"fit": len(fit), "evaluation": len(evaluation_positions)})
                            record["fold_run_ids"].append(fold_run.run_id)
                            try:
                                with fold_run:
                                    prediction, state, times = evaluate_fold(ridge_pipeline(alpha, config, prep), x, data, fit, evaluation_positions)
                                    pred = prediction_frame(data.iloc[evaluation_positions], prediction, fold_run.run_id, "ridge")
                                    pred["fold_id"], pred["alpha"], pred["candidate_run_id"] = fold.fold_id, alpha, candidate.run_id
                                    score = regression_metrics(pred.y_true, pred.y_pred)
                                    score["negative_predictions"] = int(pred.y_pred.lt(0).sum())
                                    fold_run.log_metrics(score, split="evaluation")
                                    fold_run.log_metrics({"timing_seconds": times, "validation_csv_accessed": False, "test_csv_accessed": False})
                                    fold_work = root / "artifacts/tuning_work" / fold_run.run_id
                                    fold_work.mkdir(parents=True, exist_ok=False)
                                    save_predictions(fold_run, fold_work, pred, "evaluation")
                                    save_artifact(fold_run, fold_work, state, "fitted_pipeline_state.json", "model/fitted_pipeline_state.json")
                                    predictions.append(pred)
                                    for key in times:
                                        total_times[key] += times[key]
                                    fold_run.finish_run(notes=f"alpha={alpha}, fold={fold.fold_id}, fresh T08 pipeline fit on past only; strict purged boundary, no holdout.")
                                print(f"{task} {mode} alpha={alpha} fold={fold.fold_id} completed {fold_run.run_id}", flush=True)
                            except Exception as error:
                                record["failed_fold_run_ids"].append(fold_run.run_id)
                                print(f"FAILED alpha={alpha} fold={fold.fold_id}: {type(error).__name__}: {error}; retained {fold_run.run_id}", flush=True)
                        candidate.log_metrics({"fold_run_ids": record["fold_run_ids"], "failed_fold_run_ids": record["failed_fold_run_ids"], "timing_seconds_successful_folds": total_times})
                        if record["failed_fold_run_ids"]:
                            raise CandidateFailed(f"Candidate alpha={alpha} has failed folds {record['failed_fold_run_ids']}; excluded, no retries")
                        record["summary"] = aggregate_folds(predictions)
                        candidate.log_metrics(record["summary"])
                        record["status"] = "completed"
                        candidate.finish_run(notes="Three folds completed. Rank by pooled MAE, report unweighted fold mean/std ddof0 separately; never rank by validation.")
                except CandidateFailed:
                    record["status"] = "failed"
                records.append(record)
            selected = choose_candidate(records, design["selection"]["tie_tolerance"])
            locked = {"selected_candidate_run_id": selected["run_id"], "alpha": selected["alpha"],
                      "selection_metric": "pooled_MAE", "selected_score": selected["summary"]["pooled"]["MAE"],
                      "selection_locked_before_validation": True, "locked_at": datetime.now(timezone.utc).isoformat()}
            # Persist the decision BEFORE any validation data are read or refit starts.
            save_artifact(parent, work, {"candidates": records, "selection": locked}, "selection.json", "search/selection.json")
            parent.log_metrics({"selection": locked, "attempted_candidates": len(records), "attempted_cv_fits": sum(len(c["fold_run_ids"]) for c in records),
                                "failed_candidates": sum(c["status"] == "failed" for c in records), "available_memory_mb_before_data": free_mb})
            refit_id = selected_refit(root, logger, parent, selected, common, config, prep, membership(data)) if mode == "full" else None
        result = {"mode": mode, "parent_run_id": parent.run_id, "candidates": records, "selection": locked,
                  "refit_run_id": refit_id, "test_csv_accessed": False, "official_full_search": mode == "full" and not is_test}
        save_artifact(parent, work, result, "results.json", "search/results.json")
        parent.finish_run(notes=f"{mode} bounded Ridge A search; selected alpha={selected['alpha']} only by train CV. Refit={refit_id}. All failures retained. Smoke is not official; no test/RF tuning/T12/weights.")
    report = root / "reports/tuning" / mode
    report.mkdir(parents=True, exist_ok=True)
    write_json(report / "run.json", {"parent_run_id": parent.run_id, "refit_run_id": refit_id})
    print(f"COMPLETED {task}/{mode} parent={parent.run_id}, alpha={selected['alpha']}, refit={refit_id}", flush=True)
    return parent.run_id


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args()
    execute_search(Path(__file__).resolve().parents[1], mode=args.mode, is_test=args.test_only)


if __name__ == "__main__":
    main()
