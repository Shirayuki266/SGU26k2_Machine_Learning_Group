"""Recompute T13 artifacts without fit, retuning, or reopening input test CSV."""

import csv
import io
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

from beijing_air.data import sha256
from beijing_air.eda import ids_digest,read_json,project_path
from beijing_air.final_evaluation import analysis_labels,grouped_results,scores,validate_frozen,write_json


def main():
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    root=Path(__file__).resolve().parents[1]
    out=root / "reports/final_evaluation"
    state=read_json(out / "execution.json")
    design=read_json(root / "configs/final_evaluation.json")
    if state["status"]!="completed" or not state["test_samples_accessed"]:
        raise ValueError("Expected completed and honestly exposed final test")
    frozen,_=validate_frozen(root,design)
    if state["selected_reference_run_id"]!=frozen["selected_run_id"] or state["selected_by"]!="development_validation_MAE":
        raise ValueError("Deployment selection changed after test")
    parent=root / "artifacts/experiments" / state["parent_run_id"]
    history=read_json(parent / "artifacts/data/history_before.json")
    for name,expected in history.items():
        if sha256(project_path(root,name))!=expected:raise ValueError("Historical run changed")
    old=list(csv.DictReader(io.StringIO((parent / "artifacts/data/development_ledger_before.csv").read_text(encoding="utf-8"))))
    current=list(csv.DictReader((root / "experiments/experiment_log.csv").open(encoding="utf-8",newline="")))
    indexed={r["run_id"]:r for r in current}
    if len(indexed)!=len(current) or any(indexed[r["run_id"]]!=r for r in old):
        raise ValueError("Historical CSV rows changed or duplicate IDs")
    files=0;pred_files=0;model_weights=0
    pred_by_part={"test":{},"refit":{}}
    for model,rid in {"parent":state["parent_run_id"],**state["child_run_ids"]}.items():
        d=root / "artifacts/experiments" / rid
        meta,cfg,metrics=(read_json(d/(k+".json")) for k in ("metadata","config","metrics"))
        if meta["status"]!="completed" or cfg["task_id"]!="T13" or cfg["is_test"]:
            raise ValueError("Run incomplete or synthetic")
        for info in meta["artifacts"]:
            p=project_path(root,Path("experiments") / info["path"])
            if not p.is_relative_to(d) or sha256(p)!=info["sha256"] or p.stat().st_size!=info["size_bytes"]:
                raise ValueError("Registered artifact changed")
            if model=="parent" and p.parent.name=="tables":
                if sha256(out/p.name)!=info["sha256"]:raise ValueError("Working result table differs from registered snapshot")
            if model=="parent" and p.parent.name=="figures":
                if sha256(root/"reports/figures/final_evaluation"/p.name)!=info["sha256"]:raise ValueError("Working PNG differs from registered snapshot")
            files+=1
        if model=="parent":continue
        if cfg["reference_run_id"]!=design["models"][model]["reference_run_id"]:
            raise ValueError("Development comparator reference changed")
        if model!="persistence":
            pipeline=joblib.load(d / "artifacts/model/pipeline.joblib")
            if pipeline.named_steps["model"].get_params()!=design["models"][model]["parameters"]:
                raise ValueError("Saved estimator differs from frozen parameters")
            if len(pipeline.named_steps["preprocess"].get_feature_names_out())!=pipeline.named_steps["model"].n_features_in_:
                raise ValueError("Model/feature names differ")
            model_weights+=1
        for part in ("refit","test"):
            pred=pd.read_csv(d / f"artifacts/predictions/{part}.csv.gz",parse_dates=["input_timestamp","target_timestamp"])
            if not pred.sample_id.is_unique or not pred.run_id.eq(rid).all() or not pred.is_primary.all():
                raise ValueError("Prediction membership invalid")
            if not pred.target_timestamp.sub(pred.input_timestamp).eq(pd.Timedelta(hours=1)).all():
                raise ValueError("Prediction horizon changed")
            np.testing.assert_allclose(pred.residual,pred.y_pred-pred.y_true,rtol=1e-10,atol=1e-10)
            pred_by_part[part][model]=pred
            pred_files+=1
    for part,frames in pred_by_part.items():
        baseline=frames["persistence"]
        for model,frame in frames.items():
            if frame.sample_id.tolist()!=baseline.sample_id.tolist():raise ValueError("Models use different IDs")
            np.testing.assert_array_equal(frame.y_true,baseline.y_true)
            if not frame.sample_id.is_unique:raise ValueError("Duplicate predictions")
            recorded=read_json(root / "artifacts/experiments" / state["child_run_ids"][model] / "metrics.json")
            key="test_primary" if part=="test" else "refit_train_validation"
            actual=scores(frame.y_true,frame.y_pred,baseline.y_pred)
            for k,v in actual.items():
                expected=recorded[key][k]
                if isinstance(v,(int,float)) and not isinstance(v,bool):
                    if not np.isclose(v,expected,rtol=1e-10,atol=1e-10):raise ValueError(f"Metric differs: {model}/{part}/{k}")
                elif v!=expected:raise ValueError("Metric null/reason differs")
    test=pred_by_part["test"]["persistence"]
    anchor=read_json(out / "test_manifest.json")
    if len(test)!=anchor["N"] or ids_digest(test.sample_id)!=anchor["ordered_ids_sha256"]:
        raise ValueError("Frozen test identity differs")
    comparison=pd.read_csv(out/"comparison.csv").set_index("model")
    for model,rid in state["child_run_ids"].items():
        metrics=read_json(root/"artifacts/experiments"/rid/"metrics.json")["test_primary"]
        if comparison.loc[model,"run_id"]!=rid:raise ValueError("Comparison run ID differs")
        for key in ("MAE","RMSE","R2","mae_reduction_vs_persistence_pct"):
            if not np.isclose(comparison.loc[model,key],metrics[key],rtol=1e-10,atol=1e-10):raise ValueError("Comparison differs from actual model metric")
    handoff=read_json(out/"final_model.json")
    if (handoff["final_run_id"]!=state["child_run_ids"]["random_forest"] or handoff["test_used_for_selection"]
            or not handoff["test_has_been_exposed"] or handoff["selected_development_run_id"]!=frozen["selected_run_id"]
            or sha256(project_path(root,handoff["weights"]["path"]))!=handoff["weights"]["sha256"]):
        raise ValueError("Final handoff differs from validation-selected model")
    fit=pred_by_part["refit"]["persistence"]
    if set(fit.sample_id)&set(test.sample_id) or fit.target_timestamp.max()>test.input_timestamp.min():
        raise ValueError("Fit/test overlap or labels unavailable")
    audit=read_json(parent / "artifacts/data/preflight.json")
    meta=test.rename(columns={"y_true":"target_pm25","y_pred":"PM2.5"})
    labels=analysis_labels(meta,design,audit["rapid_change_threshold_train_q95"])
    groups=grouped_results(labels,{k:f.y_pred.to_numpy() for k,f in pred_by_part["test"].items()},design)
    stored=pd.read_csv(out / "grouped_metrics.csv")
    for frame in (groups,stored):frame["value"]=frame["value"].astype(str)
    pd.testing.assert_frame_equal(groups,stored,check_dtype=False,rtol=1e-9,atol=1e-9)
    permutation_ids=pd.read_csv(out / "rf_permutation_ids.csv")
    if not permutation_ids.sample_id.is_unique or not set(permutation_ids.sample_id).issubset(set(test.sample_id)) or len(permutation_ids)>2400:
        raise ValueError("Permutation budget/IDs invalid")
    result={"status":"PASS","task_id":"T13","parent_run_id":state["parent_run_id"],"runs":4,"registered_artifacts_checked":files,
            "prediction_files_recomputed":pred_files,"saved_models_checked":model_weights,"test_primary_samples":len(test),
            "same_test_ids":True,"selection_from_development":True,"old_run_files_unchanged":len(history),"old_csv_rows_unchanged":len(old),
            "group_metrics_recomputed":len(stored),"model_fit_performed":False,"input_test_csv_reopened":False,
            "test_has_been_exposed":True,"weights_note":"Saved models were serialized/reloaded and reproduced all test predictions exactly inside the actual run."}
    write_json(out / "verification.json",result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":main()
