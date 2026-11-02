"""T12: nine grouped-selector CV fits, then fixed-parameter B/C validation."""

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

from beijing_air import ablation, feature_selection, features, preprocessing, evaluation, data as data_module, temporal_cv, tuning, initial_models, eda, samples, metrics
from beijing_air.ablation import validate_ablation, load_train_B, load_validation_B, choose_k, choose_deployment
from beijing_air.data import sha256
from beijing_air.eda import read_json
from beijing_air.experiment_logging import ExperimentLogger
from beijing_air.feature_selection import make_ablation_pipeline, selection_state
from beijing_air.initial_models import available_memory_mb, prediction_frame
from beijing_air.metrics import regression_metrics
from beijing_air.temporal_cv import expanding_folds, membership
from beijing_air.tuning import aggregate_folds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_initial_models import write_json
from run_tuning import save_artifact, save_predictions, verified_tree, CandidateFailed


def source_files():
    modules = (ablation, feature_selection, features, preprocessing, evaluation, data_module, temporal_cv, tuning, initial_models, eda, samples, metrics)
    files = {Path(m.__file__).name: Path(m.__file__) for m in modules}
    for name in ("run_ablation.py", "run_tuning.py", "run_initial_models.py"):
        files[name] = Path(__file__).with_name(name)
    return files


def guard(root, logger, task, mode, signature):
    records = []
    if logger.csv_path.exists():
        with logger.csv_path.open(encoding="utf-8", newline="") as stream:
            records = [(r, read_json(root / "experiments" / r["config_path"])) for r in csv.DictReader(stream) if r["task_id"] == task]
    parents = [(r, c) for r, c in records if c["parameters"]["stage"] == "search"]
    for row, cfg in parents:
        if row["mode"] == mode and row["status"] == "completed" and cfg["parameters"]["signature"] == signature:
            for r, _ in records: verified_tree(root, r["run_id"])
            print(f"Verified matching T12 {mode} {row['run_id']}; no new fits", flush=True)
            return row["run_id"], None
    if mode == "full":
        if any(r["mode"] == "full" for r, _ in parents):
            raise ValueError("T12 full budget already used, including failures; no automatic retries")
        smoke = next((r["run_id"] for r, c in reversed(parents) if r["mode"] == "smoke" and r["status"] == "completed" and c["parameters"]["signature"] == signature), None)
        if not smoke: raise ValueError("Full requires a completed matching T12 smoke")
        return None, smoke
    return None, None


def fit_predict(pipe, xfit, yfit, xeval):
    clock = perf_counter()
    pipe.fit(xfit, yfit)
    timing = {"fit_pipeline": perf_counter()-clock}
    state = selection_state(pipe)
    clock = perf_counter()
    prediction = pipe.predict(xeval)
    timing["predict_evaluation"] = perf_counter()-clock
    if joblib.hash(pipe) != state["fitted_object_hash"]: raise ValueError("Predict mutated fitted pipeline")
    return prediction, state, timing


def historical_prediction(root, run_id):
    cfg, metadata = verified_tree(root, run_id)
    info = next(a for a in metadata["artifacts"] if "/predictions/validation.csv" in a["path"])
    pred = pd.read_csv(root / "experiments" / info["path"])
    return cfg, pred.loc[pred.is_primary].copy()


def final_evaluations(root, parent, common, design, train, xtrain, selected, config, prep, logger):
    # Selection is already a persisted artifact before this first validation loader.
    validation, xval, validation_provenance = load_validation_B(root)
    outputs, comparison, states = {}, [], {}
    for variant, run_id in {"A": design["reference_A_run_id"], **design["historical_comparators"]}.items():
        cfg, pred = historical_prediction(root, run_id)
        if pred.sample_id.tolist() != validation.sample_id.tolist(): raise ValueError("Historical comparator IDs differ")
        np.testing.assert_allclose(pred.y_true, validation.target_pm25, rtol=1e-12, atol=1e-12)
        comparison.append({"variant": variant, "run_id": run_id, **regression_metrics(pred.y_true, pred.y_pred),
                           "negative_predictions": int(pred.y_pred.lt(0).sum()), "source": "existing_actual_run"})
    for variant in ("B", "C"):
        params = {"stage": "validation", "alpha": design["alpha"], "k_groups": selected["k_groups"] if variant == "C" else None,
                  "selected_candidate_run_id": selected["run_id"], "selection_locked_before_validation": True}
        with logger.start_run(**common, parent_run_id=parent.run_id, feature_set=variant, mode="full", kind="ablation", parameters=params,
                              data={"train": membership(train), "validation": membership(validation), "validation_provenance": validation_provenance},
                              split={"fit": "all primary train", "evaluation": "frozen primary validation", "test_locked": True}) as run:
            work = root / "artifacts/ablation_work" / run.run_id
            work.mkdir(parents=True, exist_ok=False)
            pipe = make_ablation_pipeline(variant, config, prep, alpha=design["alpha"], k_groups=params["k_groups"])
            values, state, times = fit_predict(pipe, xtrain, train.set_index("sample_id").target_pm25, xval)
            pred = prediction_frame(validation, values, run.run_id, "ridge")
            score = regression_metrics(pred.y_true, pred.y_pred)
            score["negative_predictions"] = int(pred.y_pred.lt(0).sum())
            run.log_metrics(score, split="validation_primary")
            # Train metrics are in-sample; persist predictions so they are recomputable.
            clock = perf_counter()
            train_pred = prediction_frame(train, pipe.predict(xtrain), run.run_id, "ridge")
            times["predict_train"] = perf_counter()-clock
            train_score = regression_metrics(train_pred.y_true, train_pred.y_pred)
            train_score["negative_predictions"] = int(train_pred.y_pred.lt(0).sum())
            run.log_metrics(train_score, split="train_primary")
            if joblib.hash(pipe) != state["fitted_object_hash"]: raise ValueError("Train prediction mutated state")
            run.log_metrics({"timing_seconds": times, "raw_kept_groups": len(state["kept_groups"]), "model_dimensions": state["model_dimensions"],
                             "test_csv_accessed": False, "generalization_gap_MAE": score["MAE"]-train_score["MAE"]})
            save_predictions(run, work, pred, "validation")
            save_predictions(run, work, train_pred, "train")
            save_artifact(run, work, state, "selection_state.json", "model/selection_state.json")
            run.finish_run(notes=f"Final {variant}, same Ridge alpha={design['alpha']}, no extra parameter tuning; C k chosen only by train CV. No clipping/test/serialized weights.")
            outputs[variant], states[variant] = run.run_id, state
            comparison.append({"variant": variant, "run_id": run.run_id, **score, "source": "executed_T12"})
        print(f"T12 final {variant} completed {outputs[variant]}: {score}", flush=True)
    winner = choose_deployment(comparison, design)
    winner_cfg = read_json(root / "artifacts/experiments" / winner["run_id"] / "config.json")
    parameters = (states[winner["variant"]]["parameters"] if winner["variant"] in states else
                  winner_cfg["parameters"].get("actual_model_parameters", winner_cfg["parameters"].get("signature", {}).get("effective_model_parameters", winner_cfg["parameters"])))
    feature_set = winner["variant"] if winner["variant"] in ("A", "B", "C") else ("A" if winner["variant"] == "random_forest_A" else "persistence_inputs")
    frozen = {"schema_version": "t12-frozen-v1", "status": "locked_recipe_for_future_refit", "locked_at": datetime.now(timezone.utc).isoformat(),
              "parent_run_id": parent.run_id, "selected_run_id": winner["run_id"], "selected_variant": winner["variant"],
              "selection": design["selection"], "validation_results": comparison,
              "data": {"train": membership(train), "validation": membership(validation), "provenance": validation_provenance, "horizon_hours": 1},
              "features": {"feature_set": feature_set, "definitions": config["features"],
                           "selector": {**design["selector"], "selected_k_groups": selected["k_groups"]} if feature_set == "C" else None,
                           "fitted_train_state": states.get(winner["variant"])},
              "preprocessing": winner_cfg["preprocessing"], "model": {"name": winner_cfg["model"], "parameters": parameters, "seed": winner_cfg["seed"]},
              "postprocessing": prep["prediction_postprocessing"], "refit_policy": design["final_refit_policy"],
              "selector_refit_on_train_validation_if_C": feature_set == "C", "test_locked": True, "test_evaluated": False,
              "weights_artifact": None, "deployment_ready_weights": False}
    return outputs, comparison, frozen


def execute_ablation(root, *, mode, is_test=False):
    root = Path(root).resolve()
    if mode not in ("smoke", "full") or (is_test and not root.name.startswith("TEST_ONLY")): raise ValueError("Invalid mode/test root")
    config, design, prep = (read_json(root / "configs" / f"{n}.json") for n in ("default", "ablation", "preprocessing"))
    validate_ablation(design, prep)
    memory = available_memory_mb()
    if not is_test and memory is not None and memory < design["resources"]["minimum_free_memory_mb"]: raise MemoryError("Insufficient RAM; no automatic subsampling")
    train, x, provenance = load_train_B(root)
    folds = expanding_folds(train, config)
    ref_path = root / "artifacts/experiments" / design["reference_A_run_id"]
    reference, ref_meta = read_json(ref_path / "config.json"), read_json(ref_path / "metadata.json")
    if (reference["model"] != "ridge" or reference["feature_set"] != "A" or reference["parameters"]["alpha"] != design["alpha"]
            or reference["preprocessing"] != prep or ref_meta["status"] != "completed"
            or reference["data"]["provenance"]["t05_snapshot_id"] != provenance["train_provenance"]["t05_snapshot_id"]):
        raise ValueError("Reference must be matching actual T11 Ridge A")
    if not is_test:
        t11 = read_json(root / "artifacts/experiments" / design["t11_search_run_id"] / "artifacts/search/results.json")
        if (t11["refit_run_id"] != design["reference_A_run_id"] or t11["selection"]["alpha"] != design["alpha"]
                or reference["parent_run_id"] != design["t11_search_run_id"]):
            raise ValueError("A must be the recorded T11 CV-selected refit")
    signature = {"design": design, "provenance": provenance, "temporal_cv": config["temporal_cv"], "features": config["features"],
                 "preprocessing": prep, "reference_config_sha256": sha256(ref_path / "config.json"),
                 "source_sha256": {n: sha256(p) for n, p in source_files().items()}}
    logger = ExperimentLogger(project_root=root)
    task = "TEST_ONLY_T12" if is_test else "T12"
    existing, smoke = guard(root, logger, task, mode, signature)
    if existing: return existing
    common = {"task_id": task, "reference_run_id": design["reference_A_run_id"], "model": "ridge", "seed": None,
              "is_test": is_test, "source": "executed_script", "preprocessing": prep, "budget": design["budget"],
              "objective": "Fixed-parameter A/B ablation and train-CV grouped B-to-C selection; freeze deployment by validation.", "hypothesis": design["hypothesis"]}
    with logger.start_run(**common, mode=mode, kind="feature_selection", feature_set="C", parameters={"stage": "search", "signature": signature, "smoke_reference_run_id": smoke},
                          data={"provenance": provenance, "train": membership(train)}, split=config["temporal_cv"]) as parent:
        work = root / "artifacts/ablation_work" / parent.run_id
        work.mkdir(parents=True, exist_ok=False)
        for name, path in source_files().items(): parent.log_artifact(path, name=f"source/{name}")
        save_artifact(parent, work, [f.audit for f in folds], "folds.json", "data/folds.json")
        records = []
        with threadpool_limits(limits=1):
            for k in (design["selector"]["k_groups"] if mode == "full" else design["smoke"]["k_groups"]):
                candidate = logger.start_run(**common, parent_run_id=parent.run_id, mode=mode, kind="feature_selection", feature_set="C", parameters={"stage": "candidate", "k_groups": k})
                record = {"run_id": candidate.run_id, "k_groups": k, "status": "running", "fold_run_ids": [], "failed_fold_run_ids": []}
                predictions = []
                try:
                    with candidate:
                        for fold in folds:
                            fit, ev = fold.fit, fold.evaluation
                            if mode == "smoke":
                                fit = train.iloc[fit].groupby("station", sort=True).head(design["smoke"]["train_rows_per_station"]).index.to_numpy()
                                ev = train.iloc[ev].groupby("station", sort=True).head(design["smoke"]["evaluation_rows_per_station"]).index.to_numpy()
                            child = logger.start_run(**common, parent_run_id=candidate.run_id, fold_id=fold.fold_id, mode=mode, kind="feature_selection", feature_set="C",
                                                     parameters={"stage": "fold", "k_groups": k, "source_parent_run_id": parent.run_id},
                                                     data={"fit": membership(train.iloc[fit]), "evaluation": membership(train.iloc[ev])}, split=fold.audit)
                            record["fold_run_ids"].append(child.run_id)
                            try:
                                with child:
                                    values, state, times = fit_predict(make_ablation_pipeline("C", config, prep, alpha=design["alpha"], k_groups=k), x.iloc[fit], train.iloc[fit].set_index("sample_id").target_pm25, x.iloc[ev])
                                    pred = prediction_frame(train.iloc[ev], values, child.run_id, "ridge")
                                    pred["fold_id"], pred["k_groups"] = fold.fold_id, k
                                    child.log_metrics(regression_metrics(pred.y_true, pred.y_pred), split="evaluation")
                                    child.log_metrics({"timing_seconds": times, "kept_groups": k, "model_dimensions": state["model_dimensions"], "validation_csv_accessed": False, "test_csv_accessed": False})
                                    cw = root / "artifacts/ablation_work" / child.run_id
                                    cw.mkdir(parents=True, exist_ok=False)
                                    save_predictions(child, cw, pred, "evaluation")
                                    save_artifact(child, cw, state, "selection_state.json", "model/selection_state.json")
                                    child.finish_run(notes="Fresh preprocessing/pilot/selector/final Ridge fit only on purged train fold; grouped one-hot/indicators, no holdout.")
                                    predictions.append(pred)
                                print(f"{task}/{mode} k={k} fold={fold.fold_id} completed {child.run_id}", flush=True)
                            except Exception as error:
                                record["failed_fold_run_ids"].append(child.run_id)
                                print(f"FAILED k={k}/fold{fold.fold_id}: {error}; retained {child.run_id}", flush=True)
                        candidate.log_metrics({"fold_run_ids": record["fold_run_ids"], "failed_fold_run_ids": record["failed_fold_run_ids"]})
                        if record["failed_fold_run_ids"]: raise CandidateFailed("Incomplete candidate excluded; failed folds retained, no retries")
                        record["summary"] = aggregate_folds(predictions)
                        candidate.log_metrics(record["summary"])
                        record["status"] = "completed"
                        candidate.finish_run(notes=f"C top{k} groups; rank pooled CV MAE, no validation-based k choice.")
                except CandidateFailed: record["status"] = "failed"
                records.append(record)
            selected = choose_k(records, design["selection"]["tolerance"])
            selection = {"candidate_run_id": selected["run_id"], "k_groups": selected["k_groups"], "pooled_MAE": selected["summary"]["pooled"]["MAE"],
                         "locked_at": datetime.now(timezone.utc).isoformat(), "before_validation": True}
            save_artifact(parent, work, {"selection": selection, "candidates": records}, "selection.json", "search/selection.json")
            final, comparison, frozen = final_evaluations(root, parent, common, design, train, x, selected, config, prep, logger) if mode == "full" else ({}, [], None)
        result = {"mode": mode, "parent_run_id": parent.run_id, "candidates": records, "selection": selection, "final_run_ids": final,
                  "comparison": comparison, "test_csv_accessed": False, "official_full": mode == "full" and not is_test}
        save_artifact(parent, work, result, "results.json", "search/results.json")
        if frozen: save_artifact(parent, work, frozen, "frozen_model.json", "selection/frozen_model.json")
        parent.log_metrics({"selected_k_groups": selected["k_groups"], "attempted_cv_pipeline_fits": sum(len(c["fold_run_ids"]) for c in records),
                            "failed_candidates": sum(c["status"] == "failed" for c in records), "selected_deployment_variant": frozen["selected_variant"] if frozen else None,
                            "test_csv_accessed": False, "memory_mb_before_data": memory})
        parent.finish_run(notes="Fixed Ridge alpha0.1 A(reused)/B/C; selection k by train CV, deployment by validation including existing RF/persistence. No test/T13/weights or extra tuning.")
    report = root / "reports/ablation" / mode
    report.mkdir(parents=True, exist_ok=True)
    write_json(report / "run.json", {"parent_run_id": parent.run_id, "final_run_ids": final})
    if frozen: write_json(root / "reports/ablation/frozen_model.json", frozen)
    print(f"COMPLETED {task}/{mode} parent={parent.run_id}, k={selected['k_groups']}, deployment={frozen['selected_variant'] if frozen else None}", flush=True)
    return parent.run_id


def main():
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args()
    execute_ablation(Path(__file__).resolve().parents[1], mode=args.mode, is_test=args.test_only)


if __name__ == "__main__": main()
