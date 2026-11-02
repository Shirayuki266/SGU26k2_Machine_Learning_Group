"""Bounded Ridge search design and metric aggregation; no validation selection."""

from copy import deepcopy

import numpy as np
import pandas as pd

from beijing_air.eda import load_training_data, read_json
from beijing_air.initial_models import current_A
from beijing_air.metrics import regression_metrics
from beijing_air.preprocessing import make_regression_pipeline


def validate_search(design, preprocessing):
    if (design["schema_version"] != "t11-ridge-A-v1" or design["model"] != "ridge"
            or design["feature_set"] != "A" or design["cohort"] != "primary"):
        raise ValueError("T11 execution fixes Ridge, A and primary cohort")
    alphas = design["alphas"]
    if (not 1 <= len(alphas) <= 4 or len(set(alphas)) != len(alphas)
            or any(isinstance(a, bool) or not np.isfinite(a) or a <= 0 for a in alphas)
            or 1.0 not in alphas):
        raise ValueError("At most four positive distinct alphas including the T10 alpha=1 control")
    budget = design["budget"]
    if budget != {"full_searches": 1, "candidates": len(alphas), "folds": 3,
                  "cv_fits": len(alphas)*3, "refits": 1, "automatic_retries": 0, "rf_fits": 0}:
        raise ValueError("Search budget must be fixed to one search and no automatic retries")
    if (design["selection"] != {"metric": "pooled_MAE", "tie_tolerance": 1e-12, "tie_break": "larger_alpha",
                               "std_ddof": 0, "failed_candidate": "exclude_unless_all_three_folds_completed"}
            or design["resources"]["blas_threads"] != 1 or design["resources"]["execution"] != "sequential"
            or design["save_model_weights"] is not False
            or design["smoke"]["alphas"] != [1.0] or design["smoke"]["refit_validation"] is not False
            or design["smoke"]["selection"] != "chronological_head_within_each_fold"
            or any(type(design["smoke"][k]) is not int or design["smoke"][k] < 1
                   for k in ("train_rows_per_station", "evaluation_rows_per_station"))):
        raise ValueError("Unexpected selection/resource/smoke/model-saving policy")
    if preprocessing["prediction_postprocessing"] != {"negative_predictions": "identity", "applies_to": ["persistence", "ridge", "random_forest"]}:
        raise ValueError("Keep the shared no-clipping policy")


def load_cv_training(root):
    data, provenance = load_training_data(root)
    if provenance["source_mode"] != "full":
        raise ValueError("Tuning requires the verified full T05 train snapshot")
    data = data.loc[data.is_primary].reset_index(drop=True)
    config = read_json(root / "configs/default.json")
    return data, current_A(data, config), provenance


def ridge_pipeline(alpha, config, preprocessing):
    effective = deepcopy(config)
    effective["evaluation"]["initial_parameters"]["ridge"] = {"alpha": float(alpha)}
    return make_regression_pipeline("ridge", feature_set="A", config=effective, preprocessing_config=preprocessing)


def aggregate_folds(predictions):
    if len(predictions) != 3 or any(p.empty for p in predictions):
        raise ValueError("A candidate needs exactly three successful folds")
    pooled = pd.concat(predictions, ignore_index=True)
    if not pooled.sample_id.is_unique:
        raise ValueError("Out-of-fold sample IDs overlap")
    fold_metrics = [regression_metrics(p.y_true, p.y_pred) for p in predictions]
    summary = {"pooled": regression_metrics(pooled.y_true, pooled.y_pred), "folds": fold_metrics,
               "fold_mean": {}, "fold_std": {}, "std_ddof": 0,
               "R2_defined_folds": sum(m["R2"] is not None for m in fold_metrics)}
    for metric in ("MAE", "RMSE", "R2"):
        values = [m[metric] for m in fold_metrics]
        summary["fold_mean"][metric] = float(np.mean(values)) if all(v is not None for v in values) else None
        summary["fold_std"][metric] = float(np.std(values, ddof=0)) if all(v is not None for v in values) else None
    return summary


def choose_candidate(candidates, tolerance=1e-12):
    complete = [c for c in candidates if c["status"] == "completed" and len(c["fold_run_ids"]) == 3
                and c.get("summary", {}).get("pooled", {}).get("MAE") is not None]
    if not complete:
        raise ValueError("No complete candidate; retain failures and do not evaluate validation")
    minimum = min(c["summary"]["pooled"]["MAE"] for c in complete)
    tied = [c for c in complete if c["summary"]["pooled"]["MAE"] <= minimum+tolerance]
    return max(tied, key=lambda c: c["alpha"])
