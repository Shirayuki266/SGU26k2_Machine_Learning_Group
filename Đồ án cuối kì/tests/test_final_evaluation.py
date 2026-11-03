"""TEST_ONLY synthetic contracts; no project test data or real logger runs."""

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from beijing_air.final_evaluation import (analysis_labels, coefficient_table,
    episode_ids, execute, load_partition, permutation_diagnostic, permutation_groups, reduction, scores,
    validate_frozen,write_json)
from beijing_air.data import sha256
from beijing_air.eda import ids_digest
from beijing_air.samples import ID_COLUMNS,_sample_id
from beijing_air.eda import read_json
from beijing_air.features import feature_registry
from beijing_air.preprocessing import make_regression_pipeline

ROOT=Path(__file__).resolve().parents[1]


def test_reduction_negative_and_undefined():
    assert reduction(8,10)==20
    assert reduction(12,10)==-20
    assert reduction(0,0) is None
    assert reduction(None,10) is None
    assert reduction(10,None) is None


def test_small_constant_and_empty_group_r2():
    assert scores([1,2],[1,1],[1,1],min_r2_n=30)["R2"] is None
    assert scores([1]*35,[2]*35,[2]*35,min_r2_n=30)["r2_undefined_reason"]=="constant_target"
    result=scores([],[],[],min_r2_n=30)
    assert result["MAE"] is None and result["mae_reduction_vs_persistence_pct"] is None
    assert scores([1,2],[1,2],[1,2])["mae_reduction_vs_persistence_pct"] is None


def test_episode_station_gap_threshold_and_minimum():
    meta=pd.DataFrame({"station":["TEST_A"]*5+["TEST_B"]*2,
        "target_timestamp":pd.to_datetime(["2020-01-01 00:00","2020-01-01 01:00","2020-01-01 02:00","2020-01-01 04:00","2020-01-01 05:00","2020-01-01 00:00","2020-01-01 01:00"]),
        "target_pm25":[150,151,160,200,201,200,200]})
    ids=episode_ids(meta,150,3)
    assert ids.iloc[:3].nunique()==1 and ids.iloc[:3].notna().all()
    assert ids.iloc[3:].isna().all()
    meta.loc[1,"target_pm25"]=149
    assert episode_ids(meta,150,3).isna().all()


def test_labels_use_target_season_and_fixed_threshold():
    frame=pd.DataFrame({"station":["TEST_A"],"target_timestamp":pd.to_datetime(["2020-03-01"]),"target_pm25":[150.],"PM2.5":[100.]})
    d={"analysis":{"concentration_edges":[0,35,75,150],"episode_threshold":150,"episode_min_hours":3}}
    labeled=analysis_labels(frame,d,50.)
    assert labeled.season.iloc[0]=="MAM"
    assert bool(labeled.rapid_change.iloc[0])
    assert "150" in labeled.concentration.iloc[0]


def test_source_groups_keep_cyclic_columns_together():
    x=pd.DataFrame(columns=["PM2.5","station","wd","target_hour","target_hour_sin","target_hour_cos","target_month","target_month_sin","target_month_cos"])
    groups=permutation_groups(x)
    assert groups["target_hour"]==["target_hour","target_hour_sin","target_hour_cos"]
    assert groups["station"]==["station"]
    assert sorted(c for values in groups.values() for c in values)==sorted(x.columns)


def test_permutation_never_fits_and_preserves_input():
    class TEST_ONLY_Model:
        def fit(self,*args):raise AssertionError("permutation must never fit")
        def predict(self,x):return x["PM2.5"].to_numpy()
    x=pd.DataFrame({"PM2.5":[1.,2.,3.,4.,5.,6.],"station":["TEST_A"]*3+["TEST_B"]*3})
    original=x.copy(deep=True)
    meta=pd.DataFrame({"sample_id":[f"TEST_{i}" for i in range(6)],"station":x.station,"target_timestamp":pd.date_range("2020-01-01",periods=6,freq="h"),"target_pm25":x["PM2.5"]})
    d={"analysis":{"permutation_rows_per_station":2,"permutation_repeats":3,"permutation_seed":42}}
    result,ids=permutation_diagnostic(TEST_ONLY_Model(),x,meta,d)
    assert len(ids)==4 and len(result)==6
    pd.testing.assert_frame_equal(x,original)
    repeat,_=permutation_diagnostic(TEST_ONLY_Model(),x,meta,d)
    pd.testing.assert_frame_equal(result,repeat)


def test_ridge_pipeline_holdout_not_fitted_and_saved_coefficients(tmp_path):
    import joblib
    config=read_json(ROOT / "configs/default.json")
    prep=read_json(ROOT / "configs/preprocessing.json")
    registry=feature_registry(config)
    names=registry.loc[registry.feature_sets.str.split(";").map(lambda x:"A" in x),"feature_name"]
    x=pd.DataFrame({c:np.arange(8,dtype=float) for c in names})
    x["station"]=["TEST_A"]*8; x["wd"]=["N"]*8
    pipeline=make_regression_pipeline("ridge",feature_set="A",config=config,preprocessing_config=prep)
    pipeline.fit(x,np.arange(8.))
    before=pipeline.named_steps["preprocess"].named_steps["columns"].named_transformers_["numeric"].named_steps["impute"].statistics_.copy()
    held=x.copy(); held["PM2.5"]=999999.;held["station"]="TEST_UNSEEN"
    prediction=pipeline.predict(held)
    np.testing.assert_array_equal(before,pipeline.named_steps["preprocess"].named_steps["columns"].named_transformers_["numeric"].named_steps["impute"].statistics_)
    coefficients=coefficient_table(pipeline)
    assert len(coefficients)==pipeline.named_steps["model"].n_features_in_
    assert coefficients.loc[coefficients.encoded_feature.str.startswith("numeric__"),"coefficient_per_raw_unit_if_numeric"].notna().all()
    path=tmp_path / "TEST_ONLY.joblib";joblib.dump(pipeline,path)
    np.testing.assert_array_equal(joblib.load(path).predict(held),prediction)


def test_missing_lock_stops_before_any_dataset_read(tmp_path):
    design={"schema_version":"t13-final-v1","feature_set":"A","cohort":"primary","files_sha256":{"TEST_ONLY_missing.json":"0"*64}}
    with pytest.raises(FileNotFoundError):validate_frozen(tmp_path,design)


@pytest.fixture
def TEST_ONLY_partition(tmp_path):
    station=["TEST_A","TEST_A","TEST_B","TEST_B"]
    origin=pd.to_datetime(["2020-01-01 00:00","2020-01-01 02:00"]*2)
    target=origin+pd.Timedelta(hours=1)
    frame=pd.DataFrame({"sample_id":[_sample_id(s,t,u) for s,t,u in zip(station,origin,target)],
        "station":station,"input_timestamp":origin,"target_timestamp":target,"is_primary":[True,False,True,True],
        "split":"test","PM2.5":[1.,np.nan,3.,4.],"target_pm25":[2.,3.,4.,5.]})
    files={}
    for kind,table in (("samples",frame),("ids",frame[ID_COLUMNS])):
        path=tmp_path/kind/"test.csv";path.parent.mkdir()
        table.to_csv(path,index=False)
        files["test_"+kind]={"path":path.relative_to(tmp_path).as_posix(),"bytes":path.stat().st_size,"sha256":sha256(path)}
    manifest={"files":files,"signature":{"split":{"validation_start":"2019-01-01","test_start":"2020-01-01"}},
              "membership":{"test":{name:{"samples":len(part),"ordered_sample_ids_sha256":ids_digest(part.sample_id)}
                  for name,part in (("operational",frame),("primary",frame.loc[frame.is_primary]))}}}
    return tmp_path,manifest,frame


def test_loader_keeps_exact_ids_and_no_target_imputation(TEST_ONLY_partition):
    root,manifest,original=TEST_ONLY_partition
    loaded=load_partition(root,manifest,"test")
    assert loaded.sample_id.tolist()==original.loc[original.is_primary,"sample_id"].tolist()
    assert loaded.target_pm25.tolist()==[2.,4.,5.]
    assert set(loaded.station)=={"TEST_A","TEST_B"}


def test_loader_rejects_tampered_file_before_scoring(TEST_ONLY_partition):
    root,manifest,_=TEST_ONLY_partition
    path=root/manifest["files"]["test_samples"]["path"]
    path.write_bytes(path.read_bytes()+b"\nTEST_ONLY_TAMPERED")
    with pytest.raises(ValueError,match="checksum"):
        load_partition(root,manifest,"test")


@pytest.mark.parametrize("status",["completed","running","failed"])
def test_budget_prevents_repeat_without_technical_reason(tmp_path,monkeypatch,status):
    import beijing_air.final_evaluation as module
    write_json(tmp_path/"configs/final_evaluation.json",{"schema_version":"TEST_ONLY"})
    write_json(tmp_path/"reports/final_evaluation/execution.json",{"status":status})
    monkeypatch.setattr(module,"development_data",lambda *a:({}, {}, None,None,None,{}))
    def no_logger(*a,**k):raise AssertionError("Must stop before logger or test I/O")
    monkeypatch.setattr(module,"ExperimentLogger",no_logger)
    with pytest.raises(RuntimeError,match="no automatic repeat"):
        execute(tmp_path)


def test_reporting_smoke_TEST_ONLY_before_real_exposure(tmp_path):
    from beijing_air.final_reporting import make_report
    from beijing_air.final_evaluation import grouped_results
    root=tmp_path/"TEST_ONLY_T13_REPORT";out=root/"reports/final_evaluation"
    out.mkdir(parents=True);(root/"docs").mkdir()
    train=pd.DataFrame({"sample_id":[f"TEST_TRAIN_{i}" for i in range(12)],"target_pm25":np.arange(12.)+10,"PM2.5":np.arange(12.)+9})
    val=train.iloc[:3].copy();fit=pd.concat([train,val],ignore_index=True)
    truth=np.tile([50.,60.,70.,160.,180.,190.],6)
    test=pd.DataFrame({"sample_id":[f"TEST_HELDOUT_{i}" for i in range(36)],"station":"TEST_A","target_timestamp":pd.date_range("2020-01-01",periods=36,freq="h"),"target_pm25":truth,"PM2.5":truth-1})
    test["input_timestamp"]=test.target_timestamp-pd.Timedelta(hours=1)
    design={"frozen":"TEST_ONLY_frozen.json","development_selected_run_id":"TEST_RF",
        "models":{k:{"reference_run_id":"TEST_"+k} for k in ("persistence","ridge","random_forest")},
        "analysis":{"concentration_edges":[0,35,75,150],"group_r2_min_n":30,"episode_threshold":150,"episode_min_hours":3,"timeline_station":"TEST_A","timeline_days":7}}
    values={"persistence":truth-1,"ridge":truth-.5,"random_forest":truth+.5}
    labeled=analysis_labels(test,design,38.)
    metrics={k:{"refit_train_validation":scores(fit.target_pm25,fit.target_pm25+.5,fit["PM2.5"]),"test_primary":scores(truth,p,test["PM2.5"])} for k,p in values.items()}
    pd.DataFrame([{"model":k,"run_id":"TEST_RUN_"+k,**metrics[k]["test_primary"]} for k in values]).to_csv(out/"comparison.csv",index=False)
    grouped_results(labeled,values,design).to_csv(out/"grouped_metrics.csv",index=False)
    events=[]
    for key,part in labeled.dropna(subset=["episode_id"]).groupby("episode_id"):
        events.append({"episode_id":key,"station":"TEST_A","start":part.target_timestamp.min(),"end":part.target_timestamp.max(),"n":len(part),"peak":part.target_pm25.max()})
    pd.DataFrame(events).to_csv(out/"episodes.csv",index=False)
    pd.DataFrame({"encoded_feature":["numeric__PM2.5","numeric__TEMP"],"coefficient_model_space":[1.,.1]}).to_csv(out/"ridge_coefficients.csv",index=False)
    pd.DataFrame([{"group":g,"repeat":i,"n":36,"MAE_increase":i*.1} for g in ("PM2.5","station") for i in (1,2,3)]).to_csv(out/"rf_permutation.csv",index=False)
    write_json(root/"TEST_ONLY_frozen.json",{"validation_results":[{"variant":v,"MAE":float(i+1)} for i,v in enumerate(("A","B","C"))]})
    fold_ids=[]
    for i in range(3):
        rid="TEST_FOLD_"+str(i);fold_ids.append(rid)
        path=root/"artifacts/experiments"/rid/"artifacts/predictions/evaluation.csv.gz";path.parent.mkdir(parents=True)
        part=train.iloc[i*2:i*2+2]
        pd.DataFrame({"sample_id":part.sample_id,"y_true":part.target_pm25,"y_pred":part.target_pm25+.5,"target_timestamp":pd.date_range("2019-01-01",periods=2,freq="h")}).to_csv(path,index=False,compression="gzip")
    write_json(root/"artifacts/experiments/TEST_CANDIDATE/metrics.json",{"fold_run_ids":fold_ids})
    for model,spec in design["models"].items():
        path=root/"artifacts/experiments"/spec["reference_run_id"]
        write_json(path/"config.json",{"parameters":{"selected_candidate_run_id":"TEST_CANDIDATE"}})
        write_json(path/"metrics.json",{"validation_primary":scores([1,2],[2,3],[2,3]),"train_primary":scores([1,2],[2,3],[2,3])})
    make_report(root,design,{"parent_run_id":"TEST_PARENT"},fit,train,val,labeled,values,metrics,{"latest_fit_target":"2019-12-31 23:00","rapid_change_threshold_train_q95":38.})
    assert len(list((root/"reports/figures/final_evaluation").glob("*.png")))==7
    text=(root/"docs/results_discussion.md").read_text(encoding="utf-8")
    assert all(rq in text for rq in ("RQ1","RQ2","RQ3","TEST_PARENT"))
