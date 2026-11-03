"""T13 locked evaluation. Preflight never reads test; execution records exposure."""

from copy import deepcopy
import csv
from datetime import datetime, timezone
import gc
import io
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from beijing_air.data import sha256
from beijing_air.eda import ids_digest, read_json, project_path
from beijing_air.experiment_logging import ExperimentLogger
from beijing_air.features import _requests
from beijing_air.initial_models import current_A, available_memory_mb, prediction_frame, fitted_summary
from beijing_air.metrics import regression_metrics
from beijing_air.preprocessing import make_regression_pipeline
from beijing_air.samples import ID_COLUMNS


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def reduction(model_mae, baseline_mae):
    if model_mae is None or baseline_mae is None or baseline_mae <= 0:
        return None
    return 100*(baseline_mae-model_mae)/baseline_mae


def scores(truth, prediction, baseline, *, min_r2_n=2):
    result = regression_metrics(truth, prediction)
    result["mae_reduction_vs_persistence_pct"] = reduction(result["MAE"], regression_metrics(truth, baseline)["MAE"])
    if result["n_scored"] < min_r2_n:
        result.update(R2=None, r2_undefined_reason=f"group_n_below_{min_r2_n}")
    return result


def validate_frozen(root, design):
    root = Path(root)
    if design["schema_version"] != "t13-final-v1" or design["feature_set"] != "A" or design["cohort"] != "primary":
        raise ValueError("Expected locked A/primary T13 protocol")
    for name, expected in design["files_sha256"].items():
        if sha256(project_path(root, name)) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    frozen = read_json(project_path(root, design["frozen"]))
    cfg = read_json(root / "configs/default.json")
    required = {"data", "features", "preprocessing", "model", "postprocessing", "selection"}
    if not required.issubset(frozen) or frozen["status"] != "locked_recipe_for_future_refit":
        raise ValueError("Missing complete frozen recipe")
    if (frozen["selected_variant"] != "random_forest_A" or frozen["selected_run_id"] != design["development_selected_run_id"]
            or frozen["selection"]["deployment_metric"] != "validation_MAE"
            or frozen["features"]["definitions"] != cfg["features"]
            or frozen["preprocessing"] != design["preprocessing"]
            or frozen["model"]["parameters"] != design["models"]["random_forest"]["parameters"]
            or design["postprocessing"] != "identity"
            or frozen["postprocessing"]["negative_predictions"] != "identity"):
        raise ValueError("Effective recipe differs from development lock")
    best = min(frozen["validation_results"], key=lambda row: row["MAE"])
    if best["run_id"] != frozen["selected_run_id"]:
        raise ValueError("Selected model not supported by validation")
    for name, spec in design["models"].items():
        d = root / "artifacts/experiments" / spec["reference_run_id"]
        ref, meta = read_json(d / "config.json"), read_json(d / "metadata.json")
        if meta["status"] != "completed" or ref["mode"] != "full" or ref["is_test"]:
            raise ValueError("Missing real full development reference")
        if name != "persistence":
            if ref["feature_set"] != "A" or ref["preprocessing"] != design["preprocessing"]:
                raise ValueError("Comparator schema changed")
            actual = ref["parameters"].get("actual_model_parameters")
            # T10 freezes full actual parameters in its execution signature.
            if actual is None:
                actual = ref["parameters"]["signature"]["effective_model_parameters"]
            if actual != spec["parameters"]:
                raise ValueError(f"{name} parameters differ from reference")
    return frozen, cfg


def load_partition(root, manifest, name):
    """Only callers behind the exposure audit may request name='test'."""
    info, ids_info = (manifest["files"][f"{name}_{kind}"] for kind in ("samples", "ids"))
    paths = [project_path(root, i["path"]) for i in (info, ids_info)]
    for path, item in zip(paths, (info, ids_info)):
        if path.name != name+".csv" or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"T05 {name} checksum differs")
    data = pd.read_csv(paths[0], na_values=["NA"], parse_dates=["input_timestamp", "target_timestamp"])
    ids = pd.read_csv(paths[1], parse_dates=["input_timestamp", "target_timestamp"])
    _requests(data)
    if not data[ID_COLUMNS].equals(ids[ID_COLUMNS]) or not data.split.eq(name).all():
        raise ValueError("T05 sample identity differs")
    if data.target_pm25.isna().any() or not np.isfinite(data.target_pm25).all() or data.target_pm25.lt(0).any():
        raise ValueError("Target must be observed, finite and nonnegative")
    if not data.is_primary.equals(data["PM2.5"].notna()):
        raise ValueError("Primary flag differs")
    split = manifest["signature"]["split"]
    lower = split["validation_start"] if name == "validation" else split["test_start"] if name == "test" else None
    upper = split["validation_start"] if name == "train" else split["test_start"] if name == "validation" else None
    if ((lower and not data.target_timestamp.ge(pd.Timestamp(lower)).all())
            or (upper and not data.target_timestamp.lt(pd.Timestamp(upper)).all())):
        raise ValueError("Temporal boundary differs")
    for cohort, part in (("operational", data), ("primary", data.loc[data.is_primary])):
        expected = manifest["membership"][name][cohort]
        if len(part) != expected["samples"] or ids_digest(part.sample_id) != expected["ordered_sample_ids_sha256"]:
            raise ValueError("T05 cohort differs")
    return data.loc[data.is_primary].reset_index(drop=True)


def development_data(root, design):
    frozen, cfg = validate_frozen(root, design)
    manifest = read_json(Path(root) / "reports/splits_full/split_manifest.json")
    train, val = [load_partition(root, manifest, s) for s in ("train", "validation")]
    for name, frame in (("train", train), ("validation", val)):
        if ids_digest(frame.sample_id) != frozen["data"][name]["ordered_ids_sha256"]:
            raise ValueError("Development IDs differ from frozen record")
    fit = pd.concat([train, val], ignore_index=True).sort_values(["station", "input_timestamp"], kind="stable").reset_index(drop=True)
    if not fit.sample_id.is_unique or fit.target_timestamp.max() > pd.Timestamp(cfg["split"]["test_start"])-pd.Timedelta(hours=1):
        raise ValueError("Refit labels not available at first test origin")
    delta = np.abs(train.target_pm25-train["PM2.5"])
    audit = {"test_samples_accessed": False, "train_rows": len(train), "validation_rows": len(val), "refit_rows": len(fit),
             "ordered_refit_ids_sha256": ids_digest(fit.sample_id),
             "latest_fit_target": str(fit.target_timestamp.max()),
             "planned_first_test_origin": str(pd.Timestamp(cfg["split"]["test_start"])-pd.Timedelta(hours=1)),
             "label_rule": "latest_fit_target <= first_test_origin; observation at origin already available",
             "rapid_change_threshold_train_q95": float(delta.quantile(design["analysis"]["rapid_change_training_quantile"])),
             "train_concentration_counts": pd.cut(train.target_pm25, [0,35,75,150,np.inf], right=False).value_counts(sort=False).astype(int).rename(index=str).to_dict()}
    return cfg, manifest, train, val, fit, audit


def episode_ids(meta, threshold, min_hours):
    """Observed consecutive target hours per station. Gaps break episodes."""
    result = pd.Series(None, index=meta.index, dtype=object)
    for station, part in meta.groupby("station", sort=True):
        part = part.sort_values("target_timestamp")
        high = part.loc[part.target_pm25.ge(threshold)]
        groups = high.target_timestamp.diff().ne(pd.Timedelta(hours=1)).cumsum()
        for _, event in high.groupby(groups):
            if len(event) >= min_hours:
                label = station+"__"+event.target_timestamp.iloc[0].strftime("%Y%m%dT%H")
                result.loc[event.index] = label
    return result


def analysis_labels(meta, design, rapid_threshold):
    out = meta.copy()
    month = out.target_timestamp.dt.month
    out["season"] = month.map({12:"DJF",1:"DJF",2:"DJF",3:"MAM",4:"MAM",5:"MAM",6:"JJA",7:"JJA",8:"JJA",9:"SON",10:"SON",11:"SON"})
    out["concentration"] = pd.cut(out.target_pm25, [*design["analysis"]["concentration_edges"],np.inf], right=False).astype(str)
    out["rapid_change"] = np.abs(out.target_pm25-out["PM2.5"]).ge(rapid_threshold)
    out["episode_id"] = episode_ids(out, design["analysis"]["episode_threshold"], design["analysis"]["episode_min_hours"])
    return out


def grouped_results(meta, predictions, design):
    rows = []
    for column in ("station", "season", "concentration", "rapid_change", "episode_id"):
        for value, part in meta.groupby(column, sort=True, observed=True):
            ix = part.index.to_numpy()
            for model, pred in predictions.items():
                rows.append({"group": column, "value": str(value), "model": model,
                             **scores(part.target_pm25, pred[ix], part["PM2.5"], min_r2_n=design["analysis"]["group_r2_min_n"]),
                             "mean_signed_error": float(np.mean(pred[ix]-part.target_pm25))})
    return pd.DataFrame(rows)


def permutation_groups(X):
    groups = {}
    used = set()
    for name in ("target_hour", "target_month"):
        columns = [c for c in X if c == name or c.startswith(name+"_")]
        if columns: groups[name] = columns; used.update(columns)
    groups.update({c:[c] for c in X if c not in used})
    return groups


def permutation_diagnostic(pipeline, X, meta, design):
    selected = []
    for _, part in meta.groupby("station", sort=True):
        count = min(len(part), design["analysis"]["permutation_rows_per_station"])
        selected.extend(part.index.to_numpy()[np.linspace(0,len(part)-1,count,dtype=int)])
    selected = np.asarray(selected, dtype=int)
    frame = X.iloc[selected].copy()
    truth = meta.target_pm25.iloc[selected].to_numpy()
    base = regression_metrics(truth, pipeline.predict(frame))["MAE"]
    rng = np.random.default_rng(design["analysis"]["permutation_seed"])
    rows = []
    for name, columns in permutation_groups(frame).items():
        values = []
        for repeat in range(design["analysis"]["permutation_repeats"]):
            shuffled = frame.copy()
            shuffled.loc[:,columns] = frame.iloc[rng.permutation(len(frame))][columns].to_numpy()
            mae = regression_metrics(truth, pipeline.predict(shuffled))["MAE"]
            values.append(mae-base)
            rows.append({"group": name, "columns": ";".join(columns), "repeat": repeat+1, "n":len(frame), "baseline_MAE":base, "MAE_increase":mae-base})
    return pd.DataFrame(rows), meta.iloc[selected][["sample_id","station","target_timestamp"]]


def coefficient_table(pipeline):
    pre, model = pipeline.named_steps["preprocess"], pipeline.named_steps["model"]
    names = pre.get_feature_names_out()
    scale = pre.named_steps["columns"].named_transformers_["numeric"].named_steps["scale"].scale_
    rows = []
    numeric_index = 0
    for name, value in zip(names, model.coef_):
        raw_value = None
        if name.startswith("numeric__"):
            raw_value = float(value/scale[numeric_index]); numeric_index += 1
        rows.append({"encoded_feature": name, "coefficient_model_space": float(value),
                     "coefficient_per_raw_unit_if_numeric": raw_value,
                     "note":"conditional association, not causation; scale/encoding/correlated inputs limit magnitude comparisons"})
    return pd.DataFrame(rows)


def preflight(root):
    root = Path(root)
    design = read_json(root / "configs/final_evaluation.json")
    _, _, _, _, _, audit = development_data(root, design)
    audit["status"] = "passed"
    audit["config_sha256"] = sha256(root / "configs/final_evaluation.json")
    return audit


def execute(root, *, retry_reason=None):
    """Exclusive claim prevents two concurrent final test attempts."""
    folder=Path(root).resolve() / "reports/final_evaluation"
    folder.mkdir(parents=True,exist_ok=True)
    claim=folder / ".execution_claim"
    try:
        with claim.open("x",encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
    except FileExistsError:
        raise RuntimeError("T13 execution claim exists; do not run concurrently or erase exposure history")
    try:
        return _execute(root,retry_reason=retry_reason)
    finally:
        claim.unlink()


def _execute(root, *, retry_reason=None):
    root = Path(root).resolve()
    design = read_json(root / "configs/final_evaluation.json")
    cfg, manifest, train, val, fit, audit = development_data(root, design)
    out = root / "reports/final_evaluation"
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / "execution.json"
    if state_path.exists():
        previous = read_json(state_path)
        if previous["status"] != "failed" or not retry_reason or not retry_reason.strip():
            raise RuntimeError("T13 already attempted; no automatic repeat. Failed technical retries require a reason.")
        if previous["config_sha256"] != sha256(root / "configs/final_evaluation.json"):
            raise ValueError("Cannot change configuration after test exposure")
    elif retry_reason:
        raise ValueError("No failed attempt to retry")
    # Require the implementation/config to be committed before any test access.
    status = subprocess.check_output(["git","status","--porcelain","--","src/beijing_air/final_evaluation.py","src/beijing_air/final_reporting.py","configs/final_evaluation.json","scripts/run_final_evaluation.py","scripts/verify_final_evaluation.py"],cwd=root,text=True)
    if status.strip(): raise RuntimeError("Commit implementation and locked design before test")
    memory = available_memory_mb()
    if memory is not None and memory < design["budget"]["min_free_memory_mb"]:
        raise MemoryError("Insufficient memory; test not opened")
    stamp = uuid4().hex
    scratch = root / "artifacts/t13_runtime" / stamp
    scratch.mkdir(parents=True)
    logger = ExperimentLogger(project_root=root)
    evaluation_split = {**cfg["split"],"test_locked":False,"test_authorized_by":"explicit T13 user task; exposure audit persisted before access"}
    old_rows_path = root / "experiments/experiment_log.csv"
    old_ledger_bytes = old_rows_path.read_bytes()
    old_rows = list(csv.DictReader(io.StringIO(old_ledger_bytes.decode("utf-8"))))
    history = {f"artifacts/experiments/{r['run_id']}/{n}":sha256(root / "artifacts/experiments" / r["run_id"] / n)
               for r in old_rows for n in ("config.json","metrics.json","metadata.json","notes.md")}
    state = {"attempt":stamp,"status":"running","config_sha256":sha256(root / "configs/final_evaluation.json"),
             "retry_reason":retry_reason,"test_samples_accessed":False,"child_run_ids":{},"selected_model":"random_forest",
             "selected_by":"development_validation_MAE","selected_reference_run_id":design["development_selected_run_id"]}
    parent = logger.start_run(task_id="T13", reference_run_id=design["development_selected_run_id"], mode="full",kind="train",model="locked_final_comparison",
        objective="Final held-out test evaluation of development-frozen models; deployment selection remains RF A regardless of test ordering.",
        hypothesis="Assess development generalization and error regimes without test-driven selection.",
        parameters={"design":design,"technical_retry_reason":retry_reason},feature_set="A",preprocessing=design["preprocessing"],
        data={"split_manifest_sha256":sha256(root / "reports/splits_full/split_manifest.json"),"preflight":audit},
        split=evaluation_split,seed=42,budget=design["budget"],is_test=False,source="executed_T13_final_test",
        notes="is_test=False denotes a REAL experiment, not a synthetic logger test. Evaluation partition is held-out test. No tuning.")
    state["parent_run_id"] = parent.run_id
    write_json(state_path,state)
    try:
        with parent, threadpool_limits(limits=1):
            (scratch / "development_ledger_before.csv").write_bytes(old_ledger_bytes)
            parent.log_artifact(scratch / "development_ledger_before.csv",name="data/development_ledger_before.csv")
            write_json(scratch / "history_before.json",history)
            parent.log_artifact(scratch / "history_before.json",name="data/history_before.json")
            parent.log_artifact(root / "configs/final_evaluation.json",name="config/final_evaluation.json")
            write_json(scratch / "preflight.json",audit)
            parent.log_artifact(scratch / "preflight.json",name="data/preflight.json")
            for filename in ("final_evaluation.py","final_reporting.py"):
                parent.log_artifact(root / "src/beijing_air" / filename,name="source/"+filename)
            # Persist exposure BEFORE opening even test byte hashes/IDs. Never reset it.
            state.update(test_samples_accessed=True,first_test_access_at=datetime.now(timezone.utc).isoformat())
            write_json(state_path,state)
            test = load_partition(root,manifest,"test")
            if set(fit.sample_id)&set(test.sample_id) or fit.target_timestamp.max()>test.input_timestamp.min():
                raise ValueError("Refit/test leakage")
            anchor={"cohort":"primary","N":len(test),"ordered_ids_sha256":ids_digest(test.sample_id),
                    "source":manifest["files"]["test_ids"],"first_target":str(test.target_timestamp.min()),"last_target":str(test.target_timestamp.max()),
                    "selection":"is_primary; all three models use identical IDs; no dropping missing features"}
            write_json(out / "test_manifest.json",anchor)
            parent.log_artifact(out / "test_manifest.json",name="data/test_manifest.json")
            test[ID_COLUMNS].to_csv(scratch / "test_primary_ids.csv.gz",index=False,compression="gzip")
            parent.log_artifact(scratch / "test_primary_ids.csv.gz",name="data/test_primary_ids.csv.gz")
            X_fit, X_test = current_A(fit,cfg), current_A(test,cfg)
            labeled = analysis_labels(test,design,audit["rapid_change_threshold_train_q95"])
            predictions, rows, child_metrics = {}, [], {}
            for model_name,spec in design["models"].items():
                print("START",model_name,flush=True)
                child = logger.start_run(task_id="T13",parent_run_id=parent.run_id,reference_run_id=spec["reference_run_id"],mode="full",
                    kind="baseline" if model_name=="persistence" else "train",model=model_name,parameters={"locked_parameters":spec["parameters"],"stage":"final_refit_test","postprocessing":"identity"},
                    feature_set="A",preprocessing=design["preprocessing"] if model_name!="persistence" else None,
                    data={"test_anchor":anchor,"preflight":audit},split=evaluation_split,sample_counts={"fit":len(fit),"test":len(test)},seed=42,
                    budget={"fits":0 if model_name=="persistence" else 1,"test_configurations":1},is_test=False,source="executed_T13_final_test")
                state["child_run_ids"][model_name]=child.run_id
                write_json(state_path,state)
                with child:
                    started=time.perf_counter()
                    if model_name=="persistence":
                        fit_pred, pred=fit["PM2.5"].to_numpy(),test["PM2.5"].to_numpy()
                        fit_seconds=0.
                        write_json(scratch / "persistence.json",spec)
                        child.log_artifact(scratch / "persistence.json",name="model/persistence.json")
                    else:
                        effective=deepcopy(cfg)
                        effective["evaluation"]["initial_parameters"][model_name]=spec["parameters"]
                        pipeline=make_regression_pipeline(model_name,feature_set="A",config=effective,preprocessing_config=design["preprocessing"])
                        pipeline.fit(X_fit,fit.target_pm25)
                        fit_seconds=time.perf_counter()-started
                        fit_pred,pred=pipeline.predict(X_fit),pipeline.predict(X_test)
                        if pipeline.named_steps["model"].get_params()!=spec["parameters"]:
                            raise ValueError("Estimator parameters changed")
                        joblib.dump(pipeline,scratch / "pipeline.joblib",compress=3)
                        restored=joblib.load(scratch / "pipeline.joblib")
                        np.testing.assert_allclose(restored.predict(X_test),pred,rtol=0,atol=0)
                        child.log_artifact(scratch / "pipeline.joblib",name="model/pipeline.joblib")
                        summary=fitted_summary(pipeline,model_name); summary["artifact_type"]="fitted_pipeline_summary_with_separate_saved_weights"; summary["weights_saved"]=True
                        write_json(scratch / "pipeline_summary.json",summary)
                        child.log_artifact(scratch / "pipeline_summary.json",name="model/pipeline_summary.json")
                        if model_name=="ridge":
                            coefficient_table(pipeline).to_csv(out / "ridge_coefficients.csv",index=False)
                            child.log_artifact(out / "ridge_coefficients.csv",name="interpretation/ridge_coefficients.csv")
                        else:
                            perm,perm_ids=permutation_diagnostic(pipeline,X_test,test,design)
                            perm.to_csv(out / "rf_permutation.csv",index=False)
                            perm_ids.to_csv(out / "rf_permutation_ids.csv",index=False)
                            child.log_artifact(out / "rf_permutation.csv",name="interpretation/rf_permutation.csv")
                            child.log_artifact(out / "rf_permutation_ids.csv",name="interpretation/rf_permutation_ids.csv")
                    metrics={"refit_train_validation":scores(fit.target_pm25,fit_pred,fit["PM2.5"]),
                             "test_primary":scores(test.target_pm25,pred,test["PM2.5"]),
                             "timing_seconds":{"fit_pipeline":fit_seconds,"all_operations":time.perf_counter()-started},
                             "negative_predictions":int((pred<0).sum()),"postprocessing":"identity"}
                    for part,frame,values in (("refit",fit,fit_pred),("test",test,pred)):
                        prediction_frame(frame,values,child.run_id,model_name).to_csv(scratch / (part+".csv.gz"),index=False,compression="gzip")
                        child.log_artifact(scratch / (part+".csv.gz"),name="predictions/"+part+".csv.gz")
                    child.log_metrics(metrics)
                    predictions[model_name]=np.asarray(pred)
                    child_metrics[model_name]=metrics
                    rows.append({"model":model_name,"run_id":child.run_id,"development_reference_run_id":spec["reference_run_id"],
                                 "selected_for_deployment":model_name=="random_forest",**metrics["test_primary"],"fit_seconds":fit_seconds})
                if model_name!="persistence": del pipeline,restored
                gc.collect()
                print("DONE",model_name,"test_MAE",metrics["test_primary"]["MAE"],flush=True)
            pd.DataFrame(rows).to_csv(out / "comparison.csv",index=False)
            grouped_results(labeled,predictions,design).to_csv(out / "grouped_metrics.csv",index=False)
            event_rows=[]
            for key,part in labeled.dropna(subset=["episode_id"]).groupby("episode_id",sort=True):
                event_rows.append({"episode_id":key,"station":part.station.iloc[0],"start":str(part.target_timestamp.min()),"end":str(part.target_timestamp.max()),"n":len(part),"peak":float(part.target_pm25.max())})
            pd.DataFrame(event_rows,columns=["episode_id","station","start","end","n","peak"]).to_csv(out / "episodes.csv",index=False)
            from beijing_air.final_reporting import make_report
            make_report(root,design,state,fit,train,val,labeled,predictions,child_metrics,audit)
            for path in sorted(out.glob("*.csv")):
                parent.log_artifact(path,name="tables/"+path.name)
            for path in sorted((root / "reports/figures/final_evaluation").glob("*.png")):
                parent.log_artifact(path,name="figures/"+path.name)
            parent.log_artifact(root / "docs/results_discussion.md",name="report/results_discussion.md")
            parent.log_metrics({"models":child_metrics,"test_samples":len(test),"test_ids_sha256":ids_digest(test.sample_id),"deployment_selected_by":"development_validation_MAE","test_exposed":True})
        state["status"]="completed"
    except BaseException as error:
        state.update(status="failed",error={"type":type(error).__name__,"message":str(error)})
        raise
    finally:
        write_json(state_path,state)
        write_json(out / ("attempt_"+stamp+".json"),state)
    return state
