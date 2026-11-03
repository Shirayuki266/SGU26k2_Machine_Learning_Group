"""Artifact-driven T13 discussion/figures. No fit or model selection."""

from pathlib import Path

import numpy as np
import pandas as pd

from beijing_air.eda import read_json
from beijing_air.final_evaluation import scores
from beijing_air.metrics import regression_metrics


def development_comparison(root, design, train, child_metrics):
    rows, fold_rows, summary_rows = [], [], []
    ref = root / "artifacts/experiments" / design["models"]["ridge"]["reference_run_id"]
    rc = read_json(ref / "config.json")
    candidate = read_json(root / "artifacts/experiments" / rc["parameters"]["selected_candidate_run_id"] / "metrics.json")
    lookup = train.set_index("sample_id")
    pooled = {"ridge":[],"persistence":[]}
    for number,rid in enumerate(candidate["fold_run_ids"],1):
        pred = pd.read_csv(root / "artifacts/experiments" / rid / "artifacts/predictions/evaluation.csv.gz")
        source = lookup.loc[pred.sample_id]
        np.testing.assert_allclose(source.target_pm25,pred.y_true,rtol=0,atol=0)
        baseline = source["PM2.5"].to_numpy()
        for model,values in (("ridge",pred.y_pred.to_numpy()),("persistence",baseline)):
            fold_rows.append({"model":model,"fold":number,"reference_fold_run_id":rid,
                "evaluation_start":str(pd.to_datetime(pred.target_timestamp).min()),"evaluation_last_target":str(pd.to_datetime(pred.target_timestamp).max()),
                **scores(pred.y_true,values,baseline)})
            pooled[model].append(pd.DataFrame({"y":pred.y_true,"p":values,"baseline":baseline}))
    folds = pd.DataFrame(fold_rows)
    for model,frames in pooled.items():
        all_rows = pd.concat(frames,ignore_index=True)
        subset = folds.loc[folds.model.eq(model)]
        summary={"model":model,"folds":len(subset),"std_ddof":0,**{f"pooled_{k}":v for k,v in scores(all_rows.y,all_rows.p,all_rows.baseline).items()}}
        for metric in ("MAE","RMSE","R2","mae_reduction_vs_persistence_pct"):
            summary[metric+"_fold_mean"]=float(subset[metric].mean())
            summary[metric+"_fold_std"]=float(np.std(subset[metric],ddof=0))
        summary_rows.append(summary)
    cv = pd.DataFrame(summary_rows)
    for name,spec in design["models"].items():
        historical = read_json(root / "artifacts/experiments" / spec["reference_run_id"] / "metrics.json")
        for partition,key in (("development_train_in_sample","train_primary"),("development_validation_held_out","validation_primary")):
            value=historical.get(key)
            rows.append({"model":name,"partition":partition,"reference_run_id":spec["reference_run_id"],**(value or {"MAE":None,"RMSE":None,"R2":None}),"note":"not recorded" if value is None else "historical train-only fit; not the refitted final model"})
        if name in set(cv.model):
            value=cv.loc[cv.model.eq(name)].iloc[0]
            rows.append({"model":name,"partition":"development_train_CV_pooled","MAE":value.pooled_MAE,"RMSE":value.pooled_RMSE,"R2":value.pooled_R2,"note":"3 temporal folds; std in cv_summary.csv"})
        else:
            rows.append({"model":name,"partition":"development_train_CV_pooled","MAE":None,"RMSE":None,"R2":None,"note":"RF CV not run in T11 budget; no fabricated folds"})
        for key,label in (("refit_train_validation","final_refit_train_validation_IN_SAMPLE"),("test_primary","final_test_held_out")):
            rows.append({"model":name,"partition":label,**child_metrics[name][key],"note":"final fit uses more data than historical model; validation is part of fit"})
    return pd.DataFrame(rows),folds,cv


def make_report(root,design,state,fit,train,val,test,predictions,child_metrics,audit):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    root=Path(root)
    out=root / "reports/final_evaluation"
    figures=root / "reports/figures/final_evaluation"
    figures.mkdir(parents=True,exist_ok=True)
    comparison=pd.read_csv(out / "comparison.csv")
    grouped=pd.read_csv(out / "grouped_metrics.csv")
    events=pd.read_csv(out / "episodes.csv")
    gap,folds,cv=development_comparison(root,design,train,child_metrics)
    gap.to_csv(out / "generalization_gap.csv",index=False)
    folds.to_csv(out / "development_fold_metrics.csv",index=False)
    cv.to_csv(out / "cv_summary.csv",index=False)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10})
    colors={"persistence":"#6c7784","ridge":"#d68b22","random_forest":"#287b63"}
    index=[]
    def save(fig,name,title,source,scope="test diagnostic; fixed models"):
        fig.tight_layout()
        path=figures/(name+".png")
        fig.savefig(path,dpi=170,bbox_inches="tight")
        plt.close(fig)
        index.append({"figure_id":name,"title":title,"path":path.relative_to(root).as_posix(),"source":source,"scope":scope,"parent_run_id":state["parent_run_id"]})
    fig,axes=plt.subplots(1,3,figsize=(15,4.5))
    for ax,(model,values) in zip(axes,predictions.items()):
        ax.scatter(test.target_pm25,values,s=2,alpha=.15,color=colors[model],rasterized=True)
        lo=min(0,float(np.min(values))); hi=max(float(test.target_pm25.max()),float(np.max(values)))
        ax.plot([lo,hi],[lo,hi],"k--",linewidth=.8)
        ax.set(xlabel="Actual PM2.5 (µg/m³)",ylabel="Predicted PM2.5 (µg/m³)",title=model)
    save(fig,"actual_predicted","All primary test actual/predicted observations","child predictions/test.csv.gz")
    fig,axes=plt.subplots(1,3,figsize=(15,4.5))
    for ax,(model,values) in zip(axes,predictions.items()):
        residual=values-test.target_pm25.to_numpy()
        ax.hist(residual,bins=100,color=colors[model],alpha=.8)
        ax.axvline(0,color="black",linestyle="--",linewidth=.8)
        ax.set(xlabel="Prediction - actual (µg/m³)",ylabel="Test samples",title=model)
    save(fig,"residuals","Residual distribution without clipping","child predictions/test.csv.gz")
    def timeline(part,name,title):
        fig,ax=plt.subplots(figsize=(13,4.5))
        if part.empty:
            ax.text(.5,.5,"No observations meet the predeclared rule",ha="center",transform=ax.transAxes)
        else:
            frame=part[["target_timestamp","target_pm25"]].copy()
            for model,values in predictions.items():frame[model]=values[part.index]
            frame=frame.set_index("target_timestamp").sort_index()
            frame=frame.reindex(pd.date_range(frame.index.min(),frame.index.max(),freq="h"))
            ax.plot(frame.index,frame.target_pm25,"k-",label="Actual",linewidth=1.5)
            for model in predictions:ax.plot(frame.index,frame[model],label=model,color=colors[model],linewidth=.8,alpha=.85)
            ax.legend(ncol=4)
        ax.set(xlabel="Target time (source local)",ylabel="PM2.5 (µg/m³)",title=title)
        save(fig,name,title,"child predictions/test.csv.gz; gaps remain NaN")
    first=test.target_timestamp.min()
    timeline(test.loc[test.station.eq(design["analysis"]["timeline_station"]) & test.target_timestamp.lt(first+pd.Timedelta(days=design["analysis"]["timeline_days"]))],"timeline","Predeclared station, first seven test days")
    event_title="No qualifying high-pollution episode"
    event=test.iloc[:0]
    chosen_event=None
    if not events.empty:
        chosen_event=events.sort_values(["peak","start","station"],ascending=[False,True,True]).iloc[0]
        event=test.loc[test.station.eq(chosen_event.station) & test.target_timestamp.between(pd.Timestamp(chosen_event.start)-pd.Timedelta(hours=12),pd.Timestamp(chosen_event.end)+pd.Timedelta(hours=12))]
        event_title="Highest observed episode peak: "+chosen_event.episode_id+" (diagnostic selection only)"
    timeline(event,"high_pollution_episode",event_title)
    fig,axes=plt.subplots(1,2,figsize=(14,5))
    for ax,group in zip(axes,("station","season")):
        table=grouped.loc[grouped.group.eq(group)].pivot(index="value",columns="model",values="MAE")
        table.plot.bar(ax=ax,color=[colors[k] for k in table.columns],rot=45)
        ax.set(xlabel=group,ylabel="Test MAE (µg/m³)")
    save(fig,"group_errors","MAE by station and target season","grouped_metrics.csv")
    perm=pd.read_csv(out / "rf_permutation.csv")
    importance=perm.groupby("group").MAE_increase.agg(mean="mean",std=lambda x:np.std(x,ddof=0)).sort_values("mean")
    importance.to_csv(out / "rf_permutation_summary.csv")
    fig,ax=plt.subplots(figsize=(10,7))
    ax.barh(importance.index,importance["mean"],xerr=importance["std"],color=colors["random_forest"])
    ax.set(xlabel="Increase in MAE after raw-group permutation (µg/m³)",title="RF diagnostic only; 3 repeats, ≤2400 fixed IDs; not causal")
    save(fig,"rf_permutation","Grouped permutation importance; error bars ddof0","rf_permutation.csv; rf_permutation_ids.csv")
    coef=pd.read_csv(out / "ridge_coefficients.csv")
    selected=coef.iloc[np.argsort(np.abs(coef.coefficient_model_space.to_numpy()))[-15:]]
    fig,ax=plt.subplots(figsize=(11,7))
    ax.barh(selected.encoded_feature,selected.coefficient_model_space,color=colors["ridge"])
    ax.set(xlabel="Coefficient in encoded/scaled model space",title="Ridge conditional coefficients: scales and correlated inputs limit comparison")
    save(fig,"ridge_coefficients","Ridge coefficients (not causal importance)","ridge_coefficients.csv","refit train+validation")
    pd.DataFrame(index).to_csv(out / "figure_index.csv",index=False)
    frozen=read_json(root / design["frozen"])
    lines=["# T13 — Kết quả và thảo luận RQ1–RQ3","",
        f"Issue #32; parent run `{state['parent_run_id']}`. **Test đã được mở và đánh giá**; không coi test là chưa từng xem. Không tuning/chọn lại theo test.","",
        "## Protocol và khả năng truy vết","",
        f"RF A đã chọn bằng validation MAE trong T12, reference `{design['development_selected_run_id']}`. Giữ RF A làm phương án triển khai bất kể thứ tự test. Ridge A alpha0.1 là comparator đã chọn CV T11, không thử B/C hoặc alpha mới trên test. Persistence dùng PM2.5(t).",
        f"Refit hai pipeline trên {len(fit):,} mẫu primary train+validation ({len(train):,}+{len(val):,}); test primary {len(test):,}, cùng IDs/order cho cả ba. Giữ target t+1, station, T08 train-only và hậu xử lý identity. Không đánh giá cohort operational/fallback; primary có PM2.5(t), baseline fallback=0.",
        f"Nhãn fit cuối {audit['latest_fit_target']}, origin test đầu {test.input_timestamp.min()}: label<=origin theo giả định số đo giờ t đã sẵn sàng. Pipeline/imputer/encoder/scaler chỉ fit train+validation, không fit test.",
        "Config trước test: configs/final_evaluation.json và artifact parent/config. Mỗi model có config/metrics/predictions refit+test; ML có pipeline.joblib và summary. is_test=False trong logger là run thật, không phải fixture; partition đánh giá là test.","",
        "## RQ1 — Có cải thiện so với persistence?","",
        "| Model | Run ID | N | MAE (µg/m³) | RMSE (µg/m³) | R² | % MAE giảm persistence |","| --- | --- | --- | --- | --- | --- | --- |"]
    for row in comparison.itertuples():
        lines.append(f"| {row.model} | `{row.run_id}` | {row.n_scored} | {row.MAE:.6f} | {row.RMSE:.6f} | {row.R2:.6f} | {row.mae_reduction_vs_persistence_pct:.4f}% |")
    rf=comparison.loc[comparison.model.eq("random_forest")].iloc[0]
    ridge=comparison.loc[comparison.model.eq("ridge")].iloc[0]
    lines += ["",f"RF có mức giảm MAE {rf.mae_reduction_vs_persistence_pct:.4f}%; Ridge {ridge.mae_reduction_vs_persistence_pct:.4f}%. Dấu âm nghĩa là kém persistence, không ép kết luận cải thiện. Đây là metric theo mẫu primary; chưa chứng minh hiệu quả với origin PM2.5 thiếu hoặc trạm chưa quan sát.","",
        "## Generalization gap và độ ổn định","",
        "generalization_gap.csv giữ train/validation lịch sử (model fit train-only), CV trong train và test final sau refit nhiều dữ liệu hơn. Refit_train_validation là **in-sample**, không gọi validation sau refit là held-out. Chênh lệch còn do phạm vi fit/thời gian/phân phối, không đủ để quy toàn bộ cho overfit/underfit.",
        "| Model | Historical train MAE | Historical validation MAE | Final refit train+validation MAE (in-sample) | Final test MAE | Test − refit MAE |",
        "| --- | --- | --- | --- | --- | --- |"]
    for model in design["models"]:
        history=gap.loc[gap.model.eq(model)]
        train_mae=history.loc[history.partition.eq("development_train_in_sample"),"MAE"].iloc[0]
        val_mae=history.loc[history.partition.eq("development_validation_held_out"),"MAE"].iloc[0]
        final=child_metrics[model]
        lines.append(f"| {model} | {'không ghi nhận' if pd.isna(train_mae) else f'{train_mae:.6f}'} | {val_mae:.6f} | {final['refit_train_validation']['MAE']:.6f} | {final['test_primary']['MAE']:.6f} | {final['test_primary']['MAE']-final['refit_train_validation']['MAE']:.6f} |")
    lines += ["","development_fold_metrics.csv và cv_summary.csv tính lại từ predictions fold Ridge alpha0.1 và PM2.5(t) của cùng train IDs; đây là phân tích mới có reference fold run IDs, không sửa log T11. Bảng gồm MAE/RMSE/R²/%giảm từng fold, pooled và mean/std (ddof0). RF chưa có CV trong ngân sách T11: không tạo fold/std giả.",
        "| Model | CV pooled MAE | Fold mean MAE ± std | CV pooled RMSE |","| --- | --- | --- | --- |"]
    for row in cv.itertuples():lines.append(f"| {row.model} | {row.pooled_MAE:.6f} | {row.MAE_fold_mean:.6f} ± {row.MAE_fold_std:.6f} | {row.pooled_RMSE:.6f} |")
    lines += ["","Train chỉ khoảng2năm, ít chu kỳ mùa. Evaluation fold1 là06–08/2014, thiếu các mùa khác; train fold1 không mặc nhiên thiếu mọi mùa đó. Ba fold có mùa khác nhau, std không chứng minh ổn định mọi năm hoặc là khoảng tin cậy độc lập.","",
        "## RQ2 — Feature và diễn giải","",
        "Test T13 chỉ dùng A cho Ridge/RF để giữ recipe khóa. Đóng góp lag/rolling/selection được trả lời bằng bằng chứng phát triển T12: Ridge A/B/C validation MAE lần lượt "+" / ".join(f"{next(r for r in frozen['validation_results'] if r['variant']==v)['MAE']:.6f}" for v in ("A","B","C"))+"; không coi là kết quả test A/B/C.",
        f"Ridge có {len(coef)} hệ số encoded, lưu coefficient_model_space và hệ số trên đơn vị numeric gốc khi thích hợp; scaling, OHE và biến tương quan làm hạn chế so sánh độ lớn. Không xem hệ số là tác động nhân quả.",
        f"RF permutation dùng {int(perm.n.max())} IDs, chọn tối đa200mẫu/trạm theo thời gian cách đều, seed42,3repeat,1luồng và {perm.group.nunique()} nhóm nguồn (tối đa {perm.group.nunique()*3+1} lượt predict gồm baseline). Lưu exact IDs. Calendar hour/month cùng sin/cos được xáo trộn theo nhóm, categorical xáo raw input giữ OHE cùng nguồn. Đây là chẩn đoán sau scoring, không chọn feature/model theo importance.",
        "Các nhóm tăng MAE lớn nhất: "+", ".join(f"{k}: {v:.4f} µg/m³" for k,v in importance["mean"].sort_values(ascending=False).head(5).items())+". Tương quan/đặc trưng thay thế và mẫu con làm giảm hoặc phân tán importance; permutation cũng có thể tạo tổ hợp ít xuất hiện, không suy thành nhân quả.","",
        "## RQ3 — Sai ở đâu và vì sao?","",
        "grouped_metrics.csv có station/season/concentration/rapid_change/episode_id, N, MAE/RMSE, %giảm persistence và signed error. R² nhóm N<30 hoặc target constant để null/lý do; ngưỡng30 chỉ là quy tắc hiển thị, không đảm bảo độ tin cậy.",
        "Mùa lấy target timestamp. Nhóm nồng độ [0,35),[35,75),[75,150),[150,+∞) chốt từ protocol phát triển, không học từ test/không phải chuẩn sức khỏe. Phân bố train trước test nằm trong preflight.json.",
        f"Thay đổi đột ngột: |y(t+1)−PM2.5(t)|≥{audit['rapid_change_threshold_train_q95']:.6f} µg/m³, là q95 từ train. Sự kiện cao: target≥150 ít nhất3giờ liên tiếp cùng trạm; giờ khuyết tách. Primary có thể làm ngắn sự kiện khi origin/target thiếu. Có {len(events)} sự kiện đủ quy tắc; không xóa đỉnh hợp lệ."]
    for group in ("station","season","concentration","rapid_change"):
        subset=grouped.loc[grouped.group.eq(group)&grouped.model.eq("random_forest")].sort_values("MAE",ascending=False)
        if not subset.empty:
            row=subset.iloc[0]
            lines.append(f"- RF khó nhất theo {group}: {row['value']}, N={int(row.n_scored)}, MAE={row.MAE:.6f}, RMSE={row.RMSE:.6f}, mean(pred−actual)={row.mean_signed_error:.6f} µg/m³.")
    if chosen_event is not None:
        high=test.loc[test.episode_id.eq(chosen_event.episode_id)]
        peak=high.target_pm25.idxmax()
        lines.append(f"Sự kiện vẽ có đỉnh quan sát cao nhất: {chosen_event.episode_id}, peak={chosen_event.peak:.3f} µg/m³; tại đỉnh actual={test.loc[peak,'target_pm25']:.3f}, persistence={predictions['persistence'][peak]:.3f}, Ridge={predictions['ridge'][peak]:.3f}, RF={predictions['random_forest'][peak]:.3f}. Chọn hình để mô tả lỗi, không chọn lại cấu hình.")
    lines += ["","Persistence dùng mức hiện tại nên hợp lý khi nồng độ ổn định, nhưng hụt tăng/giảm đột ngột. Signed error và hình đỉnh cho thấy mức hụt/overshoot thực tế của model. Giả thuyết: A chỉ có số đo hiện tại/lịch, Ridge tuyến tính và RF cây hữu hạn có thể làm trơn đỉnh hoặc thiếu thông tin diễn biến; cần nghiên cứu bằng dữ liệu phát triển ở công việc sau. Đây không phải chứng minh nguyên nhân vật lý, không dùng test để thử sửa tiếp.","",
        "## Hình, tài nguyên, giới hạn và bài giảng","",
        "Chỉ mục figure_index.csv ghi source/run/scope; PNG gốc tại reports/figures/final_evaluation. actual–predicted và histogram giữ tất cả test primary; timeline station chốt trước test, giờ khuyết để NaN; hình đợt cao là chẩn đoán định trước. Model weights/registered SHA trong run directories; hướng dẫn khôi phục artifact ở docs/final_evaluation.md.",
        "Bài giảng áp dụng: chủ đề05 (đánh giá/overfit/underfit),06 (Ridge),Ensemble (RF),04 khi diễn giải selection. File/trang và rubric chi tiết [CẦN BỔ SUNG]; không bịa nội dung bài giảng. Giữ temporal/train-only/no-IQR theo course_alignment.md.",
        "Codex hỗ trợ code/kiểm/soạn nhận xét từ artifact; người nhận hoanglecodingmachine cần đọc/hiểu/review trước merge. Không khẳng định phần review đã hoàn thành. Không có RF temporal CV mới, không có test B/C, không đánh giá unseen stations/cohort fallback, không suy nhân quả. T14–T16 chưa thực hiện.",""]
    (root / "docs/results_discussion.md").write_text("\n".join(lines),encoding="utf-8",newline="\n")
