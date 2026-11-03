"""TEST_ONLY observations and copied trusted weights; never fit or log runs."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sqlite3

import joblib
import numpy as np
import pandas as pd
import pytest

from beijing_air.data import MEASUREMENTS,sha256
from beijing_air.demo import DemoError,DemoStore,check_runtime,forecast_at,load_demo_model,valid_origin
from beijing_air.final_evaluation import write_json

ROOT=Path(__file__).resolve().parents[1]
RF_ID="24cd6d765f214d52aa26e5988380e2cd"


@pytest.fixture(scope="module")
def real_model():
    if not (ROOT/f"artifacts/experiments/{RF_ID}/artifacts/model/pipeline.joblib").exists():
        pytest.skip("Restore trusted T13 bundle before running model integration tests; no substitute is trained")
    return load_demo_model(ROOT)


@pytest.fixture
def TEST_store(tmp_path):
    path=tmp_path/"TEST_ONLY.sqlite3"
    times=pd.to_datetime(["2016-03-01 10:00","2016-03-01 12:00","2016-03-01 13:00","2016-03-01 12:00"])
    observations=pd.DataFrame({"station":["Aotizhongxin"]*3+["Changping"],"timestamp":times.strftime("%Y-%m-%d %H:%M:%S")})
    for name in MEASUREMENTS:observations[name]=[20.,40.,50.,60.]
    observations["wd"]=["N","N",None,"S"]
    observations.loc[2,"PM2.5"]=np.nan
    observations.loc[1,"TEMP"]=np.nan
    actuals=pd.DataFrame({"station":["Aotizhongxin"],"target_timestamp":["2016-03-01 13:00:00"],"pm25":[50.]})
    with sqlite3.connect(path) as db:
        observations.to_sql("observations",db,index=False)
        actuals.to_sql("actuals",db,index=False)
    manifest={"schema_version":"TEST_ONLY","selection":{"start":"2016-03-01 00:00:00","end":"2016-03-02 00:00:00"}}
    return DemoStore(path,manifest)


def test_future_and_other_station_values_never_change_past_forecast(real_model,TEST_store):
    first=forecast_at(real_model,TEST_store,station="Aotizhongxin",origin="2016-03-01 12:00")
    assert first.history.timestamp.max()==first.origin
    with sqlite3.connect(TEST_store.path) as db:
        db.execute('UPDATE observations SET "PM2.5"=999999,TEMP=999999 WHERE timestamp>? OR station=?',("2016-03-01 12:00:00","Changping"))
        db.execute("UPDATE actuals SET pm25=999999")
    second=forecast_at(real_model,TEST_store,station="Aotizhongxin",origin="2016-03-01 12:00")
    pd.testing.assert_frame_equal(first.features,second.features)
    assert first.predicted_pm25==second.predicted_pm25
    assert TEST_store.actual_after(second)==999999


def test_target_access_only_after_predict_and_failure_never_reads_actual(real_model,TEST_store):
    events=[];TEST_store.observer=events.append
    forecast=forecast_at(real_model,TEST_store,station="Aotizhongxin",origin="2016-03-01 12:00")
    assert events==["past_observations","predict_start","predict_complete"]
    assert TEST_store.actual_after(forecast)==50
    assert events[-1]=="future_actual"
    events.clear()
    class TEST_BadPredictor:
        def predict(self,x):return [np.nan]
    with pytest.raises(DemoError,match="hữu hạn"):
        forecast_at(replace(real_model,pipeline=TEST_BadPredictor()),TEST_store,station="Aotizhongxin",origin="2016-03-01 12:00")
    assert "future_actual" not in events
    with pytest.raises(DemoError):TEST_store.actual_after("2016-03-01 13:00")


def test_A_with_short_history_matches_full_history_and_preserves_missing(real_model,TEST_store):
    full=forecast_at(real_model,TEST_store,station="Aotizhongxin",origin="2016-03-01 12:00")
    assert np.isnan(full.features.iloc[0]["TEMP"])
    with sqlite3.connect(TEST_store.path) as db:
        db.execute("DELETE FROM observations WHERE timestamp<?",("2016-03-01 12:00:00",))
    short=forecast_at(real_model,TEST_store,station="Aotizhongxin",origin="2016-03-01 12:00")
    assert len(short.history)==1
    pd.testing.assert_frame_equal(full.features,short.features)
    assert full.predicted_pm25==short.predicted_pm25


def test_missing_current_pm25_uses_saved_median_not_zero_or_fit(real_model,TEST_store):
    before=joblib.hash(real_model.pipeline)
    forecast=forecast_at(real_model,TEST_store,station="Aotizhongxin",origin="2016-03-01 13:00")
    assert forecast.current_pm25 is None and np.isnan(forecast.features["PM2.5"].iloc[0])
    pre=real_model.pipeline.named_steps["preprocess"]
    transformed=pre.transform(forecast.features)
    imputer=pre.named_steps["columns"].named_transformers_["numeric"].named_steps["impute"]
    numeric=list(pre.named_steps["columns"].transformers_[0][2])
    expected=imputer.statistics_[numeric.index("PM2.5")]
    assert transformed["numeric__PM2.5"].iloc[0]==expected
    assert expected!=0
    assert np.isfinite(forecast.predicted_pm25)
    assert joblib.hash(real_model.pipeline)==before


@pytest.mark.parametrize("origin",["bad timestamp","2016-03-01 12:30","2016-03-01T12:00Z","2015-12-01 12:00","NaT",1])
def test_invalid_time_rejected_without_target_query(real_model,TEST_store,origin):
    events=[];TEST_store.observer=events.append
    with pytest.raises(DemoError):forecast_at(real_model,TEST_store,station="Aotizhongxin",origin=origin)
    assert "future_actual" not in events


def test_unknown_station_missing_origin_and_actual_not_filled(real_model,TEST_store):
    with pytest.raises(DemoError,match="trạm"):
        forecast_at(real_model,TEST_store,station="TEST_UNKNOWN",origin="2016-03-01 12:00")
    with pytest.raises(DemoError,match="quan sát"):
        forecast_at(real_model,TEST_store,station="Aotizhongxin",origin="2016-03-01 11:00")
    forecast=forecast_at(real_model,TEST_store,station="Aotizhongxin",origin="2016-03-01 12:00")
    with sqlite3.connect(TEST_store.path) as db:db.execute("DELETE FROM actuals")
    assert TEST_store.actual_after(forecast) is None
    with TEST_store.connect() as db:
        with pytest.raises(sqlite3.OperationalError):db.execute("DELETE FROM observations")


def test_before_fit_origin_rejected_even_inside_store_range(real_model,TEST_store):
    store=DemoStore(TEST_store.path,{"selection":{"start":"2015-01-01","end":"2017-01-01"}})
    events=[];store.observer=events.append
    with pytest.raises(DemoError,match="nhãn fit cuối"):
        forecast_at(real_model,store,station="Aotizhongxin",origin="2015-11-01 12:00")
    assert events==[]


@pytest.fixture
def TEST_model_copy(tmp_path,real_model):
    root=tmp_path/"TEST_ONLY_MODEL_COPY"
    names=["reports/final_evaluation/final_model.json","reports/ablation/frozen_model.json","configs/final_evaluation.json","configs/default.json",
        f"artifacts/experiments/{RF_ID}/metadata.json",f"artifacts/experiments/{RF_ID}/config.json",
        f"artifacts/experiments/{RF_ID}/artifacts/model/pipeline_summary.json",f"artifacts/experiments/{RF_ID}/artifacts/model/pipeline.joblib"]
    for name in names:
        dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
    return root


def test_loader_checks_checksum_before_deserialize(TEST_model_copy,monkeypatch):
    path=TEST_model_copy/f"artifacts/experiments/{RF_ID}/artifacts/model/pipeline.joblib"
    with path.open("r+b") as stream:stream.write(b"TEST_ONLY_TAMPER")
    def forbidden(*a,**k):raise AssertionError("Should not deserialize a mismatched file")
    monkeypatch.setattr(joblib,"load",forbidden)
    with pytest.raises(DemoError,match="Checksum"):load_demo_model(TEST_model_copy)


def test_loader_version_and_schema_mismatch(TEST_model_copy,monkeypatch):
    meta=TEST_model_copy/f"artifacts/experiments/{RF_ID}/metadata.json"
    value=json.loads(meta.read_text(encoding="utf-8"));value["environment"]["packages"]["scikit-learn"]="TEST_ONLY_INVALID_VERSION"
    write_json(meta,value)
    with pytest.raises(DemoError,match="Phiên bản"):load_demo_model(TEST_model_copy)
    shutil.copy2(ROOT/f"artifacts/experiments/{RF_ID}/metadata.json",meta)
    config=TEST_model_copy/"configs/default.json";value=json.loads(config.read_text(encoding="utf-8"))
    value["features"]["A"]["calendar_reference"]="TEST_ONLY_INVALID_SCHEMA";write_json(config,value)
    with pytest.raises(DemoError,match="schema"):load_demo_model(TEST_model_copy)


def test_loader_rejects_nonvalidation_selection_and_missing_model(TEST_model_copy,tmp_path):
    with pytest.raises(DemoError,match="Thiếu"):load_demo_model(tmp_path/"TEST_ONLY_MISSING")
    path=TEST_model_copy/"reports/final_evaluation/final_model.json";value=json.loads(path.read_text(encoding="utf-8"))
    value["selected_by"]="TEST_ONLY_TEST_SELECTION";write_json(path,value)
    with pytest.raises(DemoError,match="validation"):load_demo_model(TEST_model_copy)


def test_real_demo_schema_and_script_parity(real_model):
    store=DemoStore.from_project(ROOT)
    forecast=forecast_at(real_model,store,station="Aotizhongxin",origin="2016-03-01 12:00")
    assert len(forecast.features.columns)==20 and real_model.metadata["encoded_dimensions"]==65
    assert forecast.sample_id==forecast.features.index[0]
    actual=float(real_model.pipeline.predict(forecast.features)[0])
    np.testing.assert_allclose(actual,forecast.predicted_pm25,rtol=0,atol=0)
