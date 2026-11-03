"""Streamlit presentation for the read-only T14 inference service."""

from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from beijing_air.demo import DemoError,DemoStore,forecast_at,load_demo_model,model_fingerprint
from beijing_air.data import sha256
from beijing_air.eda import read_json


@st.cache_resource(show_spinner=False)
def cached_model(root, fingerprint):
    return load_demo_model(Path(root))


@st.cache_resource(show_spinner=False)
def cached_store(root, fingerprint):
    return DemoStore.from_project(Path(root))


@st.cache_data(show_spinner=False)
def cached_origins(root, fingerprint, stations):
    # Only station/timestamp keys are cached, never measurements or future truth.
    return DemoStore.from_project(Path(root)).origins(stations)


def history_chart(forecast,actual):
    times=pd.date_range(forecast.origin-pd.Timedelta(hours=47),forecast.origin,freq="h")
    series=forecast.history.set_index("timestamp")["PM2.5"].reindex(times)
    frame=pd.DataFrame({"timestamp":times,"pm25":series.to_numpy(),"series":"Số đo đến t"})
    frame["segment"]=frame.pm25.isna().cumsum().astype(str)
    labels=["Số đo đến t","Dự báo t+1"]+(["Thực tế t+1"] if actual is not None else [])
    colors=alt.Scale(domain=labels,range=["#556e87","#087f80","#cc8134"][:len(labels)])
    line=alt.Chart(frame).mark_line(strokeWidth=2).encode(
        x=alt.X("timestamp:T",title="Thời điểm theo dữ liệu gốc",axis=alt.Axis(format="%d/%m %H:%M",labelAngle=-20)),
        y=alt.Y("pm25:Q",title="PM2.5 (µg/m³)",scale=alt.Scale(zero=False)),
        color=alt.Color("series:N",scale=colors,title=None),detail="segment:N",
        tooltip=[alt.Tooltip("timestamp:T",title="Thời điểm",format="%d/%m/%Y %H:%M"),alt.Tooltip("pm25:Q",title="PM2.5 (µg/m³)",format=".2f")])
    points=[{"timestamp":forecast.target,"pm25":forecast.predicted_pm25,"series":"Dự báo t+1"}]
    if actual is not None:points.append({"timestamp":forecast.target,"pm25":actual,"series":"Thực tế t+1"})
    point=alt.Chart(pd.DataFrame(points)).encode(
        x="timestamp:T",y="pm25:Q",color=alt.Color("series:N",scale=colors,title=None),
        tooltip=[alt.Tooltip("timestamp:T",title="Thời điểm",format="%d/%m/%Y %H:%M"),"series:N",alt.Tooltip("pm25:Q",title="PM2.5 (µg/m³)",format=".2f")])
    predicted=point.transform_filter(alt.datum.series=="Dự báo t+1").mark_point(filled=True,size=140,shape="diamond")
    observed=point.transform_filter(alt.datum.series=="Thực tế t+1").mark_point(filled=True,size=120,shape="circle")
    rule=alt.Chart(pd.DataFrame({"timestamp":[forecast.origin]})).mark_rule(color="#a6b4bf",strokeDash=[5,4]).encode(x="timestamp:T")
    return (line+rule+predicted+observed).properties(height=290).configure_legend(orient="bottom")


def render(project_root):
    root=Path(project_root).resolve()
    st.set_page_config(page_title="PM2.5 · Dự báo 1 giờ",page_icon="🌫️",layout="wide",initial_sidebar_state="collapsed")
    st.markdown("""<style>
      .stApp {background:#f5f8fa;}
      .block-container {max-width:1180px;padding-top:4.2rem;padding-bottom:2rem;}
      h1 {font-size:2.35rem !important;letter-spacing:-.04em;color:#173548;}
      h2,h3 {color:#173548;}
      div[data-testid="stMetric"] {background:white;border-radius:12px;}
      .demo-label {font-size:.74rem;letter-spacing:.13em;font-weight:700;color:#087f80;}
      .demo-footer {color:#647887;font-size:.83rem;margin-top:.8rem;}
      [data-testid="stAppDeployButton"] {display:none;}
      div[data-testid="stVerticalBlockBorderWrapper"] {background:white;border-radius:14px;}
    </style>""",unsafe_allow_html=True)
    st.markdown('<div class="demo-label">DEMO NGHIÊN CỨU · DỮ LIỆU LỊCH SỬ</div>',unsafe_allow_html=True)
    st.title("Dự báo PM2.5 trước 1 giờ")
    st.write("Chọn trạm và thời điểm phát hành để xem dự báo cho giờ kế tiếp, cùng diễn biến gần đây.")
    try:
        settings=read_json(root/"configs/demo.json")
        model=cached_model(str(root),model_fingerprint(root))
        data_key=sha256(root/"app/resources/demo_manifest.json")+":"+sha256(root/"app/resources/demo.sqlite3")
        store=cached_store(str(root),data_key)
        index=cached_origins(str(root),data_key,model.stations)
        if index.empty:raise DemoError("Không có thời điểm minh họa cho các trạm đã huấn luyện.")
    except (DemoError,OSError,ValueError,KeyError) as error:
        st.error(str(error))
        st.caption("Hướng dẫn cài đặt, dữ liệu và khôi phục model: docs/demo.md trong repo.")
        st.stop()
    with st.container(border=True):
        st.subheader("Chọn thời điểm dự báo")
        c1,c2,c3=st.columns([1.3,1,1])
        stations=sorted(index.station.unique())
        default=settings["default_station"] if settings["default_station"] in stations else stations[0]
        station=c1.selectbox("Trạm đã huấn luyện",stations,index=stations.index(default),key="demo_station")
        station_index=index.loc[index.station.eq(station)]
        dates=sorted(station_index.timestamp.dt.strftime("%Y-%m-%d").unique())
        date=c2.selectbox("Ngày trong dữ liệu",dates,format_func=lambda x:pd.Timestamp(x).strftime("%d/%m/%Y"),key="demo_date")
        times=sorted(station_index.loc[station_index.timestamp.dt.strftime("%Y-%m-%d").eq(date),"timestamp"].dt.strftime("%H:%M").unique())
        hour=c3.selectbox("Giờ phát hành t",times,index=times.index(settings["default_hour"]) if settings["default_hour"] in times else 0,key="demo_hour")
        origin=pd.Timestamp(date+" "+hour)
        target=origin+pd.Timedelta(hours=1)
        st.caption(f"Giờ t: {origin:%d/%m/%Y %H:%M} → giờ dự báo: {target:%d/%m/%Y %H:%M}. Timestamp giữ theo nguồn dữ liệu.")
        clicked=st.button("Dự báo giờ kế tiếp",type="primary",key="demo_predict",width="stretch")
    request_key=(station,str(origin))
    if st.session_state.get("demo_result_key")!=request_key:
        st.session_state.pop("demo_forecast",None)
        st.session_state.pop("demo_actual",None)
    if clicked:
        st.session_state.pop("demo_forecast",None)
        st.session_state.pop("demo_actual",None)
        try:
            with st.spinner("Đang tạo dự báo…"):
                forecast=forecast_at(model,store,station=station,origin=origin)
                # The first read of target truth happens only after predict returned.
                actual=store.actual_after(forecast)
                st.session_state["demo_forecast"]=forecast
                st.session_state["demo_actual"]=actual
                st.session_state["demo_result_key"]=request_key
        except (DemoError,ValueError) as error:
            st.error(str(error))
    forecast=st.session_state.get("demo_forecast")
    if forecast is None:
        st.info("Bấm “Dự báo giờ kế tiếp” để xem kết quả. Số đo đối chiếu chưa được truy vấn.")
    else:
        actual=st.session_state.get("demo_actual")
        st.subheader(f"{station} · Dự báo cho {forecast.target:%d/%m/%Y %H:%M}")
        c1,c2,c3=st.columns(3)
        c1.metric("Dự báo PM2.5 tại t+1",f"{forecast.predicted_pm25:.1f} µg/m³",border=True)
        c2.metric("PM2.5 quan sát tại t","Thiếu số đo" if forecast.current_pm25 is None else f"{forecast.current_pm25:.1f} µg/m³",border=True)
        c3.metric("Thực tế tại t+1","Chưa có" if actual is None else f"{actual:.1f} µg/m³",border=True)
        if actual is not None:
            st.caption(f"Đối chiếu sau dự báo · Dự báo − thực tế: {forecast.predicted_pm25-actual:+.2f} µg/m³. Đây là một ví dụ lịch sử, không phải đánh giá hiệu quả mới.")
        else:
            st.caption("Chưa có số đo giờ t+1 để đối chiếu; kết quả dự báo vẫn được giữ.")
        if forecast.missing_inputs:
            st.info("Một số số đo đầu vào đang thiếu. Pipeline dùng cách xử lý đã học từ tập huấn luyện, không tự điền 0.")
        if forecast.current_pm25 is None:
            st.caption("Trường hợp thiếu PM2.5 tại t chưa được đánh giá trong cohort test chính của nghiên cứu.")
        with st.container(border=True):
            st.subheader("Diễn biến trong 48 giờ gần đây")
            st.altair_chart(history_chart(forecast,actual),width="stretch",key="demo_history")
            st.caption("Đường xanh xám: lịch sử · Hình thoi xanh ngọc: dự báo · Chấm cam: thực tế t+1 nếu có. Đường đứt là giờ phát hành t.")
            observed=int(forecast.history["PM2.5"].notna().sum())
            st.caption(f"Có {observed}/48 số đo PM2.5 trong cửa sổ minh họa đến t. Khoảng trống giữ nguyên; điểm t+1 được hiển thị riêng.")
    with st.expander("Thông tin mô hình và dữ liệu"):
        a,b=st.columns(2)
        a.write("**Random Forest · bộ đặc trưng A**")
        a.write("80 cây · độ sâu tối đa 12 · dự báo đúng 1 giờ")
        a.write("Phương án đã chọn bằng validation; demo không chọn lại theo test.")
        a.caption(f"Fit train+validation: {model.metadata['fit_samples']:,} mẫu · {model.metadata['first_fit_target']} đến {model.metadata['last_fit_target']}")
        b.write("**Phát lại dữ liệu lịch sử UCI 501**")
        b.write("Thời điểm minh họa sau giai đoạn huấn luyện. Chỉ phát lại ví dụ đã có trong T13, không đánh giá lại hiệu quả.")
        b.caption(f"Python {model.metadata['python']} · scikit-learn {model.metadata['packages']['scikit-learn']} · {model.metadata['input_dimensions']} feature đầu vào / {model.metadata['encoded_dimensions']} chiều sau xử lý")
        st.caption("Run model: "+model.metadata["run_id"]+" · nguồn: "+store.manifest["dataset_source"]+" · "+store.manifest["license"])
        show=st.checkbox("Hiển thị số đo đầu vào tại t",key="demo_inputs")
        if show and forecast is not None:
            current=forecast.history.loc[forecast.history.timestamp.eq(forecast.origin)].copy()
            st.dataframe(current,hide_index=True,width="stretch")
    st.markdown('<div class="demo-footer">Demo nghiên cứu trên dữ liệu lịch sử · Không phải hệ thống cảnh báo vận hành.</div>',unsafe_allow_html=True)
