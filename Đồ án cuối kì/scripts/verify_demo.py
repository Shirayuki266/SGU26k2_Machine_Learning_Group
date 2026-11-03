"""T14 parity on a fixed, already-evaluated T13 illustration; no fit/selection."""

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from beijing_air.demo import DemoStore,forecast_at,load_demo_model
from beijing_air.final_evaluation import write_json


def main():
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--station")
    p.add_argument("--origin")
    p.add_argument("--output",default="reports/demo/inference_verification.json")
    args=p.parse_args()
    if bool(args.station)!=bool(args.origin):p.error("Provide both --station and --origin")
    root=Path(__file__).resolve().parents[1]
    model=load_demo_model(root)
    store=DemoStore.from_project(root)
    if args.station:
        requests=[(args.station,args.origin)]
    else:
        requests=[]
        for station,part in store.origins(model.stations).groupby("station",sort=True):
            for i in np.linspace(0,len(part)-1,min(3,len(part)),dtype=int):
                requests.append((station,str(part.timestamp.iloc[i])))
    rows=[]
    for station,origin in requests:
        events=[];store.observer=events.append
        forecast=forecast_at(model,store,station=station,origin=origin)
        if "future_actual" in events:raise AssertionError("Future truth read before prediction")
        actual=store.actual_after(forecast)
        if events.index("predict_complete")>events.index("future_actual"):
            raise AssertionError("Target access ordering changed")
        direct=float(model.pipeline.predict(forecast.features)[0])
        np.testing.assert_allclose(direct,forecast.predicted_pm25,rtol=0,atol=0)
        rows.append({"station":station,"origin":str(forecast.origin),"target":str(forecast.target),
            "sample_id":forecast.sample_id,"prediction":forecast.predicted_pm25,"actual_after_prediction":actual,
            "max_observation_time_used":str(forecast.history.timestamp.max()),"history_rows":len(forecast.history),
            "missing_inputs":list(forecast.missing_inputs),"events":events})
    # Compare against the already-saved T13 test predictions AFTER all inference.
    needed={r["sample_id"] for r in rows};reference={}
    path=root/"artifacts/experiments"/model.handoff["final_run_id"]/"artifacts/predictions/test.csv.gz"
    for chunk in pd.read_csv(path,usecols=["sample_id","y_pred"],chunksize=50000):
        part=chunk.loc[chunk.sample_id.isin(needed)]
        reference.update(zip(part.sample_id,part.y_pred))
    differences=[]
    for row in rows:
        expected=reference.get(row["sample_id"])
        row["reference_T13_test_prediction"]=expected
        if expected is None:
            row["reference_status"]="not in T13 primary cohort; no fabricated reference"
        else:
            np.testing.assert_allclose(row["prediction"],expected,rtol=1e-10,atol=1e-10)
            differences.append(abs(row["prediction"]-expected))
            row["reference_status"]="matched saved T13 test prediction"
    if not differences:raise AssertionError("No matching real reference samples")
    result={"task_id":"T14","artifact_type":"inference_consistency_check_not_model_experiment","status":"PASS",
        "model_run_id":model.handoff["final_run_id"],"selected_by":model.handoff["selected_by"],
        "requests_checked":len(rows),"saved_T13_predictions_matched":len(differences),"max_absolute_difference":max(differences),
        "input_dimensions":len(model.feature_names),"encoded_dimensions":model.metadata["encoded_dimensions"],
        "new_training":False,"T13_test_predictions_read":True,"input_test_csv_read_by_verifier":False,"target_read_after_predict":True,
        "scope":"examples after final fit from the already-evaluated T13 period; no new aggregate score or model selection",
        "rows":rows}
    write_json(root/args.output,result)
    print({k:v for k,v in result.items() if k!="rows"})


if __name__=="__main__":main()
