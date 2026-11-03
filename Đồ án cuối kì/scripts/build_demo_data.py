"""T14 fixed replay after final fit, from an already-evaluated T13 window."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pandas as pd

from beijing_air.data import MEASUREMENTS,sha256
from beijing_air.eda import project_path,read_json
from beijing_air.final_evaluation import write_json


def main():
    root=Path(__file__).resolve().parents[1]
    config=read_json(root/"configs/demo.json")
    if config["source_partition"]!="test" or config["history_hours"]!=48:
        raise ValueError("Expected the fixed post-fit window/48h")
    start,end=map(pd.Timestamp,(config["start"],config["end"]))
    source_manifest=read_json(root/"reports/splits_full/split_manifest.json")
    split=source_manifest["signature"]["split"]
    execution=read_json(root/"reports/final_evaluation/execution.json")
    handoff=read_json(root/"reports/final_evaluation/final_model.json")
    model_cfg=read_json(root/"artifacts/experiments"/handoff["final_run_id"]/"config.json")
    last_fit=pd.Timestamp(model_cfg["data"]["preflight"]["latest_fit_target"])
    if (execution["status"]!="completed" or not execution["test_samples_accessed"]
            or start<pd.Timestamp(split["test_start"]) or start<last_fit or end<=start):
        raise ValueError("T13 must already be evaluated; every illustration origin must be after the fit labels")
    info=source_manifest["files"]["test_samples"]
    source=project_path(root,info["path"])
    if sha256(source)!=info["sha256"] or source.stat().st_size!=info["bytes"]:
        raise ValueError("T05 test snapshot differs; no reinterpretation as unseen test")
    data=pd.read_csv(source,na_values=["NA"],parse_dates=["input_timestamp","target_timestamp"])
    buffer_start=start-pd.Timedelta(hours=47)
    part=data.loc[data.input_timestamp.ge(buffer_start)&data.input_timestamp.lt(end)].copy()
    if part.empty or part.duplicated(["station","input_timestamp"]).any():
        raise ValueError("Empty or duplicate demo origins")
    observations=part[["station","input_timestamp",*MEASUREMENTS,"wd"]].rename(columns={"input_timestamp":"timestamp"})
    actuals=part[["station","target_timestamp","target_pm25"]].rename(columns={"target_pm25":"pm25"})
    # Historical measurements from validation are only a past context buffer;
    # no validation targets are selected or used for new predictions/selection.
    val_info=source_manifest["files"]["validation_samples"]
    val_path=project_path(root,val_info["path"])
    if sha256(val_path)!=val_info["sha256"]:raise ValueError("Validation buffer snapshot differs")
    cols=["station","input_timestamp",*MEASUREMENTS,"wd"]
    val=pd.read_csv(val_path,usecols=cols,na_values=["NA"],parse_dates=["input_timestamp"])
    buffer=val.loc[val.input_timestamp.ge(buffer_start)&val.input_timestamp.lt(part.input_timestamp.min()),cols].rename(columns={"input_timestamp":"timestamp"})
    observations=pd.concat([buffer,observations],ignore_index=True).sort_values(["station","timestamp"],kind="stable")
    if observations.duplicated(["station","timestamp"]).any():raise ValueError("Overlapping buffer/sample keys")
    for frame,column in ((observations,"timestamp"),(actuals,"target_timestamp")):
        frame[column]=frame[column].dt.strftime("%Y-%m-%d %H:%M:%S")
    folder=root/"app/resources";folder.mkdir(parents=True,exist_ok=True)
    path=folder/"demo.sqlite3"
    manifest_path=folder/"demo_manifest.json"
    # Refuse silent overwrite: this is a frozen demo fixture, not run history.
    if path.exists() or manifest_path.exists():
        raise FileExistsError("Demo resource exists; inspect it before intentionally replacing a preparation snapshot")
    with sqlite3.connect(path) as db:
        observations.to_sql("observations",db,index=False)
        actuals.to_sql("actuals",db,index=False)
        db.execute("CREATE UNIQUE INDEX observations_key ON observations(station,timestamp)")
        db.execute("CREATE UNIQUE INDEX actuals_key ON actuals(station,target_timestamp)")
        db.execute("PRAGMA user_version=14")
    db.close()
    provenance=read_json(root/"reports/data_manifest.json")
    origins=part.loc[part.input_timestamp.ge(start)]
    manifest={"schema_version":"t14-demo-data-v1","task_id":"T14","artifact_type":"historical_demo_data_preparation",
        "created_at":datetime.now(timezone.utc).isoformat(),"model_experiment_run":False,"test_samples_accessed":True,
        "selection":{"start":str(start),"end":str(end),"buffer_start":str(buffer_start),"window_selection":"fixed in config before predictions, no error-based sample selection"},
        "source_partition":"already-evaluated T13 test period, with validation measurements as past buffer","source":info,
        "history_buffer_source":val_info,"last_model_fit_target":str(last_fit),"new_model_selection_or_aggregate_score":False,
        "split_manifest_sha256":sha256(root/"reports/splits_full/split_manifest.json"),
        "dataset_source":provenance["source_url"],"license":provenance["license"],"license_url":provenance["license_url"],
        "observations":len(observations),"selectable_origins":len(origins),"actual_rows":len(actuals),
        "stations":sorted(origins.station.unique().tolist()),
        "missing_origin_pm25_in_selectable":int(origins["PM2.5"].isna().sum()),
        "observations_columns":observations.columns.tolist(),"actuals_columns":actuals.columns.tolist(),
        "selection_caveat":"T05 operational retained rows require an observed target. This illustration is conditional on that cohort, not a raw-data missingness audit or new evaluation.",
        "target_access_policy":"Offline builder separates observations/actuals. Runtime index reads only keys, feature query only times<=t; actuals query occurs only after successful predict.",
        "database":{"path":path.relative_to(root).as_posix(),"bytes":path.stat().st_size,"sha256":sha256(path)}}
    write_json(manifest_path,manifest)
    print({k:manifest[k] for k in ("observations","selectable_origins","stations","missing_origin_pm25_in_selectable","test_samples_accessed")})


if __name__=="__main__":main()
