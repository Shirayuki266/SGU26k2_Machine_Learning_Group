"""T10 data/pipeline helpers: current feature A, primary train/validation only."""

from copy import deepcopy
import ctypes
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from beijing_air.data import MEASUREMENTS, sha256
from beijing_air.eda import ids_digest, project_path, read_json
from beijing_air.evaluation import load_train_validation, freeze_validation_ids
from beijing_air.features import build_features, feature_registry
from beijing_air.preprocessing import make_regression_pipeline, FeatureSchema


def validate_design(design, preprocessing):
    if design["schema_version"] != "t10-initial-A-v1" or design["feature_set"] != "A" or design["cohort"] != "primary":
        raise ValueError("T10 supports only the agreed initial A/primary experiment")
    if design["budget"] != {"max_full_runs_per_model": 1, "smoke_required": True, "tuning": False}:
        raise ValueError("T10 budget must be one full per model, after smoke, without tuning")
    if set(design["models"]) != {"ridge", "random_forest"} or design["save_model_weights"] is not False:
        raise ValueError("Expected two initial models and state summaries only, not saved weights")
    rf = design["models"]["random_forest"]
    if not (type(rf["n_estimators"]) is int and 1 <= rf["n_estimators"] <= 100
            and type(rf["max_depth"]) is int and 1 <= rf["max_depth"] <= 12 and rf["n_jobs"] == 1):
        raise ValueError("RF resource cap exceeded")
    if design["resources"]["blas_threads"] != 1 or design["resources"]["execution"] != "sequential":
        raise ValueError("Initial models must use one BLAS thread and run sequentially")
    if design["smoke"]["selection"] != "chronological_head_after_primary_filter":
        raise ValueError("Unknown smoke selection")
    if any(type(design["smoke"][k]) is not int or design["smoke"][k] < 1 for k in ("train_rows_per_station", "validation_rows_per_station")):
        raise ValueError("Invalid smoke row limit")
    if preprocessing["prediction_postprocessing"] != {"negative_predictions": "identity", "applies_to": ["persistence", "ridge", "random_forest"]}:
        raise ValueError("Initial models must preserve the shared no-clipping policy")


def available_memory_mb():
    if os.name != "nt":
        return None
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    *[(name, ctypes.c_ulonglong) for name in ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended")]]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("Cannot read available memory")
    return status.avail_phys / 1024**2


def current_A(samples, config):
    """Reuse T07 implementation; A needs only each observed origin, not history.

    T07's general builder also computes B from the supplied observation buffer.
    Those B columns are discarded: this helper never exposes/saves B, and must
    not be used for historical feature experiments. Future B requires T04's
    full causal timeline. A is invariant to omitted unrequested history.
    """
    observations = samples[["station", "input_timestamp", *MEASUREMENTS, "wd"]].rename(columns={"input_timestamp": "timestamp"})
    result = build_features(observations, samples, config=config)
    return result.select("A")


def load_initial_data(root, *, mode, design):
    root = Path(root).resolve()
    if mode not in ("smoke", "full"):
        raise ValueError("Mode must be smoke/full")
    train, validation, provenance = load_train_validation(root)
    anchor_path, anchor = freeze_validation_ids(root, validation, provenance)
    manifest = read_json(project_path(root, provenance["split_manifest"]))
    selected, features = {}, {}
    config = read_json(root / "configs/default.json")
    columns = ["sample_id", "station", "input_timestamp", "target_timestamp", "is_primary", "split", "target_pm25", *MEASUREMENTS, "wd"]
    for name, meta in (("train", train), ("validation", validation)):
        info = manifest["files"][f"{name}_samples"]
        path = project_path(root, info["path"])
        if path.name != f"{name}.csv":
            raise ValueError("Only train/validation samples are allowed")
        frame = pd.read_csv(path, usecols=columns, na_values=["NA"], parse_dates=["input_timestamp", "target_timestamp"])
        if sha256(path) != info["sha256"] or frame.sample_id.tolist() != meta.sample_id.tolist():
            raise ValueError("Samples changed after verified T05 load")
        frame = frame.loc[frame.is_primary].reset_index(drop=True)
        expected = manifest["membership"][name]["primary"]
        if len(frame) != expected["samples"] or ids_digest(frame.sample_id) != expected["ordered_sample_ids_sha256"]:
            raise ValueError("Primary membership differs from T05")
        if mode == "smoke":
            frame = frame.groupby("station", sort=True).head(design["smoke"][f"{name}_rows_per_station"]).reset_index(drop=True)
        if frame.empty:
            raise ValueError("Empty primary partition")
        selected[name] = frame
        features[name] = current_A(frame, config)
        if features[name].index.tolist() != frame.sample_id.tolist():
            raise ValueError("Feature IDs changed")
    return selected, features, provenance, anchor, sha256(anchor_path)


def effective_pipeline(model_name, config, design, preprocessing):
    if model_name not in design["models"]:
        raise ValueError("Unknown initial model")
    effective = deepcopy(config)
    effective["evaluation"]["initial_parameters"][model_name] = deepcopy(design["models"][model_name])
    return make_regression_pipeline(model_name, feature_set="A", config=effective, preprocessing_config=preprocessing), effective


def fitted_summary(pipeline, model_name):
    """Record actual pipeline structure/statistics, not deployable model weights."""
    if not isinstance(pipeline, Pipeline) or list(pipeline.named_steps) != ["preprocess", "model"]:
        raise ValueError("Expected full T08 regression pipeline")
    pre = pipeline.named_steps["preprocess"]
    if not isinstance(pre.named_steps["schema"], FeatureSchema) or not isinstance(pre.named_steps["columns"], ColumnTransformer):
        raise ValueError("Schema/ColumnTransformer bypassed")
    columns = pre.named_steps["columns"]
    numeric = columns.named_transformers_["numeric"]
    categorical = columns.named_transformers_["categorical"]
    if not isinstance(numeric.named_steps["impute"], SimpleImputer) or not isinstance(categorical.named_steps["one_hot"], OneHotEncoder):
        raise ValueError("Expected T08 imputation/encoding")
    scale = numeric.named_steps["scale"]
    if (model_name == "ridge" and not isinstance(scale, StandardScaler)) or (model_name == "random_forest" and scale != "passthrough"):
        raise ValueError("Wrong model scaling")
    if not isinstance(columns.named_transformers_["missing"], MissingIndicator):
        raise ValueError("Missing indicators bypassed")
    model = pipeline.named_steps["model"]
    summary = {"artifact_type": "fitted_pipeline_summary_not_model_weights", "model": model_name,
               "pipeline_class": f"{type(pipeline).__module__}.{type(pipeline).__name__}",
               "model_class": f"{type(model).__module__}.{type(model).__name__}", "parameters": model.get_params(),
               "input_feature_names": pre.named_steps["schema"].get_feature_names_out().tolist(),
               "output_feature_names": pre.get_feature_names_out().tolist(), "model_n_features_in": int(model.n_features_in_),
               "numeric_features": list(columns.transformers_[0][2]),
               "numeric_imputation_statistics": numeric.named_steps["impute"].statistics_.tolist(),
               "categorical_features": list(next(t[2] for t in columns.transformers_ if t[0] == "categorical")),
               "categories": [values.tolist() for values in categorical.named_steps["one_hot"].categories_],
               "fitted_object_hash": joblib.hash(pipeline), "weights_saved": False}
    if model_name == "ridge":
        summary.update(scaler_mean=scale.mean_.tolist(), scaler_scale=scale.scale_.tolist(),
                       coef=model.coef_.tolist(), intercept=float(model.intercept_))
    else:
        summary.update(n_estimators_fitted=len(model.estimators_), feature_importances=model.feature_importances_.tolist(),
                       total_tree_nodes=sum(t.tree_.node_count for t in model.estimators_),
                       maximum_tree_depth=max(t.tree_.max_depth for t in model.estimators_))
    if summary["model_n_features_in"] != len(summary["output_feature_names"]):
        raise ValueError("Model schema differs from preprocessing")
    return summary


def prediction_frame(meta, prediction, run_id, model_name):
    values = np.asarray(prediction, dtype=float)
    if values.ndim != 1 or len(values) != len(meta) or not np.isfinite(values).all():
        raise ValueError("Incomplete/nonfinite model predictions")
    result = meta[["sample_id", "station", "input_timestamp", "target_timestamp", "is_primary", "split"]].copy()
    result["y_true"], result["y_pred"] = meta.target_pm25.to_numpy(), values
    result["residual"] = result.y_pred-result.y_true
    result["run_id"], result["model"] = run_id, model_name
    return result
