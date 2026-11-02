"""MK01 DOCX/PPTX from read-only evidence, never a model training entry point."""

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pptx import Presentation
from pptx.util import Inches, Pt as SPt
from pptx.dml.color import RGBColor as SColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN

from beijing_air.midterm_evidence import collect, sha


NAVY, TEAL, GOLD, GRAY = "14324F", "087E8B", "D99A24", "526170"
ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "[CẦN BỔ SUNG]"


def write_json(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def num(value, digits=6):
    if value is None: return "—"
    return f"{value:.{digits}f}".replace(".", ",")


def count(value): return f"{int(value):,}".replace(",", ".")


def charts(root, out, evidence):
    os.environ["MPLCONFIGDIR"] = str(root / "artifacts/midterm_matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    plt.rcParams.update({"font.size": 14, "axes.titlesize": 14, "axes.labelsize": 14, "xtick.labelsize": 13, "ytick.labelsize": 13})
    fig, ax = plt.subplots(figsize=(13, 3.6))
    ax.set(xlim=(0, 13), ylim=(0, 3.6)); ax.axis("off")
    boxes = [(0.1, "Quan sát ≤t\nPM2.5, khí tượng\nstation / wd"), (3.4, "Feature A / B\nPreprocessing\nFit train / fold"),
             (6.7, "Ridge / RF\nC: chọn nhóm\ntrong fold train"), (10, "Dự báo t+1\nValidation\nkhóa phương án")]
    for x, label in boxes:
        ax.add_patch(FancyBboxPatch((x, 1.3), 2.9, 1.2, boxstyle="round,pad=0.05", fc="#E5F3F3", ec="#087E8B"))
        ax.text(x+1.45, 1.9, label, ha="center", va="center", fontsize=18, color="#14324F")
        if x < 10: ax.annotate("", (x+3.25, 1.9), (x+2.95, 1.9), arrowprops={"arrowstyle": "->", "color": "#14324F"})
    ax.text(6.5, .65, "Khóa test • không clipping • không học từ holdout", ha="center", fontsize=17)
    ax.text(6.5, 3.05, "Pipeline thực thi • sơ đồ phương pháp", ha="center", fontsize=19, weight="bold")
    fig.tight_layout(); fig.savefig(out / "pipeline.png", dpi=160); plt.close(fig)
    base = evidence["models"][:3]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, metric in zip(axes, ("MAE", "RMSE")):
        ax.bar(["Persistence", "Ridge A", "RF A"], [r[metric] for r in base], color=["#8C969D", "#087E8B", "#D99A24"])
        ax.set(ylabel=f"Validation {metric} (µg/m³)", title=f"T09/T10 full — same {count(base[0]['N'])} primary IDs")
    fig.tight_layout(); fig.savefig(out / "t10_validation.png", dpi=160); plt.close(fig)
    import pandas as pd
    numeric = pd.DataFrame(evidence["eda_numeric"])
    selected = numeric.loc[numeric.column.ne("target_pm25")].sort_values("missing_pct")
    fig, ax = plt.subplots(figsize=(8, 4.7))
    ax.barh(selected.column, selected.missing_pct, color="#087E8B")
    ax.set(xlabel="Missing (%)", title="Train only: 205,977 observed-target origins")
    fig.tight_layout(); fig.savefig(out / "eda_missing.png", dpi=160); plt.close(fig)
    pearson = pd.read_csv(root / "reports/eda_train/pearson.csv", index_col="column")
    names = [n for n in pearson.index if n != "target_pm25"]
    values = pearson.loc[names, "target_pm25"].sort_values()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(values.index, values, color=["#D99A24" if v < 0 else "#087E8B" for v in values])
    ax.set(xlim=(-1, 1), xlabel="Pearson r with PM2.5(t+1) (dimensionless)", title="Train observed pairs — association, not causation")
    fig.tight_layout(); fig.savefig(out / "eda_correlations.png", dpi=160); plt.close(fig)
    cv = evidence["t11_candidates"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    axes[0].plot([r["alpha"] for r in cv], [r["pooled_MAE"] for r in cv], "o-")
    axes[0].set(xscale="log", xlabel="Ridge alpha", ylabel="Train CV MAE (µg/m³)", title="Select only by CV")
    axes[1].bar(["T10 α=1", "T11 α=0.1"], [evidence["models"][1]["MAE"], evidence["models"][3]["MAE"]])
    axes[1].set(ylabel="Validation MAE (µg/m³)", title="No validation improvement")
    fig.tight_layout(); fig.savefig(out / "t11_summary.png", dpi=160); plt.close(fig)
    cv = evidence["t12_candidates"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    axes[0].plot([r["k_groups"] for r in cv], [r["pooled_MAE"] for r in cv], "o-")
    axes[0].set(xticks=[12, 20, 28], xlabel="Kept raw groups", ylabel="Train CV MAE (µg/m³)", title="Select k only by CV")
    axes[1].bar(["A", "B", "C"], [evidence["models"][i]["MAE"] for i in (3, 4, 5)])
    axes[1].set(ylabel="Validation MAE (µg/m³)", title="Same Ridge α=0.1 / IDs")
    fig.tight_layout(); fig.savefig(out / "t12_summary.png", dpi=160); plt.close(fig)


def trace_entries(root, output):
    specs = [
        ("B01", "table", "Nguồn dữ liệu và nhóm thuộc tính", ["reports/raw_audit_full.json", "docs/data_dictionary.md"], [], "audit raw"),
        ("B02", "table", "Temporal split và cohorts", ["reports/splits_full/split_summary.csv", "reports/splits_full/split_manifest.json"], [], "audit T05, test chỉ count/date"),
        ("B03", "table", "EDA train: missing và phân phối", ["reports/eda_train/numeric_summary.csv"], [], "train operational"),
        ("B04", "table", "Kết quả T09/T10", ["reports/initial_models/comparison.csv"], [r["run_id"] for r in output["models"][:3]], "validation full primary"),
        ("B05", "table", "T11 CV và trước–sau", ["reports/tuning/candidates.csv", "reports/tuning/before_after.csv"], ["c895894bcf5a4ff28982fbb1ca9d69d9", output["models"][3]["run_id"]], "train CV + validation riêng"),
        ("B06", "table", "T12 A/B/C và đối chứng", ["reports/ablation/comparison.csv", "reports/ablation/selected_features.csv"], [r["run_id"] for r in output["models"]], "validation full primary"),
        ("B07", "table", "Các vòng thử–nhận xét–quyết định", ["docs/initial_findings.md", "docs/tuning_findings.md", "docs/ablation_findings.md"], [], "phân tích từ artifact"),
        ("F01", "figure", "Missing trên train", ["reports/midterm/figures/eda_missing.png", "reports/eda_train/numeric_summary.csv"], [], "train operational"),
        ("F02", "figure", "Tương quan train", ["reports/midterm/figures/eda_correlations.png", "reports/eda_train/correlation_pairs.csv", "reports/eda_train/pearson.csv"], [], "train; tương quan không là nhân quả"),
        ("F03", "figure", "Sơ đồ pipeline", ["reports/midterm/figures/pipeline.png", "src/beijing_air/preprocessing.py", "src/beijing_air/feature_selection.py"], [], "sơ đồ phương pháp"),
        ("F04", "figure", "T09/T10 validation", ["reports/midterm/figures/t10_validation.png", "reports/initial_models/comparison.csv"], [r["run_id"] for r in output["models"][:3]], "validation full primary"),
        ("F05", "figure", "T11 CV và validation", ["reports/midterm/figures/t11_summary.png", "reports/tuning/candidates.csv", "reports/tuning/before_after.csv"], ["c895894bcf5a4ff28982fbb1ca9d69d9"], "CV train / validation tách nhãn"),
        ("F06", "figure", "T12 ablation", ["reports/midterm/figures/t12_summary.png", "reports/ablation/comparison.csv"], ["0a616a9fb5134058b3af3cafb1a70e18"], "CV train / validation tách nhãn"),
    ]
    entries = []
    for key, kind, title, paths, runs, scope in specs:
        entries.append({"id": key, "kind": kind, "title": title, "scope": scope, "run_ids": runs,
                        "sources": [{"path": p, "sha256": sha(root / p)} for p in paths]})
    return entries


def doc_style(doc):
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.top_margin, s.bottom_margin = Cm(1.8), Cm(1.7)
    s.left_margin, s.right_margin = Cm(2), Cm(2)
    for style in ("Normal", "Body Text"):
        doc.styles[style].font.name = "Arial"; doc.styles[style].font.size = Pt(11)
        doc.styles[style].paragraph_format.space_after = Pt(6)
        doc.styles[style].paragraph_format.line_spacing = 1.12
    for style, size in (("Title", 25), ("Heading 1", 18), ("Heading 2", 13)):
        doc.styles[style].font.name = "Arial"; doc.styles[style].font.size = Pt(size)
        doc.styles[style].font.color.rgb = RGBColor.from_string(NAVY)
    footer = s.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = footer.add_run("NhomXX • BẢN NHÁP • chỉ validation/CV • "); r.font.size = Pt(8)
    field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE"); footer._p.append(field)
    footer.add_run(" / ").font.size = Pt(8)
    field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "NUMPAGES"); footer._p.append(field)
    header = s.header.paragraphs[0]
    header.add_run("MÁY HỌC | PM2.5 BẮC KINH | BÁO CÁO TIẾN ĐỘ").font.size = Pt(8)


def para(doc, text, *, bold=False, size=None):
    p = doc.add_paragraph()
    r = p.add_run(text); r.bold = bold
    if size: r.font.size = Pt(size)
    return p


def table(doc, headers, rows, caption, size=9):
    para(doc, caption, bold=True, size=10)
    t = doc.add_table(rows=1, cols=len(headers)); t.style = "Light Shading Accent 1"
    for cell, name in zip(t.rows[0].cells, headers): cell.text = str(name)
    repeat = OxmlElement("w:tblHeader"); t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        cells = t.add_row().cells
        for cell, value in zip(cells, row): cell.text = str(value)
    for row in t.rows:
        nosplit = OxmlElement("w:cantSplit"); row._tr.get_or_add_trPr().append(nosplit)
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(3); p.paragraph_format.space_before = Pt(2)
                for r in p.runs: r.font.name = "Arial"; r.font.size = Pt(size)
    return t


def picture(doc, root, relative, caption, width=16.5):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(root / relative), width=Cm(width))
    p = para(doc, caption, size=9); p.paragraph_format.space_after = Pt(6)


def page(doc, title):
    doc.add_page_break(); doc.add_heading(title, 1)


def build_doc(root, out, e, trace):
    doc = Document(); doc_style(doc)
    c, models = e["config"], e["models"]
    by = {m["label"]: m for m in models}
    doc.core_properties.title = c["title"]
    doc.core_properties.author = "Nhóm [CẦN BỔ SUNG]"
    doc.core_properties.subject = "Bản nháp giữa kỳ từ minh chứng validation/CV; chưa test"
    para(doc, "BÁO CÁO TIẾN ĐỘ GIỮA KỲ", bold=True, size=18)
    doc.add_heading(c["title"], 0)
    para(doc, "Học phần: Máy học • Nhóm: "+(str(c["group_number"]) if c["group_number"] else PLACEHOLDER), bold=True)
    for key, label in (("institution", "Trường/khoa"), ("class_code", "Lớp"), ("lecturer", "Giảng viên")):
        para(doc, label+": "+(c.get(key) or PLACEHOLDER))
    para(doc, "BẢN NHÁP — CHƯA SẴN SÀNG NỘP", bold=True, size=16)
    para(doc, "Người dùng sẽ tự bổ sung danh tính, phân công/đóng góp và rubric. Không suy thông tin này từ Git author.")
    para(doc, "Phạm vi đã có minh chứng: T01–T12. Trọng tâm giữa kỳ: baseline và hai model T09/T10; T11/T12 là kết quả bổ sung. Chưa refit train+validation, mở test, triển khai demo hoặc đánh giá cuối.")
    para(doc, "Snapshot nguồn khoa học: "+(e["source_commit"] or "không có Git"), size=9)
    para(doc, "Tổng hợp: "+datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M UTC+07"), size=9)
    picture(doc, root, "reports/midterm/figures/pipeline.png", "F03 — Sơ đồ phương pháp từ pipeline thực thi; không phải kết quả dự báo.", 16)

    page(doc, "1. Tóm tắt tiến độ và thông tin nhóm")
    para(doc, "Repo hiện có pipeline tái lập cho dự báo PM2.5 đúng một giờ tại 12 trạm đã quan sát. Các số liệu dưới đây thuộc validation/CV, không phải test. Kết quả tốt nhất trong pool phát triển là RF A T10, MAE "+num(by["RF A T10"]["MAE"])+" µg/m³; persistence là mốc mạnh, MAE "+num(by["Persistence T09"]["MAE"])+".")
    para(doc, "Ridge ban đầu kém persistence về MAE. T11 chọn alpha=0.1 bằng CV nhưng validation chưa cải thiện. T12 lag/rolling và selection nhóm giúp Ridge; C12 nhóm có MAE "+num(by["Ridge C T12"]["MAE"])+", vẫn kém RF A và persistence về MAE. Không che giấu kết quả bất lợi.")
    members = c["members"] or [{"name": PLACEHOLDER, "student_id": PLACEHOLDER, "work": PLACEHOLDER, "evidence": PLACEHOLDER}]
    table(doc, ["Họ tên", "MSSV", "Công việc thật", "Minh chứng/xác nhận"],
          [[m.get("name", PLACEHOLDER), m.get("student_id", PLACEHOLDER), m.get("work", PLACEHOLDER), m.get("evidence", PLACEHOLDER)] for m in members], "Thông tin nhóm — dòng mẫu không hàm ý nhóm chỉ có một thành viên")
    para(doc, "Phân công, tỷ lệ hoặc đóng góp học thuật chưa được xác nhận: "+PLACEHOLDER+". Nhóm cần điền từng người, công việc, thời điểm và minh chứng thực tế; không quy người chạy script thành người thực hiện toàn bộ nghiên cứu.")
    table(doc, ["Trạng thái", "Nội dung"], [["Đã làm", "T01–T12: audit, EDA train, feature, pipeline, baseline/model, CV và ablation; 49 hồ sơ run có phân cấp, không phải 49 model độc lập."],
          ["Đang làm", "MK01 tổng hợp/kiểm tài liệu; nhóm bổ sung danh tính và đóng góp."], ["Chưa làm", "T13 test cuối/refit, T14 demo, T15/T16 cuối kỳ; MK02 chỉ sau MK01."]], "Tiến độ dựa trên artifact, không chỉ trạng thái Issue")
    para(doc, "Thiếu bắt buộc/chưa xác minh: "+"; ".join(e["missing"])+". Các ô này làm sản phẩm là bản nháp.")

    page(doc, "2. Business Understanding: bài toán và CRISP-DM")
    para(doc, "Tại trạm s, sau khi số đo giờ t đã sẵn sàng, dự báo nồng độ PM2.5(s,t+1). Đây là hồi quy có giám sát, đơn vị µg/m³. Input chỉ chứa quan sát ≤t và thông tin lịch t+1 biết trước; output là một giá trị dự báo, không phải phân lớp chất lượng không khí.")
    table(doc, ["Thành phần", "Đặc tả"], [["Input", "PM2.5 và chất ô nhiễm/khí tượng tại t, station/wd, lịch t+1; B bổ sung history PM2.5 cùng trạm."],
          ["Output", "ŷ(s,t+1), ghép target quan sát đúng timestamp+1h cùng trạm."], ["Phạm vi", "Dự báo cuốn chiếu một bước cho các trạm đã xuất hiện; chưa khẳng định cho trạm mới."],
          ["Giả định", "Số đo t đã được cung cấp trước khi phát dự báo; chưa mô hình hóa độ trễ truyền cảm biến."], ["Tiêu chí", "MAE chính, RMSE/R² bổ sung; so cùng sample IDs và coverage."]], "Hợp đồng Input/Output")
    table(doc, ["RQ", "Câu hỏi và minh chứng hiện tại"], [["RQ1", "ML có hơn persistence? RF A cải thiện nhẹ validation MAE; Ridge A chưa thắng."],
          ["RQ2", "A→B→C ảnh hưởng thế nào? T12 cho thấy lợi ích có điều kiện ở Ridge alpha cố định; không thắng mọi metric/model."],
          ["RQ3", "Sai số theo trạm/mùa/nồng độ? Có mô tả baseline validation; phân tích cuối độc lập sau khóa/T13, chưa có test metric."]], "Câu hỏi nghiên cứu")
    para(doc, "CRISP-DM [S02] tổ chức sáu pha: hiểu bài toán → hiểu dữ liệu → chuẩn bị dữ liệu → mô hình hóa → đánh giá → triển khai. Tiến trình có vòng lặp: câu hỏi/giả thuyết → thiết kế/ngân sách → thực thi → nhận xét → quyết định. Task quản lý không đồng nghĩa một vòng thử hay một model.")

    page(doc, "3. Data Understanding: nguồn và thuộc tính")
    para(doc, "Nguồn: Beijing Multi-Site Air Quality, UCI dataset 501, Chen (2017), DOI 10.24432/C5RK5G, CC BY 4.0 [S01]. Đây là PRSA2017 nhiều trạm, không thay bằng Beijing PM2.5 một trạm. Số dưới đây từ audit raw đã lưu, không tải/audit lại trong MK01.")
    table(doc, ["Hạng mục", "Audit thực tế"], [["Quy mô raw", "12 file/trạm ×35.064 dòng =420.768 dòng, 18 cột/file."], ["Thời gian", "2013-03-01 00:00 đến 2017-02-28 23:00, giờ nguồn naive."],
          ["Truy vết", "reports/data_manifest.json; raw_audit_full.json; checksum raw/ZIP; không đoán ngày tải."], ["License", "CC BY 4.0, ghi tác giả/nguồn và các thay đổi xử lý."]], "B01 — Nguồn/quy mô; nguồn raw_audit_full.json và data_manifest.json")
    table(doc, ["Nhóm cột", "Ý nghĩa/đơn vị", "Vai trò"], [["No", "Số thứ tự bản ghi", "Không dùng làm feature"], ["year/month/day/hour", "Thời gian giờ nguồn", "Tạo timestamp, kiểm thứ tự/khóa"],
          ["PM2.5, PM10, SO2, NO2, CO, O3", "Nồng độ µg/m³", "Số đo tại t; PM2.5 đúng t+1 là target"], ["TEMP, DEWP", "Nhiệt độ/điểm sương °C", "Numeric tại t"],
          ["PRES / RAIN / WSPM", "hPa / mm / m/s", "Numeric tại t"], ["station / wd", "Mã trạm / hướng gió", "Categorical, one-hot train-only"]], "Từ điển rút gọn — chi tiết docs/data_dictionary.md")
    para(doc, "Raw thiếu được giữ nguyên; không impute trước chia tập. Các thống kê EDA có điều kiện trên train với target quan sát; không coi là đại diện không thiên lệch của toàn bộ raw. Đợt nồng độ cao hợp lệ được giữ, cờ IQR không mặc định là lỗi.")

    page(doc, "4. Data Preparation: audit, target và temporal split")
    para(doc, "T04 kiểm timestamp/schema, khóa station–timestamp, trùng dòng/trùng khóa mâu thuẫn, missing và giờ khuyết. Audit ghi 0 timestamp không hợp lệ/trùng ở raw; không âm thầm lấy dòng đầu khi khóa xung đột. Dữ liệu hợp nhất chưa impute và không xóa nồng độ cao bằng IQR.")
    para(doc, "T05 ghép target bằng khóa (station,t+1h), không shift(-1) mù qua giờ khuyết; target thiếu bị loại, không được impute. Giữ sample ID, origin timestamp và target timestamp. Primary yêu cầu PM2.5(t) đã quan sát; operational giữ origin thiếu nhưng có target để audit/fallback.")
    splitrows = []
    for name, label in (("train", "Train"), ("validation", "Validation"), ("test", "Test khóa — audit sẵn có")):
        vals = {r["cohort"]: r for r in e["split_summary"] if r["split"] == name}
        splitrows.append([label, count(vals["operational"]["samples"]), count(vals["primary"]["samples"]), str(vals["primary"]["target_timestamp_min"])[:10]+" → "+str(vals["primary"]["target_timestamp_max"])[:10]])
    table(doc, ["Tập", "Operational N", "Primary N", "Khoảng target (inclusive audit)"], splitrows, "B02 — Temporal split theo target; số test chỉ đọc audit T05 cũ, không mở test set")
    para(doc, "Ranh giới dùng chung mọi trạm: train target<2015-03-01; validation từ2015-03-01 đến trước2016-03-01; test từ2016-03-01. Test chỉ có count/date audit, chưa có metric và không dùng để quyết định giữa kỳ.")
    table(doc, ["Fold", "Eval targets [start,end)", "Fit N", "Eval N", "Purge N"],
          [[f["fold_id"], f["evaluation_start"][:10]+" → "+f["evaluation_end_exclusive"][:10], count(f["fit"]["samples"]), count(f["evaluation"]["samples"]), f["purged"]["samples"]] for f in e["cv_folds"]], "Ba expanding-window folds trong train — artifact T11/T12")
    para(doc, "CV yêu cầu max(fit.target)<min(eval.origin), purge nhãn ở origin đầu. Mỗi fold fit lại toàn pipeline. Holdout theo quy ước nhãn tại t đã sẵn sàng (≤origin); không đổi mốc split để lấy score tốt.")

    page(doc, "5. EDA train: missing, phân phối và ngoại lệ")
    n = {r["column"]: r for r in e["eda_numeric"]}
    table(doc, ["Biến", "Missing %", "Median", "Mean", "Max"], [[name, num(n[name]["missing_pct"], 3), num(n[name]["q50"], 2), num(n[name]["mean"], 2), num(n[name]["max"], 2)] for name in ("PM2.5", "CO", "TEMP", "WSPM")], "B03 — 205.977 operational train origins có target quan sát; đơn vị theo B01")
    picture(doc, root, "reports/midterm/figures/eda_missing.png", "F01 — Missing theo biến trên train, vẽ lại cho bố cục giữa kỳ từ T06/numeric_summary.csv; khác biệt trạm ở bảng station_missing_pct.csv.", 16)
    para(doc, "Nhận xét: CO thiếu nhiều nhất trong nhóm numeric, "+num(n["CO"]["missing_pct"], 2)+"%; PM2.5(t) thiếu "+count(n["PM2.5"]["missing"])+" origins. Missing khác giữa trạm; T08 dùng median và indicator chỉ fit train/fold, không backfill.")
    para(doc, "PM2.5(t) median61, mean83,88 và skew1,64; q99=350, max844 µg/m³. Có7.678 cờ IQR nhưng không coi là7.678 lỗi: giữ đợt cao, không clipping target. Numeric khác thang đo nên Ridge scale; RF không bắt buộc scale. Nguồn B03/F01; số liệu không là metric dự báo.")

    page(doc, "6. EDA train: đa biến, thời gian và quyết định")
    picture(doc, root, "reports/midterm/figures/eda_correlations.png", "F02 — Pearson với nhãn t+1 trên train; target không đưa vào X. Nguồn T06/pearson.csv; số cặp ở correlation_pairs.csv.", 15.5)
    para(doc, "T06 ghi Pearson PM2.5(t) với target(t+1)≈0,965 và PM10≈0,842; đây là liên hệ mô tả, không là causal effect hoặc bằng chứng model phải thắng. Persistence là đối chứng mạnh vì tính liên tục theo giờ.")
    para(doc, "EDA còn có hồ sơ giờ/tháng/mùa, daily timeline, khác biệt trạm và autocorrelation đúng timestamp (figures07–09, bảng hourly/monthly/seasonal/autocorrelation). Median PM2.5 theo trạm từ45 đến68 µg/m³. Ghi nhận chu kỳ và phụ thuộc thời gian làm cơ sở A/B, không random split.")
    para(doc, "Quyết định T07/T08: giữ station/wd, thêm lịch biết trước và lag/rolling đúng giờ/cùng trạm; không nội suy tương lai; xử lý NA bằng pipeline. EDA chỉ train để ra quyết định; không EDA test. Hạn chế: pairwise observed và cohort có target có thể gây chọn mẫu; phụ thuộc thời gian/trạm làm tương quan gộp dễ bị hiểu sai.")

    page(doc, "7. Feature và preprocessing pipeline")
    table(doc, ["Bộ", "Nội dung", "Số nhóm/cột raw"], [["A", "11 số đo tại t +station/wd +lịch t+1 +sin/cos giờ/tháng", "20"], ["B", "A +lags1/3/6/12/24h +rolling mean/std3/6/12/24h kết thúc t", "33"],
          ["C T12", "Subset B chọn bởi grouped pilot Ridge; k12 qua CV", "12 nhóm, 24 encoded model columns"]], "Feature engineering A→B và feature selection B→C là hai thay đổi riêng")
    picture(doc, root, "reports/midterm/figures/pipeline.png", "F03 — Pipeline thực trong repo; selector C nằm sau preprocessing và trước Ridge cuối.")
    para(doc, "Numeric: median train-only, giữ cột toàn NA và indicator. Categorical: missing token cố định, one-hot handle_unknown=ignore. Ridge scale numeric; RF không scale. Từng fold fit lại imputer/encoder/scaler/selector, không preprocess toàn train trước CV.")
    para(doc, "Lag đúng timestamp, rolling min_periods=window, ddof1, chỉ ≤t; không tạo mẫu giả ở giờ không quan sát. C chọn nguyên nhóm numeric+indicator hoặc mọi OHE cùng source. Pilot Ridge xếp nhóm bằng RMS coefficient; scoring phụ thuộc encoding/collinearity, không là importance vật lý.")
    para(doc, "Postprocessing thống nhất identity, không âm thầm clip dự báo âm. Module/tests đã kiểm causal perturbation, missing, unknown category, clone/save-load và feature names trên fixture; không gọi test fixture là run model full.")

    page(doc, "8. Persistence baseline và thiết kế đánh giá")
    para(doc, "T09 đặt mốc yhat(s,t+1)=PM2.5(s,t). Khi thiếu số đo tại t: dùng số đo quá khứ gần nhất cùng trạm tuổi≤24h, sau đó median trạm/global học trên train; không lấy tương lai. Ghi nguồn dự báo, tuổi history và tỷ lệ fallback, không bỏ ID để giảm metric.")
    baseline = by["Persistence T09"]
    para(doc, "Kết quả chính trên primary (PM2.5(t) có thật), N="+count(baseline["N"])+": MAE "+num(baseline["MAE"])+", RMSE "+num(baseline["RMSE"])+" µg/m³, R² "+num(baseline["R2"])+". Primary không dùng fallback vì số đo t đã có. Cohort operational được ghi riêng ở T09; không trộn hai cohort để so model.")
    table(doc, ["Quy tắc", "Áp dụng"], [["Sample IDs", "Các model chính cùng102.479 primary validation IDs/thứ tự, coverage100%."], ["Metric", "MAE=mean|e|; RMSE=sqrt(mean e²); R²=1−SSE/SST, null nếu không xác định."],
          ["Smoke/full", "Smoke kiểm thực thi trên tập con; chỉ full validation/CV dùng kết luận chính."], ["Ngân sách", "T10 một cấu hình full/model; T11 bốn alpha; T12 ba mức k. Không grid vô hạn."], ["Test gate", "Chỉ sau khóa và khi T13 được giao mới refit train+validation/chấm test."]], "Thiết kế đánh giá chống leakage")
    para(doc, "Log T04-LOG cung cấp UUID/config/metadata/metrics/artifacts và status/error. Parent/candidate/fold phản ánh quản lý tuning, không được đếm thành49 model độc lập. MK01 chỉ đọc kiểm chứng, không tạo run hoặc thay timestamp/metric.")

    page(doc, "9. Kết quả chính T09/T10: hai model ban đầu")
    table(doc, ["Full validation", "MAE", "RMSE", "R²", "N"], [[m["label"], num(m["MAE"]), num(m["RMSE"]), num(m["R2"]), count(m["N"])] for m in models[:3]], "B04 — Cùng primary validation; MAE/RMSE µg/m³, R² không đơn vị")
    picture(doc, root, "reports/midterm/figures/t10_validation.png", "F04 — Bảng B04 vẽ lại từ artifact full T09/T10, không dùng smoke.")
    para(doc, "RF A giảm MAE khoảng1,80% so persistence. Ridge A MAE kém hơn khoảng4,76% nhưng RMSE tốt nhất ở vòng ban đầu. Không tuyên bố một model thắng mọi tiêu chí hoặc cải thiện chắc chắn ngoài split này.")
    para(doc, "Config chốt trước score: Ridge alpha1; RF80trees/depth12/min leaf2/max_features1/seed42/n_jobs1, BLAS1. RF giới hạn theo RAM, không chọn từ sweep validation. Fit T10 Ridge≈2,96s, RF≈161,22s trên máy hiện tại; không là benchmark máy sạch.")
    para(doc, "Train MAE Ridge11,286320 / RF9,837287; validation lần lượt10,200433 /9,561488. Gap MAE âm không chứng minh không overfit; RF RMSE tăng từ16,664335 train lên18,964825 validation. Ridge có2.685 dự báo validation âm được giữ đúng identity. Nguồn B04, metadata/metrics run T10.")

    page(doc, "10. Bổ sung T11: tuning theo thời gian")
    table(doc, ["Alpha", "Pooled CV MAE", "CV RMSE", "Fold MAE mean±std"],
          [[r["alpha"], num(r["pooled_MAE"]), num(r["pooled_RMSE"]), num(r["fold_mean_MAE"])+" ± "+num(r["fold_std_MAE"])] for r in e["t11_candidates"]], "B05 — 3 expanding windows trong train; std ddof0, cùng76.102 OOF IDs")
    picture(doc, root, "reports/midterm/figures/t11_summary.png", "F05 — CV dùng chọn alpha và validation đánh giá sau chọn; hai loại score tách rõ.")
    para(doc, "CV chọn alpha0.1, pooled MAE10,405534 so alpha1 10,412704. Sau refit toàn train, validation MAE10,200529 so T10 10,200433: tăng0,000096837, chưa cải thiện. Không tăng search sau khi thấy kết quả.")
    para(doc, "Ngân sách12fit CV+1refit, chỉ Ridge do chi phí/RAM. Mean/std fold là mô tả biến thiên, không là confidence interval; fold train chồng lấn, không nested CV. Giữ kết quả bất lợi và giả thuyết cho T12, không ép tuning phải thắng.")

    page(doc, "11. Bổ sung T12: A/B/C và khóa công thức")
    abc = [by[n] for n in ("Ridge A T11", "Ridge B T12", "Ridge C T12")]
    table(doc, ["Ridge alpha0.1", "Chiều model", "Validation MAE", "RMSE", "R²"],
          [[m["label"], dim, num(m["MAE"]), num(m["RMSE"]), num(m["R2"])] for m, dim in zip(abc, (65, 91, 24))], "B06 — A reuse T11; B/C full mới, cùng IDs/params/preprocessing")
    picture(doc, root, "reports/midterm/figures/t12_summary.png", "F06 — k chọn bằng train CV và A/B/C trên validation; đối chứng RF/persistence ở comparison.csv.")
    para(doc, "RQ2 có điều kiện: B cải thiện MAE so A; C chọn12/33 nhóm, MAE cải thiện thêm nhẹ nhưng RMSE kém B. C giữ numeric+indicator thành24 chiều; station/wd bị bỏ nguyên nhóm. Không suy feature bị bỏ vô ích vật lý, vì lag/rolling tương quan và scoring phụ thuộc encoding.")
    para(doc, "Ngân sách9pipeline CV (pilot+final) +2pipeline B/C final, tổng21 estimator fits full. Không fit thêm A/RF. Frozen config chọn RF A T10 vì MAE9,561488 vẫn thấp nhất pool gồm A/B/C, RF A và persistence; không đổi tiêu chí sang RMSE sau score.")
    para(doc, "Frozen là công thức với data/split provenance, A20, RF80/depth12/min leaf2/seed42/n_jobs1, preprocessing T08 RF và identity. Chưa có model weights triển khai, chưa refit train+validation/test. C vẫn tạo/preprocess toàn B trước mask, nên ít chiều không tự chứng minh giảm mọi chi phí inference.")

    page(doc, "12. Các vòng thử–nhận xét–quyết định")
    table(doc, ["Vòng/giả thuyết", "Bằng chứng", "Nhận xét/quyết định"], [["T09: xác định mốc persistence", "Validation MAE9,736617 trên primary", "Mốc mạnh cho t+1; giữ fallback causal cho operational."],
          ["T10: đo hiện tại/lịch có giúp?", "RF MAE9,561488; Ridge10,200433", "RF cải thiện nhỏ; Ridge kém MAE nhưng tốt RMSE; giữ cả hai."],
          ["T11: đổi alpha giúp Ridge?", "CV thắng nhỏ, validation10,200529", "Chưa cải thiện validation; không sweep tiếp hoặc che kết quả kém."],
          ["T12: history và selection nhóm?", "B9,968755; C9,903377; dims91→24", "Hữu ích trong Ridge cố định; chưa thắng RF/persistence MAE. Khóa RF A cho bước sau."]], "B07 — Vòng lặp CRISP-DM từ log thật, không dựng lịch sử cải tiến")
    para(doc, "Những gì học được: hiệu quả phụ thuộc metric, model và split; tuning/selection không mặc định tốt. So sánh feature cố định alpha giúp cô lập thay đổi nhưng chưa tối ưu riêng B/C. CV dùng lại sau T11 và validation đã xem nhiều lần làm score phát triển có thể lạc quan; chưa là đánh giá độc lập.")
    para(doc, "Giữ traceability: run_id → config/metrics/predictions → bảng/hình → báo cáo/slide. Audit dữ liệu/EDA không giả làm model log. Kiểm trước tài liệu đã đối chiếu "+str(e["checks"]["runs"])+" hồ sơ, "+str(e["checks"]["artifacts_checked"])+" artifact và tính lại "+str(e["checks"]["prediction_files_recomputed"])+" file prediction, không mở test samples.")

    page(doc, "13. Khó khăn, kế hoạch và đóng góp cần xác nhận")
    table(doc, ["Khó khăn/giới hạn", "Cách xử lý và phần còn lại"], [["Missing và đợt nồng độ cao", "Giữ raw/target thật; pipeline train-only, không xóa IQR. Chưa xác minh độc lập mọi sensor/outlier."],
          ["RAM/thời gian", "RF1job/depth12/80trees; Ridge tuning hữu hạn, BLAS1; chưa benchmark máy sạch."], ["Rò rỉ thời gian", "Exact-hour target/lag, temporal split, purge; cần tiếp tục kiểm trong refit/inference."],
          ["Ridge âm, tương quan/selection", "Giữ identity, không đổi rule theo test; score feature không là nhân quả."], ["Hồ sơ nhóm/rubric", PLACEHOLDER+" — nhóm tự xác nhận trước khi nộp."]], "Khó khăn và trách nhiệm xử lý")
    table(doc, ["Bước còn lại", "Điều kiện/đầu ra", "Người phụ trách/thời hạn"], [["MK02", "Kiểm notebook/source/log/tài liệu, ZIP bản nháp và manifest", PLACEHOLDER],
          ["T13 — chưa làm", "Khi được giao: refit train+validation theo công thức khóa, test một lần và phân tích sai số", PLACEHOLDER], ["T14 — chưa làm", "Demo dùng pipeline/model được chọn, không feature tương lai", PLACEHOLDER],
          ["T15/T16 — chưa làm", "Báo cáo cuối5chương, slide và kiểm tái lập/gói cuối", PLACEHOLDER]], "Kế hoạch theo phụ thuộc, không đoán deadline/phân công")
    para(doc, "Đóng góp thật từng người: "+PLACEHOLDER+". Điền bảng thành viên ở mục1 bằng công việc/minh chứng đã xác nhận, không suy từ account GitHub/Git author hoặc số commit. Không tạo tỷ lệ đóng góp giả.")
    para(doc, "Chưa sẵn sàng nộp: số nhóm/tên–MSSV/đóng góp và rubric chưa được xác nhận. Hạn nộp/định dạng riêng của thầy cần bổ sung. Người dùng tự điền các mục này; chưa nộp Classroom.", bold=True)

    page(doc, "14. Nguồn, AI disclosure và kiểm tra")
    for source in c["sources"]:
        para(doc, source["id"]+" — "+source["title"]+"\n"+source["url"], size=10)
    para(doc, "Nguồn nội bộ: data_manifest/raw_audit_full; split_manifest; bảng/hình EDA T06; experiment_log.csv và metrics/predictions từng run. Báo cáo nguồn được kiểm ở snapshot nêu trên; không mượn metric từ nghiên cứu bên ngoài.")
    para(doc, "AI disclosure", bold=True)
    para(doc, c["ai_disclosure"])
    para(doc, "Kiểm tra đã có: T12 ghi243passed/1deselected (ca T04 raw/full có test bỏ theo scope), gồm12tests T12. Đây là bằng chứng task trước, không phải khẳng định MK01 đã chạy lại bộ tests đó. MK01 chỉ xác minh artifact, DOCX/PPTX và render; kết quả chi tiết ở build_manifest.json/verification.json.")
    para(doc, "Cần nhóm bổ sung trước nộp", bold=True)
    for label in e["missing"]: para(doc, "• "+label+": "+PLACEHOLDER)
    para(doc, "Rubric riêng của thầy chưa có. Bộ tài liệu bao phủ yêu cầu đã được người dùng cung cấp, chưa được gọi là đạt mọi rubric chưa biết. Test metric/weights triển khai không phải phần được tạo trong báo cáo giữa kỳ.")

    page(doc, "15. Phụ lục: chỉ mục truy vết bảng/hình")
    table(doc, ["ID", "Nội dung", "Phạm vi / nguồn chính"], [[t["id"], t["title"], t["scope"]+"\n"+t["sources"][0]["path"]] for t in trace], "Chỉ mục B01–B07, F01–F06 — hash và mọi source file ở traceability.json", size=8.5)
    para(doc, "Các đường dẫn là tương đối từ root đồ án, không là link máy cá nhân. Với ZIP MK02, root source giữ nguyên cấu trúc experiments/artifacts/reports. Mọi hình/bảng là artifact hoặc vẽ lại từ artifact đã kiểm; F03 là sơ đồ phương pháp có nhãn riêng.", size=9)

    page(doc, "16. Phụ lục: run registry và cách đọc")
    table(doc, ["Run alias", "UUID đầy đủ", "Task/mode/partition"], [[m["label"], m["run_id"], m["task_id"]+" / full / primary validation"] for m in models], "Các run trực tiếp cung cấp metric trong báo cáo/slide", size=9)
    para(doc, "Đường dẫn chung: artifacts/experiments/<UUID>/config.json, metadata.json, metrics.json và artifacts/predictions/. CSV tổng hợp liên kết tương đối tới các file này. Mode smoke không được dùng làm score chính; candidate/fold có parent_run_id và fold_id, không là model độc lập.")
    para(doc, "T11 search c895894bcf5a4ff28982fbb1ca9d69d9; T12 search 0a616a9fb5134058b3af3cafb1a70e18. T11 chọn alpha bằng pooled train CV; T12 chọn k bằng CV và deployment bằng validation. Child IDs đầy đủ trong parent artifacts/search/results.json.", size=9)
    para(doc, "Ledger SHA-256: "+e["checks"]["ledger_sha256"], size=8)
    para(doc, "Tái tạo tài liệu: cài optional dependencies midterm, chạy scripts/build_midterm.py, render bằng scripts/render_midterm.ps1, rồi scripts/verify_midterm.py. Không gọi script run_baseline/run_tuning/run_ablation để làm báo cáo. Muốn kiểm lại metric chỉ đọc predictions, không tạo run mới.")
    para(doc, "BẢN NHÁP — nhóm cần hoàn tất danh tính/phân công/đóng góp/rubric trước khi nộp.", bold=True)
    path = out / (c["filename_stem"]+".docx"); doc.save(path)
    return path


def textbox(slide, text, x, y, w, h, size=20, color=NAVY, bold=False):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = shape.text_frame; frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(.03)
    for i, line in enumerate(text.split("\n")):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.text = line; p.font.name = "Arial"; p.font.size = SPt(size); p.font.bold = bold; p.font.color.rgb = SColor.from_string(color)
        p.space_after = SPt(8)
    return shape


def slide_base(prs, title, number, source):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.background.fill; background.solid(); background.fore_color.rgb = SColor(250, 252, 253)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = SColor.from_string(TEAL); bar.line.fill.background()
    textbox(slide, title, .45, .35, 10.8, .8, 28, bold=True)
    textbox(slide, "BẢN NHÁP\nNhomXX", 11.65, .3, 1.2, .6, 12, color=GOLD, bold=True)
    textbox(slide, source, .45, 6.95, 11.5, .4, 9, color=GRAY)
    textbox(slide, f"{number:02d}/15", 12.2, 6.95, .65, .35, 10, color=GRAY)
    return slide


def stable(slide, headers, rows, x=.5, y=1.6, w=12.25, height=3.2, font=17):
    shape = slide.shapes.add_table(len(rows)+1, len(headers), Inches(x), Inches(y), Inches(w), Inches(height))
    t = shape.table
    for i, row in enumerate([headers]+rows):
        for j, text in enumerate(row):
            cell = t.cell(i, j); cell.text = str(text)
            cell.margin_left = cell.margin_right = Inches(.09)
            cell.fill.solid(); cell.fill.fore_color.rgb = SColor.from_string(NAVY if i == 0 else ("EEF6F7" if i%2 else "FFFFFF"))
            for p in cell.text_frame.paragraphs:
                p.font.name = "Arial"; p.font.size = SPt(font); p.font.bold = i == 0
                p.font.color.rgb = SColor.from_string("FFFFFF" if i == 0 else NAVY)
    return shape


def simage(slide, root, relative, x, y, w, h):
    from PIL import Image
    with Image.open(root / relative) as im: ratio = im.width/im.height
    if w/h > ratio: w = h*ratio
    else: h = w/ratio
    slide.shapes.add_picture(str(root / relative), Inches(x), Inches(y), width=Inches(w), height=Inches(h))


def notes(slide, text): slide.notes_slide.notes_text_frame.text = text


def build_slides(root, out, e):
    prs = Presentation(); prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    prs.core_properties.title = e["config"]["title"]
    prs.core_properties.author = "Nhóm [CẦN BỔ SUNG]; tài liệu hỗ trợ bởi Codex"
    models = e["models"]
    s = slide_base(prs, "DỰ BÁO PM2.5 TRƯỚC 1 GIỜ", 1, "MK01 | Bản nháp tiến độ, chưa sẵn sàng nộp | Không có test metric")
    textbox(s, "Tại các trạm quan trắc Bắc Kinh\nBáo cáo giữa kỳ môn Máy học", .7, 1.65, 11.6, 1.2, 30, bold=True)
    textbox(s, "NhomXX • Thành viên / MSSV / giảng viên: [CẦN BỔ SUNG]\nMinh chứng đến T12 • Trọng tâm T09/T10 • Chưa T13/test", .7, 3.2, 11.6, 1.25, 22)
    textbox(s, "49 hồ sơ log ≠ 49 model độc lập", .7, 5.3, 11, .6, 24, color=TEAL, bold=True)
    notes(s, e["config"]["title"]+"\nSource snapshot: "+e["source_commit"]+"\n"+e["config"]["ai_disclosure"])

    s = slide_base(prs, "NHÓM VÀ TIẾN ĐỘ THỰC TẾ", 2, "Nguồn: project_plan.md; metadata chưa có xác nhận nhóm")
    stable(s, ["Đã có minh chứng", "Đang làm", "Chưa làm"], [["T01–T08: dữ liệu/EDA/pipeline", "MK01 + nhóm bổ sung thông tin", "T13 test cuối / refit"], ["T09/T10: baseline + 2model", "MK02 sau MK01", "T14 demo; T15/T16 cuối kỳ"], ["T11/T12: CV + A/B/C", "Xác nhận phân công/đóng góp", "Chưa có weights triển khai"]], height=2.6, font=18)
    textbox(s, "Tên–MSSV, số nhóm, việc từng người, minh chứng và rubric: [CẦN BỔ SUNG]\nKhông suy đóng góp từ Git author hoặc số commit.", .65, 4.65, 12, 1.25, 22)
    notes(s, "Người dùng xác nhận tự bổ sung nhóm. Các ô thiếu phải giữ nguyên; chưa gọi bản này là sẵn sàng nộp.")

    s = slide_base(prs, "BÀI TOÁN: INPUT ĐẾN t → OUTPUT ĐÚNG t+1", 3, "Nguồn: problem_definition.md; B01/B02; horizon=1h, cùng station")
    textbox(s, "Input: số đo tại t + station/wd + lịch t+1 biết trước\nB thêm lag/rolling PM2.5 cùng trạm, không tương lai\nOutput: một nồng độ PM2.5(s,t+1), đơn vị µg/m³", .65, 1.65, 12, 2.1, 23)
    stable(s, ["RQ1", "RQ2", "RQ3"], [["ML hơn persistence?", "Lag/rolling và selection giúp thế nào?", "Sai số theo trạm/mùa/nồng độ?"], ["T09/T10 có validation thật", "T12 ablation cố định params", "Chưa có đánh giá test cuối"]], y=4.25, height=1.75, font=17)
    notes(s, "Giả định số đo t đã sẵn sàng; rolling one-hour ở trạm đã quan sát. MAE chính, RMSE/R² bổ sung; không đổi sang phân lớp AQI.")

    s = slide_base(prs, "CRISP-DM LÀ VÒNG LẶP, KHÔNG CHỈ DANH SÁCH TASK", 4, "Nguồn S02 (IBM); mapping project_plan.md")
    labels = [("Hiểu bài toán", "T02: RQ, Input/Output"), ("Hiểu dữ liệu", "T03/T04/T06: audit + EDA"), ("Chuẩn bị dữ liệu", "T05/T07/T08: causal pipeline"), ("Mô hình hóa", "T09–T12: baseline/CV/A-B-C"), ("Đánh giá", "Validation phát triển; test khóa"), ("Triển khai", "MK01/MK02; T14 chưa làm")]
    for i, (title, body) in enumerate(labels):
        x, y = .55+(i%3)*4.2, 1.65+(i//3)*1.65
        textbox(s, title, x, y, 3.9, .5, 22, bold=True, color=TEAL)
        textbox(s, body, x, y+.55, 3.9, .8, 18)
    textbox(s, "Giả thuyết → ngân sách → chạy → nhận xét → giữ/sửa/thử tiếp", .65, 5.65, 12, .6, 22, bold=True)
    notes(s, "S02: https://www.ibm.com/docs/en/spss-modeler/18.6.0?topic=dm-crisp-help-overview . T11 không cải thiện vẫn giữ log, không tạo lịch sử cải tiến giả.")

    s = slide_base(prs, "DỮ LIỆU UCI 501: NHIỀU TRẠM, THEO GIỜ", 5, "B01 | S01 Chen (2017), DOI 10.24432/C5RK5G, CC BY 4.0 | audit raw đã có")
    textbox(s, "12 trạm • 420.768 dòng • 18 cột raw\n2013-03-01 → 2017-02-28\nPRSA2017, không phải Beijing PM2.5 một trạm", .65, 1.6, 12, 1.75, 26, bold=True)
    stable(s, ["Nhóm biến", "Đơn vị/vai trò"], [["PM2.5/PM10/SO2/NO2/CO/O3", "µg/m³; tại t là input, PM2.5 t+1 là nhãn"], ["TEMP/DEWP; PRES; RAIN; WSPM", "°C; hPa; mm; m/s"], ["station/wd; thời gian; No", "Categorical; tạo timestamp; loại No khỏi feature"]], y=3.75, height=2.25, font=18)
    notes(s, "Nguồn raw_audit_full.json, data_manifest.json và docs/data_dictionary.md. Counts từ audit thực tế, không gán theo số công bố. Raw không đổi; không tải lại ở MK01.")

    s = slide_base(prs, "TARGET VÀ SPLIT: KHÓA TEST, KHÔNG RANDOM K-FOLD", 6, "B02 | splits_full/split_summary.csv; test chỉ count/date audit sẵn có")
    stable(s, ["Tập", "Primary N", "Ranh giới target"], [["Train", "204.865", "<2015-03-01"], ["Validation", "102.479", "[2015-03-01,2016-03-01)"], ["Test — khóa", "101.836 (audit)", "≥2016-03-01; chưa metric"]], height=2.5, font=20)
    textbox(s, "Join đúng (station,t+1h), không shift qua giờ khuyết; không impute target.\n3 expanding folds trong train, purge nhãn tại origin đầu đánh giá.\nFit lại mọi bước học dữ liệu ở train/fold-train; same IDs khi so model.", .65, 4.55, 12, 1.7, 21)
    notes(s, "Operational train205977/validation103287/test102753; primary cần PM2.5(t). Các số test chỉ đọc audit cũ, không mở test.csv. Folds T11: Jun–Sep2014, Sep–Dec2014, Dec2014–Mar2015, strict fit target<first eval origin.")

    s = slide_base(prs, "EDA TRAIN → QUYẾT ĐỊNH XỬ LÝ", 7, "F01/B03 | T06: 205.977 operational train origins, không EDA test")
    simage(s, root, "reports/midterm/figures/eda_missing.png", .5, 1.55, 7.7, 4.65)
    textbox(s, "CO thiếu 6,74%\nPM2.5(t) thiếu 1.112 origins\nPM2.5 median61; max844 µg/m³\nGiữ đợt cao; không xóa IQR\nKhác biệt trạm + chu kỳ thời gian\n→ median/indicator, scale Ridge, A/B causal", 8.55, 1.7, 4.1, 4.85, 20)
    notes(s, "B03 numeric_summary.csv: PM2.5 mean83.8821, skew1.6368, q99=350, max844; IQR flags7678 không là lỗi đã xác minh. F02/correlation_pairs: r(PM2.5t,target)=.965, không là nhân quả. T06 còn có calendar/timeline/autocorrelation và bảng nguồn.")

    s = slide_base(prs, "PIPELINE VÀ A/B/C: KHÁC NHAU Ở ĐÂU?", 8, "F03 | T07/T08/T12 modules; feature engineering khác feature selection")
    simage(s, root, "reports/midterm/figures/pipeline.png", .5, 1.45, 12.3, 2.8)
    textbox(s, "A20: số đo t + station/wd + lịch t+1\nB33: A + lag1/3/6/12/24h + rolling mean/std3/6/12/24h\nC: subset nhóm từ B; OHE và indicator giữ cùng source\nRidge scale, RF không scale; identity output, không clipping", .65, 4.55, 12, 1.9, 21)
    notes(s, "C: pilot Ridge fit trong từng fold sau preprocess, RMS coefficients theo raw group; C12giữ24 encoded numeric+indicator. Đây là ranking phụ thuộc encoding/collinearity, không causal importance.")

    s = slide_base(prs, "PERSISTENCE LÀ MỐC MẠNH CHO t+1", 9, "T09 full: 24cef47874a94d9faa7bfcbae29b5c58 | primary validation102479")
    textbox(s, "Có PM2.5(s,t): dự báo đúng giá trị đó\nNếu thiếu: lịch sử cùng trạm tuổi≤24h → median trạm/global từ train\nKhông lấy tương lai; giữ ID và log nguồn/tỷ lệ fallback", .65, 1.6, 12, 1.9, 24)
    stable(s, ["MAE (µg/m³)", "RMSE (µg/m³)", "R²"], [[num(models[0]["MAE"]), num(models[0]["RMSE"]), num(models[0]["R2"])]], y=4.05, height=1.35, font=24)
    textbox(s, "Primary có số đo t nên không fallback; operational ghi riêng.\nKhông trộn cohorts hoặc dùng smoke làm score chính.", .65, 5.7, 12, .9, 20)
    notes(s, "Metrics primary from T09 full. Baseline train statistic fit from operational train205977 origins; val comparison primary102479. Không tạo thêm baseline trong MK01.")

    s = slide_base(prs, "T10: RF CẢI THIỆN NHẸ MAE, RIDGE TỐT RMSE", 10, "B04/F04 | T09/T10 full, cùng102479 primary IDs | chi tiết UUID trong DOCX/traceability")
    simage(s, root, "reports/midterm/figures/t10_validation.png", .5, 1.45, 8.35, 3.3)
    textbox(s, "RF A: MAE9,561488\n≈giảm1,80% so baseline\nRidge A: MAE10,200433\nnhưng RMSE18,907140 thấp nhất vòng đầu", 9.05, 1.65, 3.7, 3.3, 20)
    stable(s, ["Config cố định", "Chi phí fit T10", "Giới hạn"], [["Ridge alpha1; RF80/depth12/leaf2/seed42/job1", "Ridge≈2,96s; RF≈161,22s", "Một split; Ridge có2685 dự báo âm, giữ identity"]], y=5.15, height=1.25, font=15)
    notes(s, "Run IDs: "+"; ".join(m["label"]+':'+m["run_id"] for m in models[:3])+". Validation MAE/RMSE/R2 in DOCX B04. Gap MAE âm không chứng minh không overfit; RF trainRMSE16.664335<val18.964825.")

    s = slide_base(prs, "T11: CV THẮNG NHỎ, VALIDATION CHƯA CẢI THIỆN", 11, "B05/F05 | 12 CV fits +1refit; chỉ Ridge, không test")
    simage(s, root, "reports/midterm/figures/t11_summary.png", .5, 1.55, 8.2, 3.5)
    textbox(s, "Alpha {0.1,1,10,100}\n3 expanding folds train\nCV chọn alpha0.1\nValidation MAE10,200529\nT10:10,200433 → hơi kém\nGiữ kết quả, không sweep tiếp", 9, 1.65, 3.75, 4.3, 21)
    textbox(s, "Pooled MAE dùng chọn; mean/std fold chỉ mô tả biến thiên, không confidence interval.", .65, 5.85, 12, .6, 20)
    notes(s, "Search c895894bcf5a4ff28982fbb1ca9d69d9; selected refit32e65c5a4cbc489c905cf146b743867f. CV pooledMAE10.405534 so10.412704 alpha1. Validation tăng.000096837; không ép tuning luôn tốt.")

    s = slide_base(prs, "T12 / RQ2: HISTORY VÀ SELECTION GIÚP RIDGE", 12, "B06/F06 | k chọn CV; A/B/C cùng Ridge alpha0.1, validation IDs; RF reuse")
    stable(s, ["Ridge A/B/C", "Chiều model", "Validation MAE", "RMSE"], [["A (reuse T11)", 65, "10,200529", "18,907198"], ["B (+history)", 91, "9,968755", "18,467071"], ["C (12nhóm CV)", 24, "9,903377", "18,501063"]], height=2.5, font=20)
    textbox(s, "C giảm MAE nhẹ so B nhưng RMSE tăng nhẹ; không thắng mọi metric.\nRF A T10 vẫn tốt nhất pool MAE9,561488 → khóa công thức RF A.\nChưa weights triển khai, refit train+validation hoặc test/T13.", .65, 4.55, 12, 1.7, 22)
    notes(s, "B48d2f03be4614a25906f84d98df9e9dc; C3a9f2500e4dd4ef28d7bc20def6f79c8; search0a616a9fb5134058b3af3cafb1a70e18. Fixed alpha selected on A may disadvantage B/C; C still preprocess full B. Frozen RF80/depth12/leaf2/max_features1/seed42/job1, no numeric scaling, identity.")

    s = slide_base(prs, "VÒNG THỬ → NHẬN XÉT → QUYẾT ĐỊNH", 13, "B07 | Artifact giữ cả kết quả kém; audit/EDA không giả làm model log")
    stable(s, ["Vòng", "Quan sát", "Quyết định"], [["T09", "Persistence mạnh ở horizon1h", "Giữ đối chứng cùng IDs/fallback causal"], ["T10", "RF hơn nhẹ MAE; Ridge kém MAE", "Giữ cả tốt/kém và trade-off RMSE/cost"], ["T11", "Alpha CV tốt, val chưa cải thiện", "Không tăng budget sau score"], ["T12", "C ít chiều +MAE tốt hơn B", "Chưa thắng RF; freeze theo criterion đã chốt"]], height=3.6, font=18)
    textbox(s, "Validation dùng nhiều lần; CV không nested, feature tương quan → chưa là kết luận test độc lập.", .65, 5.65, 12, .8, 21, color=TEAL)
    notes(s, "49 hồ sơ gồm search/candidate/fold/smoke, không49model. Chênh model so baseline không là tác động causal; không tạo lịch sử giả để dựng cải tiến.")

    s = slide_base(prs, "KHÓ KHĂN, PHẦN CÒN LẠI VÀ ĐÓNG GÓP", 14, "Nguồn: project_plan/midterm_plan; không tự đặt deadline/phân công")
    textbox(s, "Khó khăn: missing, đợt ô nhiễm cao, leakage thời gian, RAM/cost.\nCách làm: giữ raw, pipeline train-only, purge, budget hữu hạn, log cả kém.\nMK02: kiểm/gói, không huấn luyện thêm hoặc nộp Classroom.\nT13–T16: chỉ khi được giao, refit/test → demo → hồ sơ/kiểm cuối.\nTên–MSSV, công việc, minh chứng/đóng góp và hạn nộp: [CẦN BỔ SUNG]\nChưa benchmark máy sạch hoặc có serialized weights để inference.", .65, 1.65, 12, 4.8, 23)
    notes(s, "Không đoán tỷ lệ đóng góp. Người dùng đã xác nhận sẽ tự bổ sung nhóm. Đóng gói nháp khi còn thiếu bắt buộc, không gọi sẵn sàng nộp.")

    s = slide_base(prs, "NGUỒN, AI DISCLOSURE VÀ VIỆC NHÓM CẦN ĐIỀN", 15, "Nguồn/UUID/hash đầy đủ: DOCX phụ lục; reports/midterm/traceability.json")
    textbox(s, "S01 Chen(2017), UCI501 • DOI10.24432/C5RK5G • CC BY4.0\nS02 IBM CRISP-DM; S03/S04 scikit-learn Ridge/RandomForest\nSố liệu riêng: audit/EDA và predictions/log của repo, không mượn metric ngoài\nCodex hỗ trợ mã, chạy/kiểm đã giao, tổng hợp và tạo tài liệu; nhóm tự kiểm và chịu trách nhiệm\n[CẦN BỔ SUNG]: nhóm, thành viên, đóng góp, rubric/yêu cầu riêng, deadline\nBẢN NHÁP — CHƯA SẴN SÀNG NỘP • Chưa mở test", .65, 1.6, 12, 4.95, 22)
    notes(s, e["config"]["ai_disclosure"]+"\n"+"\n".join(x["id"]+" "+x["url"] for x in e["config"]["sources"]))
    assert len(prs.slides) == 15
    path = out / (e["config"]["filename_stem"]+".pptx"); prs.save(path)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.parse_args()
    out = ROOT / "reports/midterm"; out.mkdir(parents=True, exist_ok=True)
    figures = out / "figures"; figures.mkdir(exist_ok=True)
    e = collect(ROOT)
    write_json(out / "evidence.json", e)
    charts(ROOT, figures, e)
    trace = trace_entries(ROOT, e)
    write_json(out / "traceability.json", trace)
    import csv
    with (out / "figure_table_index.csv").open("w", encoding="utf-8", newline="") as stream:
        w = csv.writer(stream); w.writerow(["id", "kind", "title", "scope", "run_ids", "source_paths"])
        for t in trace: w.writerow([t["id"], t["kind"], t["title"], t["scope"], ";".join(t["run_ids"]), ";".join(s["path"] for s in t["sources"])])
    paths = [build_doc(ROOT, out, e, trace), build_slides(ROOT, out, e)]
    (out / "NEEDS_GROUP_INPUT.md").write_text("# BẢN NHÁP — nội dung nhóm tự bổ sung\n\n"+"\n".join("- [CẦN BỔ SUNG] "+m for m in e["missing"])+"\n\nSửa configs/midterm.json và chạy lại generator/render; không thay lịch sử model. Chưa sẵn sàng nộp.\n", encoding="utf-8")
    manifest = {"task_id": "MK01", "draft": e["draft"], "missing": e["missing"], "checks": e["checks"], "slides": 15,
                "source_commit": e["source_commit"], "model_fit_performed": False, "test_samples_accessed": False,
                "files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p), "bytes": p.stat().st_size} for p in paths],
                "generator_sha256": sha(Path(__file__)), "evidence_module_sha256": sha(ROOT / "src/beijing_air/midterm_evidence.py")}
    write_json(out / "build_manifest.json", manifest)
    print(json.dumps({"status": "DRAFT", "files": [str(p.relative_to(ROOT)) for p in paths], "checks": e["checks"]}, ensure_ascii=False))


if __name__ == "__main__": main()
