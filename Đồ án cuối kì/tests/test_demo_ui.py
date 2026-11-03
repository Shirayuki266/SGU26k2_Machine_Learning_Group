"""TEST_ONLY Streamlit workflows; real copied T13 weights, no fit or run log."""

import shutil
import pytest
import pandas as pd

from beijing_air.data import sha256
from beijing_air.demo import DemoError,DemoStore
from beijing_air.final_evaluation import write_json
from test_demo import ROOT,RF_ID,real_model,TEST_model_copy,TEST_store

def TEST_ONLY_render(root):
    from beijing_air.demo_ui import render
    render(root)


@pytest.fixture
def TEST_ui_root(TEST_model_copy,TEST_store):
    root=TEST_model_copy
    folder=root/"app/resources";folder.mkdir(parents=True)
    path=folder/"demo.sqlite3";shutil.copy2(TEST_store.path,path)
    manifest={**TEST_store.manifest,"dataset_source":"TEST_ONLY synthetic observations, not a new experiment","license":"TEST_ONLY",
              "database":{"path":"app/resources/demo.sqlite3","sha256":sha256(path),"bytes":path.stat().st_size}}
    write_json(folder/"demo_manifest.json",manifest)
    shutil.copy2(ROOT/"configs/demo.json",root/"configs/demo.json")
    return root


def test_streamlit_rerun_cache_never_fits_and_hides_stale_results(TEST_ui_root,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from sklearn.pipeline import Pipeline
    from sklearn.ensemble import RandomForestRegressor
    import beijing_air.demo_ui as ui
    ui.cached_model.clear();ui.cached_store.clear();ui.cached_origins.clear()
    calls={"load":0,"predict":0,"actual":0}
    original_load,original_predict,original_actual=ui.load_demo_model,ui.forecast_at,DemoStore.actual_after
    def counted_load(*args,**kwargs):
        calls["load"]+=1
        return original_load(*args,**kwargs)
    def counted_predict(*args,**kwargs):
        calls["predict"]+=1
        return original_predict(*args,**kwargs)
    def counted_actual(*args,**kwargs):
        calls["actual"]+=1
        return original_actual(*args,**kwargs)
    def forbidden_fit(*args,**kwargs):raise AssertionError("UI reruns must never train")
    monkeypatch.setattr(ui,"load_demo_model",counted_load)
    monkeypatch.setattr(ui,"forecast_at",counted_predict)
    monkeypatch.setattr(DemoStore,"actual_after",counted_actual)
    monkeypatch.setattr(Pipeline,"fit",forbidden_fit)
    monkeypatch.setattr(RandomForestRegressor,"fit",forbidden_fit)
    app=AppTest.from_function(TEST_ONLY_render,args=(str(TEST_ui_root),),default_timeout=20).run()
    assert not app.exception and calls=={"load":1,"predict":0,"actual":0}
    app.button(key="demo_predict").click().run()
    assert not app.exception and calls=={"load":1,"predict":1,"actual":1}
    assert len(app.metric)==3 and app.metric[2].value=="50.0 µg/m³"
    forecast=app.session_state["demo_forecast"]
    assert forecast.target==forecast.origin+pd.Timedelta(hours=1)
    app.checkbox(key="demo_inputs").check().run()
    assert not app.exception and calls=={"load":1,"predict":1,"actual":1}
    app.selectbox(key="demo_hour").set_value("13:00").run()
    assert not app.exception and len(app.metric)==0
    assert calls=={"load":1,"predict":1,"actual":1}
    app.button(key="demo_predict").click().run()
    assert not app.exception and calls=={"load":1,"predict":2,"actual":2}
    assert app.metric[1].value=="Thiếu số đo" and app.metric[2].value=="Chưa có"


def test_streamlit_missing_model_is_actionable(TEST_ui_root):
    from streamlit.testing.v1 import AppTest
    (TEST_ui_root/f"artifacts/experiments/{RF_ID}/artifacts/model/pipeline.joblib").unlink()
    app=AppTest.from_function(TEST_ONLY_render,args=(str(TEST_ui_root),),default_timeout=20).run()
    assert not app.exception and len(app.error)==1
    assert "model" in app.error[0].value and "T13" in app.error[0].value


def test_streamlit_failed_new_request_does_not_display_old_result(TEST_ui_root,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import beijing_air.demo_ui as ui
    app=AppTest.from_function(TEST_ONLY_render,args=(str(TEST_ui_root),),default_timeout=20).run()
    app.button(key="demo_predict").click().run()
    assert len(app.metric)==3
    def TEST_failure(*a,**k):raise DemoError("TEST_ONLY invalid request")
    monkeypatch.setattr(ui,"forecast_at",TEST_failure)
    app.button(key="demo_predict").click().run()
    assert not app.exception and len(app.metric)==0 and len(app.error)==1
