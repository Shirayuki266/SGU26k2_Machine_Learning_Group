"""T17b supplementary experiments using only verified train/CV/validation data."""

import json
from pathlib import Path
import csv
import tempfile
from time import perf_counter

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Lasso, Ridge
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeRegressor
from threadpoolctl import threadpool_limits

from beijing_air.ablation import load_train_B, load_validation_B
from beijing_air.eda import ids_digest, read_json
from beijing_air.experiment_logging import ExperimentLogger
from beijing_air.features import feature_registry
from beijing_air.initial_models import available_memory_mb
from beijing_air.metrics import regression_metrics
from beijing_air.preprocessing import make_preprocessor
from beijing_air.temporal_cv import expanding_folds


LOCKED_RF_RUN_ID = "780ecb7fb59d48bea58d5e4a076f1f26"
PERSISTENCE_RUN_ID = "24cef47874a94d9faa7bfcbae29b5c58"
MINIMUM_FREE_MEMORY_MB = 768


def expand_candidates(design):
    """Flatten the finite, predeclared candidate design in stable order."""
    candidates = []
    for spec in design["random_forest"]:
        candidates.append({**spec, "family": "random_forest", "model": "random_forest"})
    for spec in design["hist_gradient_boosting"]:
        candidates.append({**spec, "family": "hist_gradient_boosting",
                           "model": "hist_gradient_boosting"})
    for spec in design["linear"]:
        candidates.append({**spec, "family": "linear"})
    for spec in design["decision_tree"]:
        candidates.append({**spec, "family": "decision_tree", "model": "decision_tree"})
    for spec in design["baselines"]:
        candidates.append({**spec, "family": "baseline", "parameters": {}})
    ids = [candidate["candidate_id"] for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("T17b candidate IDs must be unique")
    return candidates


def pooled_fold_metrics(fold_predictions):
    """Aggregate all OOF rows, weighting every sample equally."""
    if len(fold_predictions) != 3 or any(frame.empty for frame in fold_predictions):
        raise ValueError("A full candidate requires exactly three nonempty CV folds")
    pooled = pd.concat(fold_predictions, ignore_index=True)
    if pooled.sample_id.isna().any() or pooled.sample_id.duplicated().any():
        raise ValueError("CV out-of-fold sample IDs must be unique")
    fold_metrics = [regression_metrics(frame.y_true, frame.y_pred) for frame in fold_predictions]
    return {
        "pooled": regression_metrics(pooled.y_true, pooled.y_pred),
        "folds": fold_metrics,
        "fold_mean": {
            key: float(np.mean([metric[key] for metric in fold_metrics]))
            for key in ("MAE", "RMSE", "R2")
            if all(metric[key] is not None for metric in fold_metrics)
        },
        "fold_std": {
            key: float(np.std([metric[key] for metric in fold_metrics], ddof=0))
            for key in ("MAE", "RMSE", "R2")
            if all(metric[key] is not None for metric in fold_metrics)
        },
        "std_ddof": 0,
    }


def choose_by_cv(candidates):
    """Choose only complete candidates, with stable predeclared tie ordering."""
    complete = [
        item for item in candidates
        if item.get("status") == "completed"
        and item.get("cv", {}).get("pooled", {}).get("MAE") is not None
    ]
    if not complete:
        raise ValueError("No complete CV candidate; do not select by validation")
    minimum = min(item["cv"]["pooled"]["MAE"] for item in complete)
    return next(item for item in complete if item["cv"]["pooled"]["MAE"] <= minimum + 1e-12)


def fit_stack_predictions(oof_parts, validation_parts, alpha):
    """Fit the meta-model on aligned train OOF rows; validation labels are ignored."""
    if len(oof_parts) != len(validation_parts) or len(oof_parts) < 2:
        raise ValueError("Stack requires matching OOF and validation base predictions")
    oof_reference = oof_parts[0].sort_values("sample_id", kind="stable").reset_index(drop=True)
    validation_reference = validation_parts[0].sort_values(
        "sample_id", kind="stable"
    ).reset_index(drop=True)
    sorted_oof = [oof_reference]
    sorted_validation = [validation_reference]
    for frame in oof_parts[1:]:
        frame = frame.sort_values("sample_id", kind="stable").reset_index(drop=True)
        if (not oof_reference.sample_id.equals(frame.sample_id)
                or not np.array_equal(oof_reference.y_true.to_numpy(), frame.y_true.to_numpy())):
            raise ValueError("Stack base OOF IDs/targets differ")
        sorted_oof.append(frame)
    for frame in validation_parts[1:]:
        frame = frame.sort_values("sample_id", kind="stable").reset_index(drop=True)
        if (not validation_reference.sample_id.equals(frame.sample_id)
                or not np.array_equal(validation_reference.y_true.to_numpy(), frame.y_true.to_numpy())):
            raise ValueError("Stack base validation IDs/targets differ")
        sorted_validation.append(frame)
    oof_matrix = np.column_stack([frame.y_pred.to_numpy() for frame in sorted_oof])
    validation_matrix = np.column_stack([frame.y_pred.to_numpy() for frame in sorted_validation])
    if not np.isfinite(oof_matrix).all() or not np.isfinite(validation_matrix).all():
        raise ValueError("Stack requires finite base OOF and validation predictions")
    meta = Ridge(alpha=alpha)
    meta.fit(oof_matrix, oof_reference.y_true.to_numpy())
    return validation_reference, meta.predict(validation_matrix), meta.get_params()


def _prediction_frame(samples, predictions, run_id, model):
    predicted = np.asarray(predictions, dtype=np.float64)
    if len(samples) != len(predicted) or not np.isfinite(predicted).all():
        raise ValueError("Predictions must be finite and preserve every requested sample")
    return pd.DataFrame({
        "sample_id": samples.sample_id.to_numpy(),
        "station": samples.station.to_numpy(),
        "input_timestamp": samples.input_timestamp.to_numpy(),
        "target_timestamp": samples.target_timestamp.to_numpy(),
        "y_true": samples.target_pm25.to_numpy(dtype=np.float64),
        "y_pred": predicted,
        "split": samples.split.to_numpy(),
        "is_primary": samples.is_primary.to_numpy(dtype=bool),
        "run_id": run_id,
        "model": model,
    })


def _rolling_mean_predictions(samples, features):
    """Use T07's causal complete 3-hour rolling mean, else persistence."""
    if not samples.sample_id.tolist() == features.index.tolist():
        raise ValueError("Rolling baseline features are not aligned to sample IDs")
    values = features["pm25_roll_mean_3h"].to_numpy(dtype=np.float64)
    current = samples["PM2.5"].to_numpy(dtype=np.float64)
    if not np.isfinite(current).all():
        raise ValueError("Primary cohort requires observed PM2.5 at the forecast origin")
    return np.where(np.isfinite(values), values, current)


def _yesterday_predictions(samples, observation_lookup):
    """Read only PM2.5 at target time minus 24h, never after the origin."""
    values = []
    columns = samples[["station", "input_timestamp", "target_timestamp", "PM2.5"]]
    for station, input_time, target_time, current_value in columns.itertuples(index=False, name=None):
        target_time = pd.Timestamp(target_time)
        origin_time = pd.Timestamp(input_time)
        lookup_time = target_time - pd.Timedelta(hours=24)
        if lookup_time > origin_time:
            raise ValueError("Yesterday baseline would use information after the forecast origin")
        observed = observation_lookup.get((station, lookup_time))
        current = float(current_value)
        if not np.isfinite(current):
            raise ValueError("Primary cohort requires observed PM2.5 at the forecast origin")
        values.append(float(observed) if observed is not None and np.isfinite(observed) else current)
    return np.asarray(values, dtype=np.float64)


def _observation_lookup(train, validation):
    rows = pd.concat([train, validation], ignore_index=True)
    rows = rows[["station", "input_timestamp", "PM2.5", "is_primary"]]
    rows = rows.loc[rows.is_primary].drop_duplicates(["station", "input_timestamp"])
    return {
        (station, timestamp): value
        for station, timestamp, value in rows[["station", "input_timestamp", "PM2.5"]]
        .itertuples(index=False, name=None)
    }


def _effective_preprocessing(preprocessing, model):
    record = json.loads(json.dumps(preprocessing))
    record["t17b_applied_scale"] = "standard_scaler" if model in ("lasso", "elastic_net") else "none"
    return record


def _pipeline(candidate, config, preprocessing):
    parameters = candidate["parameters"]
    model = candidate["model"]
    if model == "random_forest":
        estimator = RandomForestRegressor(**parameters)
        preprocessing_model = "random_forest"
    elif model == "hist_gradient_boosting":
        estimator = HistGradientBoostingRegressor(**parameters)
        preprocessing_model = "random_forest"
    elif model == "lasso":
        estimator = Lasso(**parameters)
        preprocessing_model = "ridge"
    elif model == "elastic_net":
        estimator = ElasticNet(**parameters)
        preprocessing_model = "ridge"
    elif model == "decision_tree":
        estimator = DecisionTreeRegressor(**parameters)
        preprocessing_model = "random_forest"
    else:
        raise ValueError(f"Unknown T17b estimator: {model}")
    preprocess = make_preprocessor(
        preprocessing_model,
        feature_set=candidate["feature_set"],
        config=config,
        preprocessing_config=preprocessing,
    )
    return Pipeline([("preprocess", preprocess), ("model", estimator)])


def _actual_parameters(candidate):
    model = candidate["model"]
    if model == "random_forest":
        estimator = RandomForestRegressor(**candidate["parameters"])
    elif model == "hist_gradient_boosting":
        estimator = HistGradientBoostingRegressor(**candidate["parameters"])
    elif model == "lasso":
        estimator = Lasso(**candidate["parameters"])
    elif model == "elastic_net":
        estimator = ElasticNet(**candidate["parameters"])
    elif model == "decision_tree":
        estimator = DecisionTreeRegressor(**candidate["parameters"])
    else:
        return candidate["parameters"]
    return estimator.get_params(deep=True)


def _feature_pair(data, features, feature_set, config):
    if feature_set not in ("A", "B"):
        raise ValueError(f"Unsupported feature set: {feature_set}")
    names = feature_registry(config).loc[
        lambda frame: frame.feature_sets.str.split(";").map(lambda sets: feature_set in sets),
        "feature_name",
    ].tolist()
    result = features.loc[data.sample_id, names].copy()
    result.index = data.sample_id.to_numpy()
    if result.index.tolist() != data.sample_id.tolist():
        raise ValueError("Feature IDs/order differ from samples")
    return result


def _write_predictions(frame, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False, encoding="utf-8", lineterminator="\n",
                 compression={"method": "gzip", "compresslevel": 6, "mtime": 0})
    return destination


def _log_candidate(root, logger, parent, candidate, candidate_x, train, folds,
                   design, config, preprocessing, observation_lookup, mode, temp_dir):
    is_baseline = candidate["family"] == "baseline"
    reference_run = PERSISTENCE_RUN_ID if is_baseline else LOCKED_RF_RUN_ID
    preprocessing_record = (
        {"baseline": candidate["candidate_id"]}
        if is_baseline else _effective_preprocessing(preprocessing, candidate["model"])
    )
    parameters = {
        "stage": "candidate",
        "candidate_id": candidate["candidate_id"],
        "family": candidate["family"],
        "actual_model_parameters": _actual_parameters(candidate),
        "declared_parameters": candidate["parameters"],
        "missing_policy": candidate.get("missing_policy"),
    }
    candidate_run = logger.start_run(
        task_id="T17b",
        reference_run_id=reference_run,
        parent_run_id=parent.run_id,
        mode=mode,
        kind="tuning",
        objective=f"Evaluate {candidate['candidate_id']} using train-only temporal CV.",
        hypothesis=candidate.get("hypothesis", "Compare the predeclared candidate without assuming it improves."),
        change=f"Predeclared T17b candidate {candidate['candidate_id']}.",
        model=candidate["model"],
        parameters=parameters,
        feature_set=candidate["feature_set"],
        preprocessing=preprocessing_record,
        data={"split_manifest": "reports/splits_full/split_manifest.json",
              "feature_manifest": "reports/features_full/feature_manifest.json",
              "scope": "T05 train only; no test file or test IDs accessed"},
        split={"protocol": "expanding_window", "folds": len(folds),
               "fold_ids": [fold.fold_id for fold in folds],
               "selection_metric": "pooled_MAE"},
        time_ranges=[fold.audit for fold in folds],
        sample_counts={"train": len(train), "fold_evaluations": [
            len(train.iloc[fold.evaluation]) for fold in folds]},
        seed=design["seed"],
        budget=design["budget"],
        is_test=False,
        source="scripts/run_supplementary_experiments.py",
    )
    fold_ids, fold_frames, failed_fold_ids = [], [], []
    start = perf_counter()
    with candidate_run:
        for fold in folds:
            fit_rows = train.iloc[fold.fit]
            eval_rows = train.iloc[fold.evaluation]
            run_params = {
                "stage": "fold",
                "candidate_id": candidate["candidate_id"],
                "fold_audit": fold.audit,
                "actual_model_parameters": parameters["actual_model_parameters"],
            }
            child = logger.start_run(
                task_id="T17b",
                reference_run_id=reference_run,
                parent_run_id=candidate_run.run_id,
                fold_id=fold.fold_id,
                mode=mode,
                kind="tuning",
                objective=f"Out-of-fold prediction for {candidate['candidate_id']}.",
                hypothesis=candidate.get("hypothesis", "Predeclared candidate; no validation-based tuning."),
                change=f"Fold {fold.fold_id} only; fitted preprocessing/model use fold fit rows.",
                model=candidate["model"],
                parameters=run_params,
                feature_set=candidate["feature_set"],
                preprocessing=preprocessing_record,
                data={"scope": "T05 train rows only; no test access"},
                split=fold.audit,
                sample_counts={"fit": len(fit_rows), "evaluation": len(eval_rows),
                               "purged": len(fold.purged)},
                seed=design["seed"],
                budget=design["budget"],
                is_test=False,
                source="scripts/run_supplementary_experiments.py",
            )
            try:
                with child:
                    if not is_baseline:
                        memory = available_memory_mb()
                        if memory is not None and memory < MINIMUM_FREE_MEMORY_MB:
                            raise MemoryError(
                                f"Available memory {memory:.0f} MB is below the predeclared "
                                f"{MINIMUM_FREE_MEMORY_MB} MB floor; no automatic subsampling."
                            )
                        model_pipeline = _pipeline(candidate, config, preprocessing)
                        x_fit = candidate_x.loc[fit_rows.sample_id]
                        x_eval = candidate_x.loc[eval_rows.sample_id]
                        with threadpool_limits(limits=design["blas_threads"]):
                            model_pipeline.fit(x_fit, fit_rows.target_pm25)
                            predictions = model_pipeline.predict(x_eval)
                    elif candidate["model"] == "rolling_mean_3h":
                        predictions = _rolling_mean_predictions(
                            eval_rows, candidate_x.loc[eval_rows.sample_id]
                        )
                    else:
                        predictions = _yesterday_predictions(eval_rows, observation_lookup)
                    frame = _prediction_frame(eval_rows, predictions, child.run_id, candidate["model"])
                    metrics = regression_metrics(frame.y_true, frame.y_pred)
                    child.log_metrics(metrics, split="evaluation")
                    artifact = _write_predictions(
                        frame, Path(temp_dir) / f"{child.run_id}_evaluation.csv.gz"
                    )
                    child.log_artifact(artifact, name="predictions/evaluation.csv.gz")
                fold_ids.append(child.run_id)
                fold_frames.append(frame)
            except Exception:
                failed_fold_ids.append(child.run_id)
                raise
        pooled = pooled_fold_metrics(fold_frames) if mode == "full" else {
            "pooled": regression_metrics(
                pd.concat(fold_frames, ignore_index=True).y_true,
                pd.concat(fold_frames, ignore_index=True).y_pred,
            ),
            "folds": [regression_metrics(frame.y_true, frame.y_pred) for frame in fold_frames],
            "fold_mean": {},
            "fold_std": {},
            "std_ddof": 0,
        }
        oof = pd.concat(fold_frames, ignore_index=True)
        candidate_run.log_metrics({
            "fold_run_ids": fold_ids,
            "failed_fold_run_ids": failed_fold_ids,
            "pooled": pooled["pooled"],
            "folds": pooled["folds"],
            "fold_mean": pooled["fold_mean"],
            "fold_std": pooled["fold_std"],
            "std_ddof": pooled["std_ddof"],
            "fit_and_cv_seconds": perf_counter() - start,
            "oof_sample_ids_sha256": ids_digest(oof.sample_id),
        })
        artifact = _write_predictions(
            oof, Path(temp_dir) / f"{candidate_run.run_id}_oof.csv.gz"
        )
        candidate_run.log_artifact(artifact, name="predictions/oof.csv.gz")
        candidate_run.finish_run(
            notes=f"Completed {len(fold_ids)} fold(s); pooled metrics use every saved OOF row.",
            decision="Eligible for CV-only selection." if mode == "full"
            else "Smoke result only; not eligible for model selection.",
        )
    return {
        "candidate": candidate,
        "candidate_run_id": candidate_run.run_id,
        "status": "completed",
        "cv": pooled,
        "fold_run_ids": fold_ids,
        "oof": pd.concat(fold_frames, ignore_index=True),
        "validation": None,
    }


def _run_validation(root, logger, parent, result, train, validation, x_train, x_validation,
                    design, config, preprocessing, temp_dir):
    candidate = result["candidate"]
    is_baseline = candidate["family"] == "baseline"
    candidate_x_train = x_train[candidate["feature_set"]]
    candidate_x_validation = x_validation[candidate["feature_set"]]
    preprocessing_record = (
        {"baseline": candidate["candidate_id"]}
        if is_baseline else _effective_preprocessing(preprocessing, candidate["model"])
    )
    parameters = {
        "stage": "validation",
        "candidate_id": candidate["candidate_id"],
        "selected_candidate_run_id": result["candidate_run_id"],
        "family": candidate["family"],
        "actual_model_parameters": _actual_parameters(candidate),
        "declared_parameters": candidate["parameters"],
        "missing_policy": candidate.get("missing_policy"),
    }
    run = logger.start_run(
        task_id="T17b",
        reference_run_id=result["candidate_run_id"],
        parent_run_id=parent.run_id,
        mode="full",
        kind="train",
        objective=f"Evaluate CV-selected {candidate['candidate_id']} on the frozen primary validation IDs.",
        hypothesis=candidate.get("hypothesis", "Compare the predeclared candidate without assuming it improves."),
        change="Validation is evaluated after CV-only selection; it is not used to fit preprocessing or model.",
        model=candidate["model"],
        parameters=parameters,
        feature_set=candidate["feature_set"],
        preprocessing=preprocessing_record,
        data={"split_manifest": "reports/splits_full/split_manifest.json",
              "scope": "T05 train fit and primary validation evaluation; no test access"},
        split={"train_only_fit": True, "validation_ids_sha256": ids_digest(validation.sample_id),
               "validation_samples": len(validation)},
        sample_counts={"train": len(train), "validation": len(validation)},
        seed=design["seed"],
        budget=design["budget"],
        is_test=False,
        source="scripts/run_supplementary_experiments.py",
    )
    with run:
        if not is_baseline:
            memory = available_memory_mb()
            if memory is not None and memory < MINIMUM_FREE_MEMORY_MB:
                raise MemoryError(
                    f"Available memory {memory:.0f} MB is below the predeclared "
                    f"{MINIMUM_FREE_MEMORY_MB} MB floor; no automatic subsampling."
                )
            model_pipeline = _pipeline(candidate, config, preprocessing)
            with threadpool_limits(limits=design["blas_threads"]):
                model_pipeline.fit(candidate_x_train, train.target_pm25)
                predictions = model_pipeline.predict(candidate_x_validation)
        elif candidate["model"] == "rolling_mean_3h":
            predictions = _rolling_mean_predictions(validation, candidate_x_validation)
        else:
            predictions = _yesterday_predictions(
                validation, _observation_lookup(train, validation)
            )
        frame = _prediction_frame(validation, predictions, run.run_id, candidate["model"])
        metrics = regression_metrics(frame.y_true, frame.y_pred)
        run.log_metrics(metrics, split="validation_primary")
        path = _write_predictions(frame, Path(temp_dir) / f"{run.run_id}_validation.csv.gz")
        run.log_artifact(path, name="predictions/validation.csv.gz")
        run.log_metrics({"validation_ids_sha256": ids_digest(frame.sample_id),
                         "test_csv_accessed": False, "validation_run_seconds": None})
        run.finish_run(
            notes="Validation metrics are descriptive for one development split; not used for hyperparameter selection.",
            decision="Candidate only; does not change the T12/T13 frozen model.",
        )
    result["validation_run_id"] = run.run_id
    result["validation"] = frame
    result["validation_metrics"] = metrics
    return result


def _create_ensemble_candidate(logger, parent, selected, design, temp_dir):
    fold_frames = []
    for fold_id in (1, 2, 3):
        frame = _ensemble_fold("fusion_3", selected, fold_id)
        fold_frames.append(frame)
    cv = pooled_fold_metrics(fold_frames)
    candidate = {
        "candidate_id": "fusion_3_cv_champions",
        "family": "fusion",
        "model": "fusion_3",
        "feature_set": "A+B",
        "parameters": {
            "base_candidate_run_ids": [item["candidate_run_id"] for item in selected],
            "selection": "top three distinct model families by train pooled CV MAE",
            "base_model_count": 3,
        },
        "hypothesis": "A CV-selected mean ensemble may combine complementary prediction errors.",
    }
    params = {
        "stage": "candidate",
        "candidate_id": candidate["candidate_id"],
        "family": "fusion",
        "actual_model_parameters": candidate["parameters"],
        "base_selection_metric": "pooled_CV_MAE",
        "oof_selection_reuses_cv": True,
    }
    run = logger.start_run(
        task_id="T17b", parent_run_id=parent.run_id, mode="full", kind="tuning",
        objective="Describe Fusion-3 OOF performance for CV-selected base learners.",
        hypothesis=candidate["hypothesis"],
        change="Unweighted mean of three distinct-family CV champions selected using train OOF pooled MAE.",
        model="fusion_3", parameters=params, feature_set="A+B",
        preprocessing={"base_pipelines": "T08"},
        data={"scope": "train OOF predictions only"},
        split={"protocol": "expanding_window", "folds": 3, "selection_metric": "pooled_CV_MAE"},
        sample_counts={"folds": [len(frame) for frame in fold_frames]},
        seed=design["seed"], budget=design["budget"], is_test=False,
        source="scripts/run_supplementary_experiments.py",
    )
    fold_run_ids = []
    with run:
        for fold_id, frame in enumerate(fold_frames, 1):
            child = logger.start_run(
                task_id="T17b", parent_run_id=run.run_id, fold_id=fold_id, mode="full",
                kind="tuning", objective="Average selected base OOF predictions for this fold.",
                hypothesis=candidate["hypothesis"], change="No fitting; average aligned fold predictions.",
                model="fusion_3", parameters={"stage": "fold", "candidate_id": candidate["candidate_id"],
                                              "actual_model_parameters": candidate["parameters"]},
                feature_set="A+B", preprocessing={"base_pipelines": "T08"},
                data={"scope": "train OOF predictions only"},
                split={"fold_id": fold_id}, sample_counts={"evaluation": len(frame)},
                seed=design["seed"], budget=design["budget"], is_test=False,
                source="scripts/run_supplementary_experiments.py",
            )
            with child:
                frame = frame.copy()
                frame["run_id"] = child.run_id
                child.log_metrics(regression_metrics(frame.y_true, frame.y_pred), split="evaluation")
                path = _write_predictions(frame, Path(temp_dir) / f"{child.run_id}_evaluation.csv.gz")
                child.log_artifact(path, name="predictions/evaluation.csv.gz")
            fold_run_ids.append(child.run_id)
        run.log_metrics({
            "fold_run_ids": fold_run_ids,
            "failed_fold_run_ids": [],
            "pooled": cv["pooled"],
            "folds": cv["folds"],
            "fold_mean": cv["fold_mean"],
            "fold_std": cv["fold_std"],
            "std_ddof": 0,
            "selection_reuses_cv": True,
        })
        oof = pd.concat(fold_frames, ignore_index=True)
        path = _write_predictions(oof, Path(temp_dir) / f"{run.run_id}_oof.csv.gz")
        run.log_artifact(path, name="predictions/oof.csv.gz")
        run.finish_run(
            notes="CV score is descriptive only: the base learners were selected using the same OOF pooled MAE.",
            decision="Report validation separately; do not use this CV score as an unbiased ensemble estimate.",
        )
    return {**candidate, "candidate_run_id": run.run_id, "status": "completed",
            "cv": cv, "fold_run_ids": fold_run_ids, "oof": pd.concat(fold_frames, ignore_index=True)}


def _ensemble_fold(model, base_results, fold_id):
    parts = []
    for result in base_results:
        if fold_id not in result["fold_ids_by_id"]:
            raise ValueError("An ensemble base model is missing the requested OOF fold")
        frame = result["oof"].loc[
            result["oof"].sample_id.isin(result["fold_ids_by_id"][fold_id])
        ].sort_values("sample_id", kind="stable").reset_index(drop=True)
        parts.append(frame)
    first = parts[0]
    for part in parts[1:]:
        if (not first.sample_id.equals(part.sample_id)
                or not np.array_equal(first.y_true.to_numpy(), part.y_true.to_numpy())):
            raise ValueError("Ensemble base OOF sample IDs/targets differ")
    frame = first.copy()
    frame["y_pred"] = np.mean(
        np.column_stack([part.y_pred.to_numpy() for part in parts]), axis=1
    )
    frame["model"] = model
    return frame


def _run_stack_validation(logger, parent, selected, validation, design, temp_dir):
    oof_parts = []
    validation_parts = []
    for item in selected:
        oof_parts.append(item["oof"].sort_values("sample_id", kind="stable").reset_index(drop=True))
        validation_parts.append(item["validation"].sort_values("sample_id", kind="stable").reset_index(drop=True))
    oof_reference = oof_parts[0]
    validation_reference, prediction, meta_parameters = fit_stack_predictions(
        oof_parts, validation_parts, design["ensemble"]["stack_alpha"]
    )
    params = {
        "stage": "validation",
        "base_candidate_run_ids": [item["candidate_run_id"] for item in selected],
        "meta_model": "Ridge",
        "parameters": meta_parameters,
        "alpha": design["ensemble"]["stack_alpha"],
        "fit_scope": "OOF train predictions only",
        "validation_is_fit_data": False,
    }
    run = logger.start_run(
        task_id="T17b", parent_run_id=parent.run_id, mode="full", kind="train",
        objective="Evaluate a Ridge stacker fit exclusively on aligned base OOF predictions.",
        hypothesis="A linear meta-learner may combine the selected base predictions.",
        change="Meta Ridge is fit on train OOF predictions; validation is prediction-only.",
        model="stack", parameters=params, feature_set="A+B",
        preprocessing={"base_pipelines": "T08; meta Ridge on saved OOF prediction columns"},
        data={"scope": "train OOF labels for meta fit; primary validation for scoring only"},
        split={"validation_ids_sha256": ids_digest(validation_reference.sample_id),
               "stack_fit_sample_ids_sha256": ids_digest(oof_reference.sample_id)},
        sample_counts={"oof_fit": len(oof_reference), "validation": len(validation_reference)},
        seed=design["seed"], budget=design["budget"], is_test=False,
        source="scripts/run_supplementary_experiments.py",
    )
    with run:
        frame = validation_reference.copy()
        frame["y_pred"] = prediction
        frame["run_id"] = run.run_id
        frame["model"] = "stack"
        metrics = regression_metrics(frame.y_true, frame.y_pred)
        run.log_metrics(metrics, split="validation_primary")
        run.log_metrics({"oof_only_meta_fit": True, "validation_used_for_fit": False})
        path = _write_predictions(frame, Path(temp_dir) / f"{run.run_id}_validation.csv.gz")
        run.log_artifact(path, name="predictions/validation.csv.gz")
        run.finish_run(
            notes="Meta-learner fit uses OOF train predictions only; one validation split, no test.",
            decision="Supplementary candidate only; does not change frozen T12/T13 model.",
        )
    return {"run_id": run.run_id, "frame": frame, "metrics": metrics}


def _baseline_references(root, validation):
    result = {}
    for run_id in (PERSISTENCE_RUN_ID, LOCKED_RF_RUN_ID):
        path = root / "artifacts" / "experiments" / run_id / "artifacts" / "predictions" / "validation.csv.gz"
        if not path.is_file():
            if run_id != PERSISTENCE_RUN_ID:
                raise FileNotFoundError(f"Required saved validation reference is missing: {path}")
            frame = pd.DataFrame({
                "sample_id": validation.sample_id.to_numpy(),
                "y_true": validation.target_pm25.to_numpy(dtype=np.float64),
                "y_pred": validation["PM2.5"].to_numpy(dtype=np.float64),
            })
            summary_path = root / "reports" / "tables" / "experiment_summary.csv"
            summary = pd.read_csv(
                summary_path, usecols=["run_id (validation/CV)", "Validation MAE"]
            )
            saved = summary.loc[
                summary["run_id (validation/CV)"].eq(run_id), "Validation MAE"
            ]
            if len(saved) != 1:
                raise ValueError("Cannot verify persistence reference against the T17a summary")
            measured = regression_metrics(frame.y_true, frame.y_pred)["MAE"]
            if abs(measured - float(saved.iloc[0])) > 1e-6:
                raise ValueError("Reconstructed primary persistence differs from the verified T17a metric")
            result[run_id] = {"predictions": frame, "source": "PM2.5(t) on primary IDs; T17a MAE verified"}
            continue
        compression = "gzip" if path.suffix == ".gz" else None
        frame = pd.read_csv(path, compression=compression, usecols=["sample_id", "y_true", "y_pred"])
        if frame.sample_id.isna().any() or frame.sample_id.duplicated().any():
            raise ValueError(f"Duplicate/missing validation IDs in reference run {run_id}")
        if set(frame.sample_id) != set(validation.sample_id):
            raise ValueError(f"Reference validation IDs differ: {run_id}")
        aligned = validation[["sample_id", "target_pm25"]].merge(
            frame, on="sample_id", how="left", validate="one_to_one", sort=False
        )
        if (not np.allclose(aligned.target_pm25, aligned.y_true, rtol=0, atol=1e-12)
                or not np.isfinite(aligned.y_pred).all()):
            raise ValueError(f"Reference validation target/prediction mismatch: {run_id}")
        result[run_id] = {"predictions": frame, "source": path.relative_to(root).as_posix()}
    return result


def _require_restored_run_bundles(root):
    """Fail before data preparation if the official logger cannot append safely."""
    ledger = root / "experiments" / "experiment_log.csv"
    missing = []
    with ledger.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            run_dir = root / "artifacts" / "experiments" / row["run_id"]
            absent = [
                name for name in ("config.json", "metadata.json", "metrics.json", "notes.md")
                if not (run_dir / name).is_file()
            ]
            if absent:
                missing.append(f"{row['run_id']} ({row['task_id']}): {', '.join(absent)}")
    if missing:
        raise FileNotFoundError(
            "Restore the original indexed run bundles before starting T17b; "
            "the experiment ledger was not changed. Missing: " + "; ".join(missing)
        )


def _full_folds(train, config):
    folds = expanding_folds(train, config)
    if len(folds) != 3:
        raise ValueError("T17b requires the frozen three-fold expanding CV")
    return folds


def _smoke_fold(train):
    times = pd.DatetimeIndex(train.target_timestamp.unique()).sort_values()
    if len(times) < 80:
        raise ValueError("Not enough train timestamps for a bounded smoke run")
    fit_stop = min(64, len(times) - 16)
    eval_stop = min(fit_stop + 8, len(times))
    first_origin = times[fit_stop] - pd.Timedelta(hours=1)
    fit = np.flatnonzero(train.target_timestamp.lt(first_origin))
    evaluation = np.flatnonzero(
        train.target_timestamp.ge(times[fit_stop]) & train.target_timestamp.lt(times[eval_stop])
    )
    if not len(fit) or not len(evaluation):
        raise ValueError("Could not construct the train-only smoke window")
    purged = np.flatnonzero(
        train.target_timestamp.lt(times[fit_stop])
        & train.target_timestamp.ge(first_origin)
    )
    return [type("SmokeFold", (), {
        "fold_id": 1,
        "fit": fit,
        "evaluation": evaluation,
        "purged": purged,
        "audit": {
            "fold_id": 1,
            "mode": "smoke",
            "fit_sample_ids_sha256": ids_digest(train.iloc[fit].sample_id),
            "evaluation_sample_ids_sha256": ids_digest(train.iloc[evaluation].sample_id),
            "fit_samples": len(fit),
            "evaluation_samples": len(evaluation),
            "purged_samples": len(purged),
            "test_csv_accessed": False,
        },
    })()]


def run_supplementary_experiments(root, *, mode="full"):
    """Run the predeclared T17b plan; no code path reads test samples."""
    root = Path(root).resolve()
    if mode not in ("smoke", "full"):
        raise ValueError("mode must be smoke or full")
    design_path = root / "configs/supplementary_experiments.json"
    design = read_json(design_path)
    default_config = read_json(root / "configs/default.json")
    preprocessing = read_json(root / "configs/preprocessing.json")
    initial = read_json(root / "configs/initial_models.json")
    frozen = read_json(root / "reports/ablation/frozen_model.json")
    if (design["schema_version"] != "t17b-supplementary-v1"
            or design["seed"] != 42 or design["cohort"] != "primary"
            or design["folds"] != 3 or design["automatic_retries"] != 0
            or design["parallel_jobs"] != 1 or design["blas_threads"] != 1):
        raise ValueError("T17b design differs from the predeclared finite protocol")
    if (frozen["status"] != "locked_recipe_for_future_refit"
            or frozen["selected_variant"] != "random_forest_A"
            or frozen["selected_run_id"] != LOCKED_RF_RUN_ID
            or frozen["model"]["name"] != "random_forest"
            or frozen["model"]["parameters"] != RandomForestRegressor(
                **initial["models"]["random_forest"]
            ).get_params()
            or frozen["preprocessing"] != preprocessing
            or frozen["features"]["definitions"] != default_config["features"]):
        raise ValueError("T17b must not change the T12/T13 frozen recipe")

    _require_restored_run_bundles(root)
    train, x_train_raw, provenance = load_train_B(root)
    validation, x_validation_raw, validation_provenance = load_validation_B(root)
    train = train.reset_index(drop=True)
    validation = validation.reset_index(drop=True)
    if (train.empty or validation.empty or not train.is_primary.all()
            or not validation.is_primary.all() or not train.split.eq("train").all()
            or not validation.split.eq("validation").all()
            or train.sample_id.duplicated().any() or validation.sample_id.duplicated().any()):
        raise ValueError("T17b requires unique, verified primary train and validation cohorts")
    if not train.sample_id.tolist() == x_train_raw.index.tolist():
        raise ValueError("T07 train features differ from train cohort IDs/order")
    if not validation.sample_id.tolist() == x_validation_raw.index.tolist():
        raise ValueError("Validation features differ from T05 cohort IDs/order")
    _baseline_references(root, validation)
    x_train = {
        feature_set: _feature_pair(train, x_train_raw, feature_set, default_config)
        for feature_set in ("A", "B")
    }
    x_validation = {
        feature_set: _feature_pair(validation, x_validation_raw, feature_set, default_config)
        for feature_set in ("A", "B")
    }
    observation_lookup = _observation_lookup(train, validation)
    folds = _full_folds(train, default_config) if mode == "full" else _smoke_fold(train)
    candidates = expand_candidates(design)
    if mode == "full" and len([c for c in candidates if c["family"] != "baseline"]) != 13:
        raise ValueError("The fixed T17b full search must contain 13 model configurations")
    logger = ExperimentLogger(project_root=root)
    budget = {
        "mode": mode,
        "candidate_configurations": len(candidates),
        "candidate_cv_fits": sum(
            len(folds) for candidate in candidates if candidate["family"] != "baseline"
        ),
        "validation_refit_max": 6 if mode == "full" else 0,
        "folds": len(folds),
        "automatic_retries": 0,
        "parallel_jobs": 1,
        "blas_threads": 1,
        "minimum_free_memory_mb": MINIMUM_FREE_MEMORY_MB,
    }
    with tempfile.TemporaryDirectory(prefix="t17b-") as temp_dir:
        with logger.start_run(
            task_id="T17b",
            mode=mode,
            kind="tuning",
            objective="Run the predeclared supplementary PM2.5 experiments on train/CV/validation only.",
            hypothesis="Supplementary baselines/models/ensembles may or may not improve on locked RF A.",
            change=f"Execute configs/supplementary_experiments.json in {mode} mode.",
            model="supplementary_search",
            parameters={"stage": "search", "design_path": "configs/supplementary_experiments.json",
                        "t05_train_snapshot_id": provenance["train_provenance"]["t05_snapshot_id"],
                        "validation_ids_sha256": ids_digest(validation.sample_id)},
            feature_set="A+B",
            preprocessing=preprocessing,
            data={"train": provenance, "validation": validation_provenance,
                  "scope": "train/CV/validation only; test samples and IDs not opened"},
            split={"protocol": "expanding_window", "folds": len(folds),
                   "validation_ids_sha256": ids_digest(validation.sample_id)},
            sample_counts={"train": len(train), "validation": len(validation),
                           "cv_evaluation": [len(train.iloc[fold.evaluation]) for fold in folds]},
            seed=design["seed"],
            budget=budget,
            is_test=False,
            source="scripts/run_supplementary_experiments.py",
        ) as parent:
            results, failed = [], []
            started = perf_counter()
            for candidate in candidates:
                candidate_x = (
                    x_train[candidate["feature_set"]]
                    if candidate["family"] != "baseline"
                    else x_train["B"]
                )
                try:
                    result = _log_candidate(
                        root, logger, parent, candidate, candidate_x, train, folds,
                        design, default_config, preprocessing, observation_lookup, mode, temp_dir,
                    )
                    result["fold_ids_by_id"] = {
                        fold.fold_id: set(
                            train.iloc[fold.evaluation].sample_id.tolist()
                        ) for fold in folds
                    }
                    results.append(result)
                except Exception as error:
                    failed.append({"candidate_id": candidate["candidate_id"],
                                   "error": f"{type(error).__name__}: {error}"})
                    if isinstance(error, (KeyboardInterrupt, SystemExit)):
                        raise
            parent.log_metrics({"candidate_run_ids": [r["candidate_run_id"] for r in results],
                                "failed_candidates": failed,
                                "test_csv_accessed": False,
                                "elapsed_seconds": perf_counter() - started})
            if mode == "smoke":
                parent.finish_run(
                    notes="Smoke uses one chronological train-only window; not a full CV result.",
                    decision="Smoke-only; do not report or select from these metrics.",
                )
                return {"mode": mode, "parent_run_id": parent.run_id,
                        "completed_candidates": len(results), "failed_candidates": failed}
            if failed:
                raise RuntimeError(f"T17b full candidate failures: {failed}")

            by_id = {result["candidate"]["candidate_id"]: result for result in results}
            rf = [result for result in results if result["candidate"]["family"] == "random_forest"]
            hgb = [result for result in results if result["candidate"]["family"] == "hist_gradient_boosting"]
            linear = [result for result in results if result["candidate"]["family"] == "linear"]
            trees = [result for result in results if result["candidate"]["family"] == "decision_tree"]
            baseline = [result for result in results if result["candidate"]["family"] == "baseline"]
            rf_tuned = choose_by_cv([
                result for result in rf
                if result["candidate"]["candidate_id"] in {
                    "rf_B_tuned_small", "rf_B_tuned_more_trees"
                }
            ])
            validation_results = []
            validation_candidates = {
                by_id["rf_A_locked"]["candidate"]["candidate_id"]: by_id["rf_A_locked"],
                by_id["rf_B_locked"]["candidate"]["candidate_id"]: by_id["rf_B_locked"],
                rf_tuned["candidate"]["candidate_id"]: rf_tuned,
                choose_by_cv(hgb)["candidate"]["candidate_id"]: choose_by_cv(hgb),
                choose_by_cv(linear)["candidate"]["candidate_id"]: choose_by_cv(linear),
                choose_by_cv(trees)["candidate"]["candidate_id"]: choose_by_cv(trees),
            }
            for item in baseline:
                validation_candidates[item["candidate"]["candidate_id"]] = item
            for result in validation_candidates.values():
                validation_results.append(_run_validation(
                    root, logger, parent, result, train, validation,
                    x_train, x_validation, design, default_config,
                    preprocessing, temp_dir,
                ))

            champions = [
                choose_by_cv(rf),
                choose_by_cv(hgb),
                choose_by_cv(linear),
                choose_by_cv(trees),
                choose_by_cv(baseline),
            ]
            selected = sorted(
                champions,
                key=lambda item: (
                    item["cv"]["pooled"]["MAE"],
                    item["candidate"]["candidate_id"],
                ),
            )[:design["ensemble"]["fusion_size"]]
            if len({item["candidate"]["family"] for item in selected}) != 3:
                raise ValueError("Fusion/Stack must use three distinct model families")
            validation_by_candidate = {
                result["candidate"]["candidate_id"]: result for result in validation_results
            }
            ensemble_bases = [
                validation_by_candidate[item["candidate"]["candidate_id"]]
                for item in selected
            ]
            fusion = _create_ensemble_candidate(
                logger, parent, ensemble_bases, design, temp_dir
            )
            base_validation = [item["validation"] for item in ensemble_bases]
            reference = base_validation[0]
            for frame in base_validation[1:]:
                if (not reference.sample_id.equals(frame.sample_id)
                        or not np.array_equal(reference.y_true.to_numpy(), frame.y_true.to_numpy())):
                    raise ValueError("Fusion base validation IDs/targets differ")
            fusion_predictions = np.mean(
                np.column_stack([frame.y_pred.to_numpy() for frame in base_validation]), axis=1
            )
            fusion_run = logger.start_run(
                task_id="T17b", parent_run_id=parent.run_id,
                reference_run_id=fusion["candidate_run_id"], mode="full", kind="train",
                objective="Score Fusion-3 on the frozen primary validation IDs.",
                hypothesis=fusion["hypothesis"],
                change="Unweighted mean of the three base validation predictions selected by train pooled CV MAE.",
                model="fusion_3",
                parameters={"stage": "validation", "candidate_id": fusion["candidate_id"],
                            "selected_candidate_run_id": fusion["candidate_run_id"],
                            "actual_model_parameters": fusion["parameters"]},
                feature_set="A+B", preprocessing={"base_pipelines": "T08"},
                data={"scope": "primary validation only; base models fit on train"},
                split={"validation_ids_sha256": ids_digest(reference.sample_id)},
                sample_counts={"validation": len(reference)}, seed=design["seed"],
                budget=budget, is_test=False, source="scripts/run_supplementary_experiments.py",
            )
            with fusion_run:
                fusion_frame = reference.copy()
                fusion_frame["y_pred"] = fusion_predictions
                fusion_frame["run_id"] = fusion_run.run_id
                fusion_frame["model"] = "fusion_3"
                fusion_metrics = regression_metrics(fusion_frame.y_true, fusion_frame.y_pred)
                fusion_run.log_metrics(fusion_metrics, split="validation_primary")
                fusion_path = _write_predictions(
                    fusion_frame, Path(temp_dir) / f"{fusion_run.run_id}_validation.csv.gz"
                )
                fusion_run.log_artifact(fusion_path, name="predictions/validation.csv.gz")
                fusion_run.finish_run(
                    notes="CV selection and validation are separate; one validation split is not an independent test.",
                    decision="Supplementary candidate only; T12/T13 lock remains unchanged.",
                )
            stack = _run_stack_validation(
                logger, parent, ensemble_bases, validation, design, temp_dir
            )
            parent.log_metrics({
                "selected_validation_candidate_ids": list(validation_candidates),
                "fusion_base_candidate_ids": [
                    item["candidate"]["candidate_id"] for item in selected
                ],
                "fusion_validation_run_id": fusion_run.run_id,
                "stack_validation_run_id": stack["run_id"],
                "validation_sample_ids_sha256": ids_digest(validation.sample_id),
                "test_csv_accessed": False,
            })
            parent.finish_run(
                notes="Completed the declared T17b candidates, CV-only selection, validation comparisons, and ensembles.",
                decision="No model can replace the T12/T13 lock from these supplementary results.",
            )
            return {
                "mode": mode,
                "parent_run_id": parent.run_id,
                "candidate_run_ids": [result["candidate_run_id"] for result in results],
                "validation_run_ids": [
                    result["validation_run_id"] for result in validation_results
                ],
                "fusion_validation_run_id": fusion_run.run_id,
                "stack_validation_run_id": stack["run_id"],
                "selected_fusion_candidate_ids": [
                    item["candidate"]["candidate_id"] for item in selected
                ],
                "test_csv_accessed": False,
            }
