"""Capture actual local historical replay; no video, deployment, fit or new scoring."""

import argparse
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys

import pandas as pd

from beijing_air.data import sha256
from beijing_air.demo import DemoStore,forecast_at,load_demo_model
from beijing_air.eda import read_json
from beijing_air.final_evaluation import write_json


def main():
    root=Path(__file__).resolve().parents[1]
    if importlib.util.find_spec("playwright") is None:
        local=root/"artifacts/t14_tools/python"
        if local.is_dir():sys.path.insert(0,str(local))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise SystemExit("Install the optional demo-test dependencies and Chromium; see docs/demo.md") from error
    local_browsers=root/"artifacts/t14_tools/browsers"
    if local_browsers.is_dir():os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH",str(local_browsers))
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url",default="http://127.0.0.1:8514")
    args=p.parse_args()
    if not args.url.startswith("http://127.0.0.1:"):
        p.error("Capture the local demo only")
    out=root/"reports/demo/screenshots";out.mkdir(parents=True,exist_ok=True)
    settings=read_json(root/"configs/demo.json")
    initial_origin=pd.Timestamp(settings["start"]).normalize()+pd.Timedelta(hours=int(settings["default_hour"].split(":")[0]))
    expected=forecast_at(load_demo_model(root),DemoStore.from_project(root),station=settings["default_station"],origin=initial_origin)
    images=[];errors=[]
    def capture(page,name,scenario):
        # Streamlit scrolls inside stMain, not the document body. Expand to
        # content height and reset that scroll container for a complete image.
        page.wait_for_timeout(250)
        content_height=page.locator(".block-container").evaluate("el => Math.ceil(el.scrollHeight)")
        page.set_viewport_size({"width":page.viewport_size["width"],"height":min(3200,max(900,content_height+100))})
        page.get_by_test_id("stMain").evaluate("el => {el.scrollTop=0}")
        page.wait_for_timeout(250)
        page.wait_for_function("document.fonts.status === 'loaded'")
        path=out/(name+".png")
        page.screenshot(path=str(path),full_page=True)
        images.append({"path":path.relative_to(root).as_posix(),"sha256":sha256(path),"scenario":scenario,"bytes":path.stat().st_size,"viewport":page.viewport_size})
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1440,"height":1120},device_scale_factor=1)
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(args.url,wait_until="domcontentloaded")
        button=page.get_by_role("button",name="Dự báo giờ kế tiếp",exact=True)
        button.wait_for(state="visible",timeout=45000)
        capture(page,"01_ready","Actual local app before prediction; no target queried by UI")
        button.click()
        page.get_by_test_id("stMetric").first.get_by_text(f"{expected.predicted_pm25:.1f} µg/m³",exact=True).wait_for(timeout=30000)
        page.get_by_test_id("stVegaLiteChart").locator("svg,canvas").first.wait_for(state="visible",timeout=20000)
        capture(page,"02_forecast",f"{expected.station} {expected.origin} -> {expected.target}, post-fit pipeline forecast then actual")
        page.get_by_text("Thông tin mô hình và dữ liệu",exact=True).click()
        page.get_by_text("Random Forest · bộ đặc trưng A",exact=True).wait_for()
        capture(page,"03_model_details","Version/schema/training phase and validation selection, real T13 model")
        manifest=read_json(root/"app/resources/demo_manifest.json")
        with sqlite3.connect((root/manifest["database"]["path"]).as_uri()+"?mode=ro",uri=True) as db:
            missing=db.execute('SELECT station,timestamp FROM observations WHERE timestamp>=? AND timestamp<? AND "PM2.5" IS NULL ORDER BY station,timestamp LIMIT 1',
                [manifest["selection"]["start"],manifest["selection"]["end"]]).fetchone()
        if missing:
            station,origin=missing;origin=pd.Timestamp(origin)
            def choose(position,label):
                page.get_by_role("combobox").nth(position).click()
                page.get_by_role("option",name=label,exact=True).click()
                # Each dependent selector triggers a server rerun; wait before
                # changing the next widget so an older render cannot reset it.
                page.wait_for_timeout(700)
            choose(0,station)
            choose(1,origin.strftime("%d/%m/%Y"))
            choose(2,origin.strftime("%H:%M"))
            page.get_by_text(f"Giờ t: {origin:%d/%m/%Y %H:%M}",exact=False).wait_for()
            button.click()
            page.get_by_text("Thiếu số đo",exact=True).wait_for(timeout=30000)
            page.get_by_test_id("stVegaLiteChart").locator("svg,canvas").first.wait_for(state="visible",timeout=20000)
            capture(page,"04_missing_current","Real demo row with missing PM2.5(t); learned imputation, no zero-fill")
        page.set_viewport_size({"width":430,"height":1000})
        capture(page,"05_mobile","Responsive local app, same model/prediction state")
        version=browser.version
        if page.get_by_test_id("stException").count():raise AssertionError("Streamlit exception visible in actual browser")
        browser.close()
    if errors:raise AssertionError(errors)
    write_json(root/"reports/demo/browser_verification.json",{
        "task_id":"T14","status":"PASS","browser":"Chromium "+version,"url":args.url,"images":images,
        "browser_page_errors":errors,"missing_current_example":None if not missing else {"station":missing[0],"origin":str(missing[1])},
        "server_exposed_publicly":False,"deployed":False,"video_recorded":False,"model_training_performed":False,
        "note":"Screenshots are actual browser UI, not mockups. A member must record the demo video later."})
    print({"status":"PASS","screenshots":len(images),"browser":version,"video_recorded":False})


if __name__=="__main__":main()
