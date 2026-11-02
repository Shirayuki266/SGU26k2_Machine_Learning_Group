"""T12 fixed-model ablation data, finite design and validation decision."""

import numpy as np
import pandas as pd
from pathlib import Path
from pandas.testing import assert_frame_equal

from beijing_air.data import sha256, MEASUREMENTS
from beijing_air.eda import read_json, load_training_data, project_path
from beijing_air.features import build_features, feature_registry
from beijing_air.initial_models import current_A, load_initial_data
from beijing_air.evaluation import load_validation_history


def validate_ablation(d, prep):
    ks, budget = d["selector"]["k_groups"], d["budget"]
    if (d["schema_version"] != "t12-group-ridge-v1" or d["model"] != "ridge" or d["alpha"] != 0.1
            or d["cohort"] != "primary" or d["selector"]["pilot_alpha"] != d["alpha"]
            or d["selector"]["method"] != "grouped_select_from_ridge"
            or not 1 <= len(ks) <= 3 or len(set(ks)) != len(ks) or any(type(k) is not int or not 1 <= k <= 33 for k in ks)):
        raise ValueError("Expected fixed Ridge alpha0.1/A-B-C and at most three valid group counts")
    if budget != {"full_searches": 1, "selector_candidates": len(ks), "folds": 3, "cv_pipeline_fits": len(ks)*3,
                  "cv_pilot_estimator_fits": len(ks)*3, "validation_pipeline_fits": 2,
                  "total_estimator_fits": len(ks)*6+3, "RF_fits": 0, "automatic_retries": 0}:
        raise ValueError("Finite T12 budget changed")
    selector_policy = {key: value for key, value in d["selector"].items() if key != "k_groups"}
    if selector_policy != {"method": "grouped_select_from_ridge", "score": "sqrt(mean(pilot_coef_squared_within_raw_feature_group))",
                           "categorical_policy": "keep_all_one_hot_columns_together", "indicator_policy": "same_group_as_source_numeric_feature",
                           "rank_tie_break": "T07_registry_order", "pilot_alpha": 0.1}:
        raise ValueError("Grouped selector definition changed")
    if d["selection"] != {"cv_metric": "pooled_MAE", "cv_tie_break": "fewer_groups", "tolerance": 1e-12,
                          "deployment_metric": "validation_MAE", "deployment_pool": ["A", "B", "C", "random_forest_A", "persistence"],
                          "deployment_tie_order": ["A", "random_forest_A", "B", "C", "persistence"]}:
        raise ValueError("Predeclared CV/deployment criteria changed")
    if (d["postprocessing"] != "identity_no_clipping" or d["save_model_weights"] is not False
            or d["resources"]["blas_threads"] != 1 or d["resources"]["execution"] != "sequential"
            or d["selection"]["cv_metric"] != "pooled_MAE" or d["selection"]["cv_tie_break"] != "fewer_groups"
            or d["selection"]["deployment_metric"] != "validation_MAE" or d["smoke"]["validation"] is not False
            or len(d["smoke"]["k_groups"]) != 1 or d["smoke"]["k_groups"][0] not in ks
            or prep["prediction_postprocessing"]["negative_predictions"] != "identity"):
        raise ValueError("Unexpected selection/resource/output policy")


def load_train_B(root):
    data, provenance = load_training_data(root)
    cfg = read_json(root / "configs/default.json")
    path = root / "reports/features_full/feature_manifest.json"
    manifest = read_json(path)
    signature = manifest["signature"]
    if (manifest["task_id"] != "T07" or manifest["mode"] != "full" or manifest["status"] != "complete"
            or manifest["fit_performed"] is not False or signature["train_provenance"] != provenance
            or signature["features"] != cfg["features"]
            or signature["module_sha256"] != sha256(Path(__import__("beijing_air.features", fromlist=["x"]).__file__))):
        raise ValueError("T07 feature provenance/config differs")
    info = manifest["files"]["train_B"]
    file = project_path(root, info["path"])
    if sha256(file) != info["sha256"] or file.stat().st_size != info["bytes"]:
        raise ValueError("T07 B checksum differs")
    x = pd.read_csv(file, index_col="sample_id", na_values=["NA"])
    if x.index.tolist() != data.sample_id.tolist() or list(x.columns) != feature_registry(cfg).feature_name.tolist():
        raise ValueError("T07 B IDs/schema differ from T05")
    data = data.loc[data.is_primary].reset_index(drop=True)
    x = x.loc[data.sample_id].copy()
    for name in ("station", "wd"): x[name] = x[name].astype("string")
    a = current_A(data, cfg)
    assert_frame_equal(x.loc[:, a.columns], a, check_dtype=False, rtol=1e-12, atol=1e-12)
    return data, x, {"train_provenance": provenance, "t07_manifest_sha256": sha256(path), "train_B": info,
                     "t07_snapshot_id": manifest["snapshot_id"]}


def B_from_pm_history(history, origins, config):
    """Past PM2.5 only; other measurements are needed at requested origins only."""
    current_columns = ["station", "input_timestamp", *[c for c in MEASUREMENTS if c != "PM2.5"], "wd"]
    current = origins[current_columns].rename(columns={"input_timestamp": "timestamp"})
    observations = history[["station", "timestamp", "PM2.5"]].merge(current, on=["station", "timestamp"], how="left", validate="one_to_one")
    result = build_features(observations, origins, config=config)
    assert_frame_equal(result.select("A"), current_A(origins, config), check_dtype=False, rtol=1e-12, atol=1e-12)
    return result.select("B")


def load_validation_B(root):
    sets, _, provenance, anchor, _ = load_initial_data(root, mode="full", design=read_json(root / "configs/initial_models.json"))
    history, scope = load_validation_history(root, sets["validation"], provenance)
    x = B_from_pm_history(history, sets["validation"], read_json(root / "configs/default.json"))
    return sets["validation"], x, {"provenance": provenance, "anchor": anchor, "history_scope": scope}


def choose_k(records, tolerance=1e-12):
    valid = [r for r in records if r["status"] == "completed" and len(r["fold_run_ids"]) == 3]
    if not valid: raise ValueError("No complete selection candidate; do not evaluate validation")
    best = min(r["summary"]["pooled"]["MAE"] for r in valid)
    return min((r for r in valid if r["summary"]["pooled"]["MAE"] <= best+tolerance), key=lambda r: r["k_groups"])


def choose_deployment(rows, design):
    expected = design["selection"]["deployment_pool"]
    if set(r["variant"] for r in rows) != set(expected):
        raise ValueError("Missing deployment comparator; do not silently narrow the pool")
    minimum = min(r["MAE"] for r in rows)
    tied = [r for r in rows if r["MAE"] <= minimum+design["selection"]["tolerance"]]
    return min(tied, key=lambda r: design["selection"]["deployment_tie_order"].index(r["variant"]))
