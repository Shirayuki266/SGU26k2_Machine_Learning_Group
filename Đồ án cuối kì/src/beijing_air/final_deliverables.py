"""Build T15 report, slides, poster, and source-linked verification artifacts.

This module reads only existing summary artifacts and source documentation. It
does not train models, read raw test samples, or write to the experiment ledger.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor as PptColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches as PptInches, Pt as PptPt


ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER = "[CẦN BỔ SUNG]"
NAVY = "14324F"
TEAL = "087E8B"
GOLD = "D99A24"
PALE = "EAF3F5"
INK = "243746"
GRAY = "647482"
T13_RUNS = {
    "persistence": "0960fac6455f4380bd5b6d1407633cf8",
    "ridge": "51975d2c66ff4263b83ace6962f3d3f7",
    "random_forest": "24cd6d765f214d52aa26e5988380e2cd",
}
T17B_PARENT_RUN = "2512bc9c844a4b39a150c52f6bded9db"
T17B_ROWS = {
    "rolling_mean_3h": "068d8c0a9f1f4ac8a1ed8e366810c5a2",
    "same_target_hour_yesterday": "9840ae4d73ec445b81ef9c66602d724b",
    "decision_tree_B": "eecf89f226e44f448d8d4a98e6a8cde0",
    "lasso_B": "9c6b003eae2348b68f389c84c88a2b83",
    "hist_gradient_boosting_B": "414f8aff5cd44fcab1919616c7e9ea90",
    "random_forest_B": "0524feb701164bf397e22ecbffa1c1cd",
    "random_forest_B_tuned": "8169e7b42226418ea898f7957c9aa400",
    "fusion_3": "e708283791cf4bafb4e75f21984855a4",
    "oof_ridge_stack": "b09e47f628624116a8272135767a4ada",
}
FIGURES = {
    "eda_missing": "reports/figures/eda_train/01_missing.png",
    "eda_calendar": "reports/figures/eda_train/07_calendar.png",
    "t13_actual_predicted": "reports/figures/final_evaluation/actual_predicted.png",
    "t13_group_errors": "reports/figures/final_evaluation/group_errors.png",
    "t13_high_pollution": "reports/figures/final_evaluation/high_pollution_episode.png",
    "t13_permutation": "reports/figures/final_evaluation/rf_permutation.png",
    "t13_coefficients": "reports/figures/final_evaluation/ridge_coefficients.png",
    "t13_timeline": "reports/figures/final_evaluation/timeline.png",
    "t17b_validation": "reports/tables/t17b_validation_comparison.png",
    "demo_screenshot": "reports/demo/screenshots/02_forecast.png",
}
TABLES = [
    ("T01", "Thành viên, phần việc và tỷ lệ đóng góp", ["docs/team_contributions.md"]),
    ("T02", "Quy mô dữ liệu và kiểm định chất lượng", ["configs/uci_501.json", "reports/raw_audit_full.json"]),
    ("T03", "Phân chia thời gian và số mẫu", ["reports/splits_full/split_summary.csv"]),
    ("T04", "Kết quả T13 trên Test primary", ["reports/final_evaluation/comparison.csv"]),
    ("T05", "Tổng quát hóa và khoảng cách train/test", ["reports/final_evaluation/generalization_gap.csv"]),
    ("T06", "Độ ổn định ba fold trong Train", ["reports/final_evaluation/development_fold_metrics.csv"]),
    ("T07", "Sai số theo trạm/mùa/nồng độ/biến đổi nhanh", ["reports/final_evaluation/grouped_metrics.csv"]),
    ("T08", "Hành trình T09–T12", ["reports/initial_models/comparison.csv", "reports/tuning/candidates.csv", "reports/ablation/comparison.csv"]),
    ("T09", "Tổng hợp 27 cấu hình T17a/T17b", ["reports/tables/experiment_summary.csv"]),
    ("T10", "Chỉ số Validation T17b", ["reports/tables/experiment_summary.csv"]),
    ("T11", "Hệ số Ridge", ["reports/final_evaluation/ridge_coefficients.csv"]),
    ("T12", "Permutation importance theo nhóm", ["reports/final_evaluation/rf_permutation_summary.csv"]),
]
FIGURE_INDEX = [
    ("H01", "Missing và phân phối EDA trên Train", FIGURES["eda_missing"]),
    ("H02", "Mùa/tháng EDA trên Train", FIGURES["eda_calendar"]),
    ("H03", "Actual so với dự báo trên Test T13", FIGURES["t13_actual_predicted"]),
    ("H04", "Sai số nhóm Test T13", FIGURES["t13_group_errors"]),
    ("H05", "Đợt ô nhiễm cao Test T13", FIGURES["t13_high_pollution"]),
    ("H06", "Permutation importance RF", FIGURES["t13_permutation"]),
    ("H07", "Hệ số Ridge", FIGURES["t13_coefficients"]),
    ("H08", "Timeline Test T13", FIGURES["t13_timeline"]),
    ("H09", "So sánh Validation T17b", FIGURES["t17b_validation"]),
    ("H10", "Ảnh thật Demo Streamlit T14", FIGURES["demo_screenshot"]),
]
REQUIRED_SOURCES = [
    ".gitattributes",
    ".gitignore",
    "README.md",
    "configs/final_deliverables.json",
    "configs/uci_501.json",
    "configs/final_evaluation.json",
    "configs/supplementary_experiments.json",
    "reports/raw_audit_full.json",
    "reports/quality_full/summary.json",
    "reports/splits_full/split_manifest.json",
    "reports/splits_full/split_summary.csv",
    "reports/eda_train/numeric_summary.csv",
    "reports/eda_train/seasonal.csv",
    "reports/initial_models/comparison.csv",
    "reports/tuning/candidates.csv",
    "reports/ablation/comparison.csv",
    "reports/ablation/frozen_model.json",
    "reports/final_evaluation/comparison.csv",
    "reports/final_evaluation/grouped_metrics.csv",
    "reports/final_evaluation/episodes.csv",
    "reports/final_evaluation/generalization_gap.csv",
    "reports/final_evaluation/development_fold_metrics.csv",
    "reports/final_evaluation/rf_permutation_summary.csv",
    "reports/final_evaluation/ridge_coefficients.csv",
    "reports/final_evaluation/final_model.json",
    "reports/final_evaluation/execution.json",
    "reports/final_evaluation/verification.json",
    "reports/tables/experiment_summary.csv",
    "reports/tables/t17b_validation_comparison.png",
    "docs/codex_workflow.md",
    "docs/final_deliverables.md",
    "docs/references.md",
    "docs/related_work_notes.md",
    "docs/submission_checklist.md",
    "docs/github_workflow.md",
    "docs/final_stage_requirements.md",
    "docs/course_alignment.md",
    "docs/team_contributions.md",
    "docs/ai_disclosure.md",
    "src/beijing_air/final_deliverables.py",
    "scripts/build_final_deliverables.py",
    "scripts/verify_final_deliverables.py",
    "tests/test_final_deliverables.py",
    "docs/results_discussion.md",
    "docs/final_evaluation.md",
    "docs/experiment_summary_readme.md",
    "docs/t17b_design.md",
    "docs/supplementary_experiments.md",
    "docs/demo.md",
    "docs/demo_video_storyboard.md",
    "docs/changelog_issue35.md",
    "reports/demo/qa.json",
    "reports/demo/browser_verification.json",
    "reports/issue35/qa.json",
    "reports/issue35/after.json",
    "docs/notebook_code_map.md",
    "docs/project_journey.md",
    "reports/notebook/journey_verification.json",
    "notebooks/PM25_Project_Journey_T01_T14.ipynb",
    "experiments/experiment_log.csv",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def safe_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def protected_snapshot(root: Path) -> dict:
    ledger = root / "experiments/experiment_log.csv"
    midterm = root / "reports/midterm"
    if not ledger.is_file() or not midterm.is_dir():
        raise FileNotFoundError("Required protected history is missing")
    entries = []
    for path in sorted(p for p in midterm.rglob("*") if p.is_file()):
        entries.append({"path": safe_relative(root, path), "sha256": sha256(path), "bytes": path.stat().st_size})
    tree_hash = hashlib.sha256(
        "\n".join(f"{row['path']}:{row['sha256']}:{row['bytes']}" for row in entries).encode("utf-8")
    ).hexdigest()
    return {
        "ledger_sha256": sha256(ledger),
        "midterm_file_count": len(entries),
        "midterm_tree_sha256": tree_hash,
        "midterm_files": entries,
    }


def _number(value: str | float | int | None):
    if value in (None, ""):
        return None
    return float(value)


def _index(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in rows}


def _assert_close(actual: float, expected: float, label: str, tolerance: float = 1e-8):
    if abs(actual - expected) > tolerance:
        raise ValueError(f"{label} differs from its verified artifact: {actual} != {expected}")


def collect_evidence(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    missing = [relative for relative in REQUIRED_SOURCES if not (root / relative).is_file()]
    missing += [path for path in FIGURES.values() if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError("Missing evidence files: " + ", ".join(missing))

    dataset = read_json(root / "configs/uci_501.json")
    split = read_csv(root / "reports/splits_full/split_summary.csv")
    split_counts = {(r["cohort"], r["split"]): int(r["samples"]) for r in split}
    comparison = _index(read_csv(root / "reports/final_evaluation/comparison.csv"), "model")
    summary = read_csv(root / "reports/tables/experiment_summary.csv")
    summary_by_run = {row["run_id (validation/CV)"]: row for row in summary}
    groups = read_csv(root / "reports/final_evaluation/grouped_metrics.csv")
    episode_rows = read_csv(root / "reports/final_evaluation/episodes.csv")
    final_model = read_json(root / "reports/final_evaluation/final_model.json")
    t13_exec = read_json(root / "reports/final_evaluation/execution.json")
    issue35 = read_json(root / "reports/issue35/after.json")
    demo = read_json(root / "reports/demo/qa.json")
    journey = read_json(root / "reports/notebook/journey_verification.json")

    if dataset["dataset_id"] != 501 or dataset["published_rows"] != 420768 or dataset["published_stations"] != 12:
        raise ValueError("UCI dataset metadata differs from the project source")
    if split_counts.get(("operational", "train")) != 205977:
        raise ValueError("Train split counts do not match split_summary.csv")
    expected_split = {
        ("primary", "train"): 204865,
        ("primary", "validation"): 102479,
        ("primary", "test"): 101836,
        ("operational", "validation"): 103287,
        ("operational", "test"): 102753,
    }
    if any(split_counts.get(k) != v for k, v in expected_split.items()):
        raise ValueError("Primary/operational split counts differ from source")

    models = {}
    expected = {
        "persistence": (T13_RUNS["persistence"], 10.161809183392906, 19.436188081133132, 0.9449753346094043, 0.0),
        "ridge": (T13_RUNS["ridge"], 10.384442508805602, 18.939486569257028, 0.9477517646173637, -2.1908827591108277),
        "random_forest": (T13_RUNS["random_forest"], 9.877149899523696, 18.56963395188441, 0.9497724597810346, 2.8012657857659757),
    }
    for name, (run_id, mae, rmse, r2, reduction) in expected.items():
        row = comparison[name]
        if row["run_id"] != run_id or int(row["n_scored"]) != 101836:
            raise ValueError(f"T13 run or cohort differs for {name}")
        for field, value in (("MAE", mae), ("RMSE", rmse), ("R2", r2), ("mae_reduction_vs_persistence_pct", reduction)):
            _assert_close(float(row[field]), value, f"T13 {name} {field}")
        models[name] = {
            "run_id": run_id, "MAE": mae, "RMSE": rmse, "R2": r2,
            "mae_reduction_pct": reduction, "N": 101836, "coverage": 1.0,
        }
    if not final_model["test_has_been_exposed"] or final_model["test_used_for_selection"]:
        raise ValueError("T13 test exposure/selection provenance is inconsistent")
    if final_model["selected_model"] != "random_forest" or final_model["selected_by"] != "development_validation_MAE":
        raise ValueError("T13 frozen model-selection provenance differs")

    t17b = {}
    for name, run_id in T17B_ROWS.items():
        row = summary_by_run.get(run_id)
        if not row or row["Trạng thái"] != "completed" or not row["Validation MAE"]:
            raise ValueError(f"Missing completed T17b validation row for {name}")
        t17b[name] = {
            "label": row["Method"],
            "validation_MAE": float(row["Validation MAE"]),
            "validation_RMSE": float(row["Validation RMSE"]),
            "validation_R2": float(row["Validation R²"]),
            "mae_reduction_pct": float(row["Δ MAE validation so với persistence (%)"]),
            "run_id": run_id,
            "N": int(row["Validation N"]),
            "locked": row["Đã khóa (T12/T13)"].lower() == "true",
        }
    if len(summary) != 27:
        raise ValueError(f"Expected 27 T17a/T17b summary rows, found {len(summary)}")
    if t17b["oof_ridge_stack"]["validation_MAE"] >= t17b["fusion_3"]["validation_MAE"]:
        raise ValueError("T17b stack comparison is inconsistent with summary")

    grouped = {}
    selectors = {
        ("station", "Dingling", "random_forest"),
        ("station", "Wanshouxigong", "random_forest"),
        ("station", "Dingling", "persistence"),
        ("season", "JJA", "random_forest"),
        ("season", "DJF", "random_forest"),
        ("concentration", "[150.0, inf)", "random_forest"),
        ("rapid_change", "True", "random_forest"),
    }
    for row in groups:
        key = (row["group"], row["value"], row["model"])
        if key in selectors:
            grouped["|".join(key)] = {
                "group": row["group"], "value": row["value"], "model": row["model"],
                "n": int(row["n_scored"]), "MAE": float(row["MAE"]),
                "RMSE": float(row["RMSE"]), "mean_signed_error": float(row["mean_signed_error"]),
                "mae_reduction_pct": float(row["mae_reduction_vs_persistence_pct"]),
            }
    missing_groups = [key for key in selectors if "|".join(key) not in grouped]
    if missing_groups:
        raise ValueError(f"Missing grouped metric rows: {missing_groups}")
    event = next((row for row in episode_rows if row["episode_id"] == "Nongzhanguan__20170127T21"), None)
    if not event or float(event["peak"]) != 835:
        raise ValueError("Peak pollution event differs from the saved episodes artifact")

    # Call out mismatches instead of printing prompt figures as if they were artifact values.
    conflicts = [
        {
            "item": "RF Dingling test MAE",
            "requested_value": 8.6287,
            "artifact_value": grouped["station|Dingling|random_forest"]["MAE"],
            "source": "reports/final_evaluation/grouped_metrics.csv",
        },
        {
            "item": "RF JJA test MAE",
            "requested_value": 6.6666,
            "artifact_value": grouped["season|JJA|random_forest"]["MAE"],
            "source": "reports/final_evaluation/grouped_metrics.csv",
        },
        {
            "item": "T17b first full failure run",
            "requested_value": "3cc5790dd34d4ca29435f4da86b68ae7",
            "artifact_value": None,
            "source": "experiments/experiment_log.csv",
            "note": "The run ID was not found in the current ledger or artifacts; supplementary_experiments.md describes the recorded first full attempt as a Stack metadata failure.",
        },
    ]
    _assert_close(
        round(grouped["station|Dingling|random_forest"]["MAE"], 4),
        8.5951,
        "RF Dingling grouped MAE",
    )
    _assert_close(
        round(grouped["season|JJA|random_forest"]["MAE"], 4),
        7.6437,
        "RF JJA grouped MAE",
    )

    source_paths = set(REQUIRED_SOURCES) | set(FIGURES.values())
    source_paths.update(path for _, _, paths in TABLES for path in paths)
    hashes = {
        path: {"sha256": sha256(root / path), "bytes": (root / path).stat().st_size}
        for path in sorted(source_paths)
    }
    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, encoding="utf-8"
        ).strip()
        authors = subprocess.check_output(
            ["git", "log", "HEAD", "--format=%an"], cwd=root, text=True, encoding="utf-8"
        ).splitlines()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Unable to read local Git history for report provenance") from exc
    author_counts = {}
    for author in authors:
        author_counts[author] = author_counts.get(author, 0) + 1
    ledger = read_csv(root / "experiments/experiment_log.csv")
    ledger_by_run = {row.get("run_id"): row for row in ledger}
    if ledger_by_run.get(T17B_PARENT_RUN, {}).get("status") != "completed":
        raise ValueError(f"T17b parent run is missing or incomplete: {T17B_PARENT_RUN}")
    failed_t17b_run = "3cc5790dd34d4ca29435f4da86b68ae7" in ledger_by_run
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "dataset": dataset,
        "split_counts": split_counts,
        "models": models,
        "t17b": t17b,
        "grouped_metrics": grouped,
        "peak_episode": event,
        "summary_rows": len(summary),
        "summary_run_ids": [row["run_id (validation/CV)"] for row in summary],
        "t17b_parent_run_id": T17B_PARENT_RUN,
        "locked_model": final_model,
        "t13_execution": t13_exec,
        "issue35": issue35,
        "demo": demo,
        "journey": journey,
        "source_hashes": hashes,
        "git_author_commit_counts": author_counts,
        "git_commit_count": len(authors),
        "ledger_rows": len(ledger),
        "t17b_requested_failed_run_found": failed_t17b_run,
        "evidence_conflicts": conflicts,
        "protected_snapshot": protected_snapshot(root),
        "metrics_scope": "Existing saved aggregate artifacts only; no test raw input or model fit.",
    }


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _doc_defaults(doc: Document):
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(1.7), Cm(1.7)
    section.left_margin, section.right_margin = Cm(1.8), Cm(1.8)
    for name in ("Normal", "Body Text"):
        style = doc.styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(10.5)
        style.paragraph_format.space_after = Pt(5)
        style.paragraph_format.line_spacing = 1.08
    for name, size in (("Title", 24), ("Heading 1", 17), ("Heading 2", 13), ("Heading 3", 11)):
        style = doc.styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(NAVY)
    section.header.paragraphs[0].text = "MÁY HỌC | PM2.5 BẮC KINH | T15"
    section.header.paragraphs[0].runs[0].font.size = Pt(8)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("NhomXX • BẢN NHÁP • ").font.size = Pt(8)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)


def _p(doc: Document, text: str, bold: bool = False, size: int | None = None):
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    return para


def _table(doc: Document, headers: list[str], rows: list[list], caption: str, font_size: int = 8):
    _p(doc, caption, bold=True, size=9)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Shading Accent 1"
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = str(value)
    header = OxmlElement("w:tblHeader")
    table.rows[0]._tr.get_or_add_trPr().append(header)
    for values in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, values):
            cell.text = str(value)
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                para.paragraph_format.space_after = Pt(2)
                for run in para.runs:
                    run.font.name = "Arial"
                    run.font.size = Pt(font_size)
    return table


def _doc_figure(doc: Document, root: Path, relative: str, caption: str, width_cm: float = 16.0):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.add_run().add_picture(str(root / relative), width=Cm(width_cm))
    _p(doc, caption, size=8)


def _page(doc: Document, title: str):
    doc.add_page_break()
    doc.add_heading(title, level=1)


def _build_docx(root: Path, out: Path, e: dict):
    cfg = read_json(root / "configs/final_deliverables.json")
    doc = Document()
    _doc_defaults(doc)
    doc.core_properties.title = cfg["title"]
    doc.core_properties.author = "Nhóm [CẦN BỔ SUNG]"
    doc.core_properties.subject = "T15 — bản nháp từ nguồn minh chứng đã lưu"
    _p(doc, "BÁO CÁO CUỐI KỲ — BẢN NHÁP", bold=True, size=18)
    doc.add_heading(cfg["title"], 0)
    _p(doc, f"Học phần: Máy học  |  Nhóm: {cfg['group_number']}", bold=True)
    _p(doc, f"Trường/khoa, lớp, giảng viên: {PLACEHOLDER} / {PLACEHOLDER} / {PLACEHOLDER}")
    _p(doc, "BẢN NHÁP — CHƯA SẴN SÀNG NỘP", bold=True, size=15)
    _p(doc, "Các trường cá nhân, rubric và kích thước poster chưa được nhóm/giảng viên xác nhận. Không suy thông tin cá nhân hay tỷ lệ đóng góp từ Git.")
    _p(doc, f"Snapshot mã nguồn: {e['source_commit']}")
    _doc_figure(doc, root, FIGURES["t13_actual_predicted"], "H03 — Actual/predicted, Test T13; hình gốc đã lưu, không chấm lại.", 15.5)

    _page(doc, "Thông tin thành viên và tóm tắt")
    members = cfg["members"]
    _table(
        doc,
        ["Họ tên", "MSSV", "Vai trò", "Phần việc thật", "Đóng góp %", "Minh chứng"],
        [[m["name"], m["student_id"], m["role"], m["actual_work"], m["contribution_percent"], m["evidence"]] for m in members],
        "Bảng T01 — Bảng mẫu; cần nhóm xác nhận từng thành viên và tổng tỷ lệ 100%.",
        7,
    )
    _p(doc, f"Git có {e['git_commit_count']} commit trong lịch sử reachable từ snapshot, theo authors: {json.dumps(e['git_author_commit_counts'], ensure_ascii=False)}. Đây chỉ là thống kê metadata Git, không phải tỷ lệ đóng góp học thuật và không được dùng để suy ra phần trăm.")
    _p(doc, "Tóm tắt — Nghiên cứu xây dựng bài toán hồi quy dự báo PM2.5 đúng một giờ tiếp theo tại cùng trạm, từ quan sát đến thời điểm t. Trên Test primary gồm 101.836 mẫu, Random Forest A đạt MAE 9,8772 µg/m³, giảm 2,8013% so Persistence; Ridge A kém Persistence theo MAE (-2,1909%). RF A vẫn là mô hình được chọn bằng validation trước khi mở Test. Các kết quả T17b là bổ sung trên validation, không thay quyết định đã khóa.")
    _p(doc, "Abstract — This project forecasts next-hour PM2.5 at the same Beijing monitoring station using information available no later than origin time t. On the 101,836-sample primary test cohort, locked Random Forest A achieved MAE 9.8772 µg/m³ (2.8013% below persistence), whereas Ridge A was 2.1909% worse by MAE. Model selection remained based on development validation, not test results. Supplementary T17b validation results are reported separately and do not replace the locked T13 model.")
    doc.add_heading("Mục lục", level=2)
    for item in (
        "Chương 1 — Giới thiệu",
        "Chương 2 — Cơ sở lý thuyết và nghiên cứu liên quan",
        "Chương 3 — Dữ liệu và phương pháp",
        "Chương 4 — Thực nghiệm, kết quả và thảo luận",
        "Chương 5 — Kết luận và hướng phát triển",
        "Phụ lục — Bản đồ mã nguồn, chỉ mục, thay đổi và tái lập",
    ):
        _p(doc, item)

    _page(doc, "Chương 1 — Giới thiệu")
    doc.add_heading("1.1 Bối cảnh và động cơ", level=2)
    _p(doc, "PM2.5 là hạt bụi mịn được quan trắc theo thời gian tại nhiều trạm. Dự án sử dụng tập Beijing Multi-Site Air-Quality Data của UCI, bao quát 12 trạm và chuỗi giờ 2013–2017 [1]. Dự báo một giờ giúp mô tả năng lực khai thác trạng thái hiện tại và lịch sử gần, nhưng không đồng nghĩa hệ thống cảnh báo sức khỏe hay khẳng định quan hệ nhân quả.")
    doc.add_heading("1.2 Mục tiêu và câu hỏi nghiên cứu", level=2)
    _p(doc, "Mục tiêu là xây dựng và đánh giá pipeline tái lập cho hồi quy PM2.5(s,t+1) từ quan sát cùng trạm s có thời điểm không muộn hơn t; đơn vị đầu ra µg/m³. Nhãn t+1 được nối chính xác theo station và timestamp, không thay bằng dòng kế tiếp khi thiếu giờ.")
    _table(doc, ["RQ", "Câu hỏi", "Minh chứng"], [
        ["RQ1", "Mô hình học máy có giảm MAE so với Persistence không?", "T13 Test cùng 101.836 primary IDs; RF +2,8013%, Ridge -2,1909%."],
        ["RQ2", "Feature A/B/C và các họ mô hình ảnh hưởng ra sao?", "T09–T12 và T17b validation; không dùng Test để chọn thêm."],
        ["RQ3", "Sai số tập trung ở trạm, mùa, nồng độ hay biến động nào?", "T13 grouped metrics và episodes; mô tả, không diễn giải nhân quả."],
    ], "Bảng T02 — Câu hỏi nghiên cứu.")
    doc.add_heading("1.3 Phạm vi và đóng góp", level=2)
    _p(doc, "Phạm vi là dữ liệu 12 trạm đã quan sát, dự báo cuốn chiếu đúng một giờ. Primary cohort yêu cầu PM2.5(t) hiện hữu. Operational cohort giữ các origin thiếu PM2.5(t) cho audit/ứng dụng nhưng không gộp vào kết luận primary. Dự án báo MAE chính, RMSE/R² bổ sung và phần trăm MAE giảm Persistence trên cùng cohort.")
    _p(doc, "Các giới hạn chính: thời gian train chỉ khoảng hai năm; T17b so sánh nhiều ứng viên trên một validation split; đánh giá test đã mở ở T13 nhưng chỉ sau khi khóa lựa chọn; chưa có video demo thật, rubric gốc và dữ liệu nhóm đã xác nhận.")

    _page(doc, "Chương 2 — Cơ sở lý thuyết và nghiên cứu liên quan")
    doc.add_heading("2.1 CRISP-DM cho bài toán chuỗi thời gian", level=2)
    _p(doc, "CRISP-DM tổ chức quy trình hiểu bài toán/dữ liệu, chuẩn bị, mô hình hóa, đánh giá và triển khai; dự án lưu cả vòng lặp giả thuyết → thiết kế → chạy → nhận xét → quyết định. Dữ liệu không được random-split: thời gian phải đi từ quá khứ đến tương lai [8].")
    doc.add_heading("2.2 Baseline và hồi quy điều chuẩn", level=2)
    _p(doc, "Persistence dự báo PM2.5(s,t+1)=PM2.5(s,t), là mốc mạnh cho horizon một giờ. Khi thiếu, quy tắc causal đã định trước dùng lịch sử gần cùng trạm rồi thống kê train; so sánh primary T13 không cần fallback. Ridge phạt L2 [2], Lasso phạt L1 và có thể tạo hệ số bằng 0 [3], Elastic Net kết hợp hai dạng phạt [4]. T17b Lasso/ElasticNet B là ứng viên phát triển, không phải phương án test.")
    doc.add_heading("2.3 Cây, boosting và gộp mô hình", level=2)
    _p(doc, "Random Forest là ensemble cây bootstrap [5]. HistGradientBoosting bổ sung boosting với loss bình phương hoặc tuyệt đối [6]. Fusion-3 trung bình ba dự báo được chọn theo pooled train-CV; OOF Ridge Stacking fit meta-model chỉ trên dự báo OOF train [7]. Nhóm nghiên cứu `GroupRidgeSelector` chọn cả nhóm biến gốc/OHE/missing indicator ở trong fold-train; nhóm được giữ không đồng nghĩa tác động nhân quả.")
    doc.add_heading("2.4 Temporal CV, purge và metric", level=2)
    _p(doc, "Dùng expanding-window 3 fold trên Train, cùng ranh giới timestamp qua trạm và purge=12 mẫu theo protocol; mọi tiền xử lý/selector fit lại trong fold-train. MAE=mean(|y−ŷ|), RMSE=sqrt(mean((y−ŷ)²)), R² là hệ số xác định; % giảm MAE = 100×(MAE_persistence−MAE_model)/MAE_persistence trên cùng IDs/cohort. Fold 1 chỉ đánh giá 2014-06 đến 2014-08; đây là thiếu phủ mùa của cửa sổ đánh giá, không khẳng định phần fit chưa từng thấy mùa khác.")
    doc.add_heading("2.5 Liên hệ bài giảng và khác biệt cho time series", level=2)
    _p(doc, "Mapping theo tên chủ đề do nhóm cung cấp: Chủ đề 02/03 về quy trình và dữ liệu; Chủ đề 04 về chọn đặc trưng; Chủ đề 05 về đánh giá; Chủ đề 06 về Ridge; Ensemble về RF/boosting/gộp. Tên tệp và trang/slide giảng viên cùng rubric chính thức: [CẦN BỔ SUNG]. Không áp dụng random split, fit tiền xử lý toàn cục hoặc xóa outlier bằng IQR vì sẽ phá thứ tự thông tin hoặc xóa đỉnh hợp lệ.")

    _page(doc, "Chương 3 — Dữ liệu và phương pháp")
    doc.add_heading("3.1 Nguồn và kiểm định chất lượng", level=2)
    _p(doc, "UCI #501: 12 trạm × 35.064 giờ = 420.768 dòng, 18 cột [1]. T03–T04 kiểm schema, khóa và thời gian; báo cáo chất lượng ghi 0 lỗi, 951 cảnh báo rà soát và không impute/xóa ngoại lệ. Dữ liệu thiếu giữ nguyên đến pipeline.")
    _table(doc, ["Cohort/split", "Train", "Validation", "Test", "Tổng"], [
        ["Operational", "205.977", "103.287", "102.753", "412.017"],
        ["Primary", "204.865", "102.479", "101.836", "409.180"],
    ], "Bảng T03 — Nhãn t+1 ghép theo station/timestamp; thiếu 8.751 mẫu nhãn.")
    _p(doc, "Primary tổng 409.180 mẫu; refit T13 dùng 307.344 mẫu Train+Validation; Test giữ 101.836 mẫu. Ranh giới theo target timestamp: Train trước 2015-03-01, Validation [2015-03-01, 2016-03-01), Test từ 2016-03-01.")
    doc.add_heading("3.2 EDA chỉ trên Train", level=2)
    _p(doc, "EDA T06 chỉ dùng Train có target, 205.977 operational origins (204.865 primary). PM2.5(t) missing 1.112; CO missing 6,74%; PM2.5 median 61, mean 83,88, q99=350, max=844 µg/m³. Cờ IQR là rà soát chứ không phải xác nhận lỗi. Các tương quan chỉ mô tả.")
    _doc_figure(doc, root, FIGURES["eda_missing"], "H01 — Missing theo biến trên Train; nguồn reports/eda_train.", 15.5)
    _doc_figure(doc, root, FIGURES["eda_calendar"], "H02 — Thống kê lịch/mùa trên Train; không EDA Test.", 15.5)
    doc.add_heading("3.3 Đặc trưng và pipeline", level=2)
    _table(doc, ["Bộ", "Thành phần", "Kích thước"], [
        ["A", "Số đo tại t, station/wd, lịch t+1 và sin/cos", "20 cột → 65 chiều"],
        ["B", "A + lag/rolling PM2.5 causal cùng trạm", "33 cột → 91 chiều"],
        ["C", "12 nhóm chọn từ B bằng GroupRidgeSelector", "24 chiều encoded"],
    ], "Bảng T04 — Đặc trưng A/B/C.")
    _p(doc, "T08 pipeline dùng FeatureSchema, median imputer và MissingIndicator cho numeric, one-hot cho categorical. Ridge scale numeric sau imputation; RF không scale. Từng fold chỉ fit trên fold-train; T13 refit train+validation sau khóa. Prediction policy identity, không clipping.")
    doc.add_heading("3.4 Khóa đánh giá", level=2)
    _p(doc, "T13 đánh giá theo config frozen, cùng cohort và IDs, không chọn lại model theo Test. RF A được chọn bằng Validation MAE ở T12; Ridge A alpha=0,1 là comparator đã chọn qua CV T11. T17b chỉ đọc/đánh giá development train-CV/validation, không truy cập test.")

    _page(doc, "Chương 4 — Thực nghiệm, kết quả và thảo luận")
    doc.add_heading("4.1 Hành trình T09–T12", level=2)
    _table(doc, ["Giai đoạn", "Kết quả phát triển", "Quyết định"], [
        ["T09", "Persistence Validation MAE 9,7366", "Giữ baseline."],
        ["T10", "Ridge A 10,2004; RF A 9,5615", "RF thắng MAE; Ridge có RMSE thấp hơn."],
        ["T11", "Alpha 0,1; pooled CV MAE 10,4055; Val 10,2005", "Không cải thiện Val so T10."],
        ["T12", "Ridge A 10,2005 → B 9,9688 → C 9,9034", "Ablation Ridge; RF A vẫn tốt nhất MAE và được khóa."],
    ], "Bảng T05 — Các vòng phát triển.")
    doc.add_heading("4.2 T13 — kết quả Test sau khóa", level=2)
    _table(doc, ["Model / run_id", "MAE", "RMSE", "R²", "Δ MAE so Persistence"], [
        [f"Persistence / {T13_RUNS['persistence']}", "10,1618", "19,4362", "0,9450", "0,0000%"],
        [f"Ridge A α=0,1 / {T13_RUNS['ridge']}", "10,3844", "18,9395", "0,9478", "-2,1909%"],
        [f"RF A đã khóa / {T13_RUNS['random_forest']}", "9,8772", "18,5696", "0,9498", "+2,8013%"],
    ], "Bảng T06 — T13 primary Test, N=101.836; refit Train+Validation N=307.344; đơn vị MAE/RMSE µg/m³.")
    _doc_figure(doc, root, FIGURES["t13_actual_predicted"], "H03 — Actual và dự báo trên Test T13; các điểm cực trị được giữ.", 15.0)
    _p(doc, "RF A được chọn bởi Validation trước khi Test được mở; T13 chỉ đánh giá, không tái lựa chọn. Ridge tối ưu bình phương có RMSE tốt hơn Persistence nhưng MAE kém hơn, nên không đổi tiêu chí chính sau khi nhìn Test.")
    doc.add_heading("4.3 Generalization gap và fold stability", level=2)
    _table(doc, ["Model", "Train lịch sử MAE", "Validation lịch sử MAE", "Refit Train+Val in-sample MAE", "Test MAE"], [
        ["Persistence", "không ghi", "9,7366", "10,6661", "10,1618"],
        ["Ridge", "11,2863", "10,2005", "10,7771", "10,3844"],
        ["RF", "9,8373", "9,5615", "9,5491", "9,8772"],
    ], "Bảng T07 — Các giai đoạn fit khác nhau; validation sau refit không phải holdout.")
    _p(doc, "Ridge pooled CV MAE 10,4055; fold mean±std 10,4255±1,2680. Persistence pooled 10,1596; 10,1809±1,3576. Fold std ddof=0 chỉ mô tả. RF CV không được chạy trong budget T11 nên không bịa fold/std. Train khoảng hai năm; Fold 1 chỉ đánh giá mùa hè, không đại diện các mùa khác.")
    doc.add_heading("4.4 RQ3 — sai số theo nhóm và đợt ô nhiễm", level=2)
    _table(doc, ["Nhóm Test RF", "N", "MAE", "RMSE", "Sai lệch dự báo trung bình"], [
        ["Dingling", "8.397", "8,5951", "17,2161", "+0,0469"],
        ["Wanshouxigong", "8.469", "10,9729", "21,3609", "-0,3080"],
        ["Mùa JJA", "25.714", "7,6437", "11,9861", "+0,2556"],
        ["Mùa DJF", "25.374", "13,2832", "26,4712", "-0,1816"],
        ["Nồng độ [150,+∞)", "14.784", "20,5795", "33,3101", "-7,5497"],
        ["Biến đổi nhanh |Δy|≥38", "4.377", "61,9229", "73,6433", "+6,1539"],
    ], "Bảng T08 — Nhóm mô tả, µg/m³; signed error = prediction − actual.")
    _doc_figure(doc, root, FIGURES["t13_group_errors"], "H04 — Sai số nhóm trên Test T13; xem bảng nhóm và nguồn để có N/coverage.", 15.0)
    _doc_figure(doc, root, FIGURES["t13_high_pollution"], "H05 — Đợt cao Tết Đinh Dậu; Nongzhanguan__20170127T21, peak quan sát 835 µg/m³.", 15.0)
    _p(doc, "RF thắng Persistence về MAE ở 12/12 trạm trong artifact T13. Sai số cao ở mùa đông, nồng độ cao và các giờ đổi nhanh là mô tả, không xác định nguyên nhân vật lý. Tại nhóm ≥150, RF có bias -7,5497 µg/m³, tức dự báo thấp trung bình. Ngưỡng nhóm không phải chuẩn sức khỏe.")
    _p(doc, "Sai khác được kiểm toán: yêu cầu đầu vào nêu Dingling 8,6287 và JJA 6,6666, nhưng grouped_metrics.csv lưu RF lần lượt 8,5951 và 7,6437. Báo cáo dùng giá trị artifact và lưu xung đột trong verification.json; cần người phụ trách đối chiếu nếu có nguồn mới.")
    doc.add_heading("4.5 Diễn giải và thí nghiệm bổ sung", level=2)
    _table(doc, ["Nhóm đặc trưng RF", "Permutation MAE tăng (µg/m³)"], [
        ["PM2.5", "52,9972"], ["PM10", "6,7182"], ["WSPM", "1,4520"], ["CO", "0,5619"], ["DEWP", "0,5168"],
    ], "Bảng T09 — Grouped permutation; chẩn đoán, không phải nhân quả.")
    _doc_figure(doc, root, FIGURES["t13_permutation"], "H06 — Permutation importance theo nhóm nguồn.", 15.0)
    _p(doc, "Ridge coefficient trên feature space cũng bị ảnh hưởng bởi chuẩn hóa, one-hot và tương quan. Cả hệ số và permutation importance chỉ biểu thị quan hệ dự báo theo cách đo đã dùng, không chứng minh nhân quả.")
    t17_rows = []
    labels = {
        "rolling_mean_3h": "Baseline rolling mean 3h",
        "same_target_hour_yesterday": "Cùng giờ hôm qua",
        "decision_tree_B": "Decision Tree B",
        "lasso_B": "Lasso B",
        "hist_gradient_boosting_B": "HistGB B",
        "random_forest_B": "RF B",
        "random_forest_B_tuned": "RF B tuned",
        "fusion_3": "Fusion-3",
        "oof_ridge_stack": "OOF Ridge Stack",
    }
    for name, row in e["t17b"].items():
        t17_rows.append([labels[name], f"{row['validation_MAE']:.4f}", f"{row['validation_RMSE']:.4f}", f"{row['mae_reduction_pct']:+.2f}%", row["run_id"]])
    _table(doc, ["Ứng viên T17b", "Val MAE", "Val RMSE", "Δ MAE vs Persistence", "validation run_id"], t17_rows, "Bảng T10 — T17b trên Validation N=102.479, không phải Test.", 7)
    _doc_figure(doc, root, FIGURES["t17b_validation"], "H09 — So sánh validation T17b theo artifact T17a.", 15.0)
    _p(doc, f"T17b validation (parent_run_id={e['t17b_parent_run_id']}) gồm đủ 9 ứng viên; Lasso B giữ 23/33 nhóm, còn Bộ C chọn 12 nhóm bằng GroupRidgeSelector. Stack (9,2321; +5,18%) và Fusion-3 (9,2746; +4,75%) là hai kết quả nổi bật; RF B 9,3798. Chúng không thay RF A: T17b là nhiều ứng viên trên một split, không phải lựa chọn độc lập và không có Test. T17a summary gồm 27 dòng, run/CV IDs được truy vết.")
    doc.add_heading("4.6 Demo và lỗi tương thích", level=2)
    _doc_figure(doc, root, FIGURES["demo_screenshot"], "H10 — Ảnh browser thật của Demo T14, không phải video.", 12.0)
    _p(doc, "Demo Streamlit dùng dữ liệu ≤t và pipeline RF A đã fit, dự báo t+1 rồi mới truy vấn actual. T14 QA lưu 19 test pass, 36 dự báo khớp artifact T13 và 5 ảnh browser. Video thật chưa được quay.")
    _p(doc, "Issue #35/PR #37 sửa TypeError của pandas 3.0.6 trong guard kiểu categorical ở single-row inference. Đây là lỗi tương thích phần mềm, không phải sai số hay chất lượng dự báo học máy. Commit sửa `a819acf`, tài liệu/bằng chứng `2369ca5`; source SHA `preprocessing.py` chuyển từ `3e121c…` sang `a5279d…`. Không refit T13, không đổi weights hoặc metrics.")

    _page(doc, "Chương 5 — Kết luận và hướng phát triển")
    doc.add_heading("5.1 Trả lời RQ", level=2)
    _p(doc, "RQ1: RF A giảm MAE 2,8013% so Persistence trên primary Test; Ridge A giảm âm 2,1909%, nên không phải mọi mô hình học máy đều tốt hơn baseline. RQ2: T12 cho thấy B/C giảm MAE của Ridge trên validation; T17b cho thấy một số ứng viên/gộp thấp hơn RF A trên validation, nhưng không thay khóa T13. RQ3: sai số tập trung hơn ở Wanshouxigong, DJF, nồng độ cao và biến đổi nhanh; các kết luận là mô tả trên cohort đã chấm.")
    doc.add_heading("5.2 Giới hạn và hướng phát triển", level=2)
    _p(doc, "Giới hạn gồm thời gian Train ngắn/ít chu kỳ mùa, một holdout validation được dùng cho nhiều quyết định, không có RF CV độc lập trong T11, chỉ primary đã quan sát t, các nhóm nhỏ có độ bất định, không có kiểm định ý nghĩa thống kê, và đỉnh ô nhiễm bị dự báo thấp. Importance không giải thích cơ chế nhân quả.")
    _p(doc, "Naive Bayes là classifier xác suất, K-Means là clustering; không khớp mục tiêu hồi quy liên tục nếu không đổi bài toán. KNN/Kernel SVR và Deep Learning có thể mở rộng sau khi kiểm ngân sách, temporal CV, khả năng mở rộng và baseline mạnh; chưa chạy trong phạm vi chính và không được tuyên bố là đã thử.")
    _p(doc, "Hướng tiếp theo: tăng độ phủ năm/mùa và trạm ngoài mẫu; kiểm định validation bằng thiết kế đã khóa; đánh giá operational missingness riêng; kiểm tra calibration/độ bất định và giám sát drift; cung cấp video thật, rubric gốc, thành viên và yêu cầu poster; rà nguồn model/version trước bàn giao.")
    _p(doc, "Trạng thái hồ sơ: bản nháp. Thiếu tên/MSSV/vai trò/đóng góp 100%, rubric, thông tin lớp/giảng viên và xác nhận poster; không tự tuyên bố đáp ứng toàn bộ rubric.")

    _page(doc, "Phụ lục — Chỉ mục, nhật ký thay đổi và tái lập")
    doc.add_heading("A. Bản đồ vị trí mã nguồn", level=2)
    _table(doc, ["Giai đoạn", "Mã/chứng cứ chính"], [
        ["T01–T04", "scripts/check_imports.py; src/beijing_air/data.py; reports/raw_audit_full.json; reports/quality_full/"],
        ["T05–T08", "samples.py; features.py; preprocessing.py; feature_selection.py; reports/splits_full/"],
        ["T09–T12", "baseline.py; initial_models.py; temporal_cv.py; tuning.py; ablation.py; artifacts/experiments/"],
        ["T13", "final_evaluation.py; reports/final_evaluation/; comparison.csv; docs/results_discussion.md"],
        ["T14", "demo.py; demo_ui.py; app/streamlit_app.py; reports/demo/"],
        ["T17a/T17b", "experiment_summary.py; supplementary_experiments.py; reports/tables/; docs/supplementary_experiments.md"],
        ["T15", "final_deliverables.py; scripts/build_final_deliverables.py; scripts/verify_final_deliverables.py"],
    ], "Chỉ mục mã nguồn T01–T17b; chi tiết AST và dòng nằm trong docs/notebook_code_map.md.")
    doc.add_heading("B. Chỉ mục bảng/hình", level=2)
    _table(doc, ["ID", "Nội dung", "Nguồn"], [[i, title, "; ".join(paths)] for i, title, paths in TABLES], "Bảng T11 — Chỉ mục bảng.")
    _table(doc, ["ID", "Nội dung", "Nguồn"], [[i, title, path] for i, title, path in FIGURE_INDEX], "Bảng T12 — Chỉ mục hình.")
    doc.add_heading("C. Nhật ký thay đổi và lỗi", level=2)
    _p(doc, "Issue #35 / PR #37: bug categorical empty-value guard trong pandas 3.0.6 được sửa ở commit a819acf và tài liệu QA ở 2369ca5. Source SHA preprocessing.py trước/sau được nêu ở Chương 4. Tương thích inference được kiểm trên fixture TEST_ONLY; không đổi T13 fit, weights, run ID, hoặc metric.")
    _p(doc, "Lần T17b full đầu trong yêu cầu tác vụ được nhắc với run ID 3cc5790dd34d4ca29435f4da86b68ae7 và ArrayMemoryError. ID này hiện không được tìm thấy trong ledger 264 dòng hoặc cây artifact đã có; docs/supplementary_experiments.md ghi lần full đầu thất bại ở bước Stack metadata rồi được sửa. Không ghi nhận ID/lỗi này là đã xác minh; cần đối chiếu hồ sơ gốc.")
    doc.add_heading("D. AI disclosure và tái lập", level=2)
    _p(doc, "AI hỗ trợ đọc tài liệu, viết module/script/test và tạo tài liệu/hình từ artifact có sẵn. Không huấn luyện, tune/refit, sinh run, mở test raw hoặc thêm dòng experiment log. Người nhận T15 là GitHub `duyhuynh4869-byte` theo xác nhận của người dùng; thành viên cần đọc/hiểu/review trước khi merge [CẦN BỔ SUNG].")
    _p(doc, "Tái lập: từ root đồ án chạy `.\u005c.venv\u005cScripts\u005cpython.exe scripts/build_final_deliverables.py`, sau đó `.\u005c.venv\u005cScripts\u005cpython.exe scripts/verify_final_deliverables.py` và pytest được ghi trong docs/final_deliverables.md. Generator chỉ đọc các bảng, JSON, docs và hình đã có; không gọi model runners. Khôi phục dataset/model bundle là quy trình riêng trong README/demo.md.")
    _p(doc, "Bài giảng Chủ đề 02–06/Ensemble, slide/trang cụ thể và rubric: [CẦN BỔ SUNG].")
    doc.add_heading("E. Tài liệu tham khảo", level=2)
    reference_source = (root / "docs/references.md").read_text(encoding="utf-8")
    reference_section = reference_source.split("## Bài giảng môn học", 1)[0]
    reference_items = []
    current_reference = ""
    for line in reference_section.splitlines():
        stripped = line.strip()
        if re.match(r"^\d+\.\s", stripped):
            if current_reference:
                reference_items.append(current_reference)
            current_reference = re.sub(r"^\d+\.\s", "", stripped)
        elif current_reference and stripped:
            current_reference += " " + stripped
    if current_reference:
        reference_items.append(current_reference)
    for reference in reference_items:
        reference = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", reference).replace("*", "")
        _p(doc, reference, size=9)
    _p(doc, "Bài giảng môn học: Chủ đề 02–06 và Ensemble; tên file, phiên bản và slide/trang [CẦN BỔ SUNG].", size=9)
    path = out / "NhomXX_DuBaoPM25_BacKinh_CuoiKy.docx"
    doc.save(path)
    return path


def _hex(color: str) -> PptColor:
    return PptColor.from_string(color)


def _slide_base(prs: Presentation, title: str, number: int, source: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _hex("FAFCFD")
    stripe = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, PptInches(0.11))
    stripe.fill.solid()
    stripe.fill.fore_color.rgb = _hex(TEAL)
    stripe.line.fill.background()
    textbox(slide, title, 0.45, 0.28, 10.8, 0.7, 27, NAVY, True)
    textbox(slide, "BẢN NHÁP · NhomXX", 11.5, 0.32, 1.45, 0.3, 10, GOLD, True)
    textbox(slide, source, 0.45, 7.12, 11.5, 0.22, 8, GRAY)
    textbox(slide, f"{number:02d}/18", 12.18, 7.1, 0.7, 0.25, 9, GRAY)
    return slide


def textbox(slide, text: str, x: float, y: float, w: float, h: float, size: int = 18, color: str = INK, bold: bool = False):
    shape = slide.shapes.add_textbox(PptInches(x), PptInches(y), PptInches(w), PptInches(h))
    frame = shape.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = PptInches(0.04)
    frame.margin_top = frame.margin_bottom = PptInches(0.02)
    for idx, line in enumerate(text.split("\n")):
        para = frame.paragraphs[0] if idx == 0 else frame.add_paragraph()
        para.text = line
        para.font.name = "Arial"
        para.font.size = PptPt(size)
        para.font.bold = bold
        para.font.color.rgb = _hex(color)
        para.space_after = PptPt(5)
    return shape


def _table_slide(slide, headers, rows, x=0.55, y=1.5, w=12.2, h=4.4, font=15):
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), PptInches(x), PptInches(y), PptInches(w), PptInches(h))
    table = shape.table
    for i, row in enumerate([headers] + rows):
        for j, value in enumerate(row):
            cell = table.cell(i, j)
            cell.text = str(value)
            cell.fill.solid()
            cell.fill.fore_color.rgb = _hex(NAVY if i == 0 else ("EEF6F7" if i % 2 else "FFFFFF"))
            cell.margin_left = cell.margin_right = PptInches(0.06)
            cell.margin_top = cell.margin_bottom = PptInches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            for para in cell.text_frame.paragraphs:
                para.font.name = "Arial"
                para.font.size = PptPt(font)
                para.font.bold = i == 0
                para.font.color.rgb = _hex("FFFFFF" if i == 0 else NAVY)
    return shape


def _slide_image(slide, root: Path, relative: str, x: float, y: float, w: float, h: float):
    with Image.open(root / relative) as image:
        ratio = image.width / image.height
    if w / h > ratio:
        w = h * ratio
    else:
        h = w / ratio
    return slide.shapes.add_picture(str(root / relative), PptInches(x), PptInches(y), width=PptInches(w), height=PptInches(h))


def _speaker_notes(slide, text: str):
    slide.notes_slide.notes_text_frame.text = text


def _build_slides(root: Path, out: Path, e: dict):
    prs = Presentation()
    prs.slide_width, prs.slide_height = PptInches(13.333), PptInches(7.5)
    prs.core_properties.title = "Báo cáo cuối kỳ PM2.5 Bắc Kinh — T15"
    prs.core_properties.author = "Nhóm [CẦN BỔ SUNG]"
    models = e["models"]
    s = _slide_base(prs, "DỰ BÁO PM2.5 TRƯỚC 1 GIỜ", 1, "T15 · Bản nháp · UCI 501")
    textbox(s, "Tại 12 trạm quan trắc ở Bắc Kinh", 0.75, 1.55, 11.6, 0.65, 26, TEAL, True)
    textbox(s, "RF A đã khóa: Test MAE 9,8772 µg/m³\n−2,80% MAE so với Persistence", 0.75, 2.45, 11.7, 1.25, 34, NAVY, True)
    textbox(s, "Nhóm / thành viên / MSSV / giảng viên: [CẦN BỔ SUNG]\nTest chỉ mở sau khóa; T17b là validation bổ sung.", 0.75, 4.45, 11.8, 1.0, 22)
    _speaker_notes(s, f"Source snapshot: {e['source_commit']}. Test T13 đã mở; lựa chọn RF A được chốt theo validation.")

    s = _slide_base(prs, "MỤC TIÊU VÀ CÂU HỎI NGHIÊN CỨU", 2, "Nguồn: docs/problem_definition.md; results_discussion.md")
    _table_slide(s, ["RQ", "Câu hỏi", "Kết luận ngắn"], [
        ["RQ1", "ML có hơn Persistence?", "RF A +2,80%; Ridge −2,19% MAE trên Test."],
        ["RQ2", "Feature/model bổ sung giúp gì?", "A/B/C và T17b chỉ phát triển; không đổi lock."],
        ["RQ3", "Sai số tập trung ở đâu?", "Winter, mức cao và biến đổi nhanh khó hơn."],
    ], y=1.65, h=3.6, font=17)
    textbox(s, "Mục tiêu: hồi quy PM2.5(s,t+1) từ thông tin cùng trạm ≤ t.", 0.7, 5.65, 11.9, 0.55, 20, TEAL, True)

    s = _slide_base(prs, "UCI 501 · DỮ LIỆU THEO GIỜ, NHIỀU TRẠM", 3, "Nguồn: configs/uci_501.json; reports/raw_audit_full.json")
    textbox(s, "12 trạm × 35.064 giờ = 420.768 dòng · 18 cột", 0.65, 1.35, 12, 0.6, 25, NAVY, True)
    _slide_image(s, root, FIGURES["eda_missing"], 0.55, 2.15, 6.5, 4.35)
    textbox(s, "PM2.5(t) missing 1.112\nCO missing 6,74%\nTrain-only EDA\nKhông impute sớm\nKhông xóa đỉnh bằng IQR", 7.4, 2.3, 5.1, 3.8, 22)

    s = _slide_base(prs, "BÀI TOÁN · OUTPUT ĐÚNG 1 GIỜ SAU", 4, "Nguồn: docs/problem_definition.md; UCI 501")
    textbox(s, "Input: quan sát tại trạm s đến thời điểm t\nOutput: PM2.5(s,t+1), µg/m³\nNhãn nối chính xác theo (station, timestamp + 1h)", 0.75, 1.65, 11.8, 2.4, 26)
    textbox(s, "Giờ khuyết không lấy dòng kế tiếp · Không impute target · Forecast rolling, không batch tương lai.", 0.75, 4.65, 11.9, 1.0, 21, TEAL, True)

    s = _slide_base(prs, "CRISP-DM · TỪ CÂU HỎI ĐẾN QUYẾT ĐỊNH", 5, "Nguồn: docs/project_journey.md; [CẦN BỔ SUNG] slide môn học")
    _table_slide(s, ["Pha", "Thực hiện"], [
        ["Business/Data", "T02–T06: bài toán, audit, EDA Train"],
        ["Preparation", "T05–T08: exact join, causal features, pipeline"],
        ["Modeling", "T09–T12, T17b: baseline, CV, A/B/C, bổ sung"],
        ["Evaluation", "T13: Test sau khi khóa; T17b Validation riêng"],
        ["Deployment", "T14: Streamlit local, video chưa quay"],
    ], y=1.65, h=4.4, font=18)

    s = _slide_base(prs, "A/B/C · FEATURE VÀ PIPELINE", 6, "Nguồn: T07/T08/T12; 20→65, 33→91, 12 nhóm→24")
    _table_slide(s, ["Bộ", "Định nghĩa", "Kích thước"], [
        ["A", "Đo tại t, station/wd, lịch t+1", "20 cột → 65"],
        ["B", "A + causal lag/rolling", "33 cột → 91"],
        ["C", "GroupRidgeSelector trong fold", "12 nhóm → 24"],
    ], y=1.65, h=3.45, font=17)
    textbox(s, "Median + MissingIndicator · OneHotEncoder · StandardScaler cho tuyến tính\nRF không scale · Fit tiền xử lý trong train/fold · Không clipping", 0.65, 5.45, 12, 1.05, 18)

    s = _slide_base(prs, "CHỐNG RÒ RỈ · TEMPORAL SPLIT/CV", 7, "Nguồn: split_manifest.json; configs/final_evaluation.json")
    _table_slide(s, ["Split", "Primary N", "Target timestamps"], [
        ["Train", "204.865", "< 2015-03-01"],
        ["Validation", "102.479", "[2015-03-01, 2016-03-01)"],
        ["Test", "101.836", "≥ 2016-03-01; chấm sau khóa"],
    ], y=1.55, h=2.8, font=19)
    textbox(s, "3 expanding folds · purge=12 · mọi bước học chỉ fit fold-train\nTest không được dùng để chọn model; T13 refit train+validation sau khóa.", 0.65, 4.8, 12, 1.35, 20, TEAL, True)

    s = _slide_base(prs, "T09–T10 · PERSISTENCE LÀ MỐC MẠNH", 8, "Nguồn: reports/initial_models/comparison.csv; baseline T09")
    _table_slide(s, ["Validation", "MAE", "RMSE"], [
        ["Persistence", "9,7366", "19,2409"],
        ["Ridge A", "10,2004", "18,9071"],
        ["RF A", "9,5615", "18,9648"],
    ], y=1.7, h=3.4, font=20)
    textbox(s, "T10: RF giảm khoảng 1,80% MAE so baseline; Ridge kém MAE nhưng RMSE tốt hơn.", 0.7, 5.55, 11.8, 0.75, 20)

    s = _slide_base(prs, "T11–T12 · TUNING VÀ ABLATION", 9, "Nguồn: tuning/candidates.csv; ablation/comparison.csv")
    _table_slide(s, ["Bước", "Validation MAE", "Nhận xét"], [
        ["Ridge A α=0,1 (T11)", "10,2005", "CV pooled 10,4055; val không cải thiện"],
        ["Ridge B (T12)", "9,9688", "Lag/rolling"],
        ["Ridge C (T12)", "9,9034", "12 nhóm; 24 chiều"],
        ["RF A đã khóa", "9,5615", "Tốt nhất MAE trong pool T12"],
    ], y=1.65, h=4.2, font=17)

    s = _slide_base(prs, "T13 · TEST CHỈ SAU KHI KHÓA", 10, "Primary N=101.836 · refit Train+Validation N=307.344")
    _table_slide(s, ["Model / run_id", "MAE", "RMSE", "R²", "Δ MAE"], [
        [T13_RUNS["persistence"], "10,1618", "19,4362", "0,9450", "0,00%"],
        [T13_RUNS["ridge"], "10,3844", "18,9395", "0,9478", "−2,19%"],
        [T13_RUNS["random_forest"], "9,8772", "18,5696", "0,9498", "+2,80%"],
    ], y=1.65, h=3.75, font=14)
    textbox(s, "RF A được chọn bằng Validation trước Test. Không chọn lại theo Test.", 0.7, 5.75, 11.9, 0.55, 20, TEAL, True)

    s = _slide_base(prs, "RQ1 · RF A GIẢM MAE 2,80%", 11, "Nguồn: reports/final_evaluation/comparison.csv")
    _slide_image(s, root, FIGURES["t13_actual_predicted"], 0.6, 1.45, 8.2, 4.8)
    textbox(s, "RF A\n9,8772 µg/m³\n+2,8013%", 9.15, 2.1, 3.1, 2.2, 25, TEAL, True)
    textbox(s, "Ridge −2,1909%\nTest đã mở sau khóa.", 9.15, 4.65, 3.2, 1.0, 18)

    s = _slide_base(prs, "GENERALIZATION GAP · FOLD CÓ GIỚI HẠN", 12, "Nguồn: generalization_gap.csv; development_fold_metrics.csv")
    _table_slide(s, ["Model", "Hist. Val MAE", "Refit Train+Val (in-sample)", "Test MAE"], [
        ["Persistence", "9,7366", "10,6661", "10,1618"],
        ["Ridge", "10,2005", "10,7771", "10,3844"],
        ["RF", "9,5615", "9,5491", "9,8772"],
    ], y=1.55, h=2.8, font=15)
    textbox(s, "Ridge CV pooled MAE 10,4055; fold mean ± std 10,4255 ± 1,2680.\nFold 1 đánh giá mùa hè 2014; 3 fold không đại diện mọi mùa/năm.\nRF CV chưa có trong T11.", 0.65, 4.8, 12, 1.25, 17)

    s = _slide_base(prs, "RQ3 · SAI SỐ THEO NHÓM", 13, "Nguồn: grouped_metrics.csv · signed error = prediction − actual")
    _slide_image(s, root, FIGURES["t13_group_errors"], 0.4, 1.35, 7.1, 5.0)
    _table_slide(s, ["Nhóm RF", "MAE", "N"], [
        ["Dingling", "8,5951", "8.397"],
        ["Wanshouxigong", "10,9729", "8.469"],
        ["JJA / DJF", "7,6437 / 13,2832", "25.714 / 25.374"],
        ["≥150 µg/m³", "20,5795", "14.784"],
        ["|Δy|≥38", "61,9229", "4.377"],
    ], x=7.65, y=1.6, w=5.1, h=4.9, font=12)

    s = _slide_base(prs, "ĐỢT Ô NHIỄM CAO · GIỮ ĐỈNH HỢP LỆ", 14, "Nongzhanguan__20170127T21 · peak 835 µg/m³")
    _slide_image(s, root, FIGURES["t13_high_pollution"], 0.55, 1.35, 8.2, 5.3)
    textbox(s, "Nồng độ ≥150\nRF bias −7,5497\nMAE 20,5795\nKhông phải ngưỡng sức khỏe", 9.0, 2.0, 3.4, 3.6, 20)

    s = _slide_base(prs, "DIỄN GIẢI · LIÊN HỆ KHÔNG PHẢI NHÂN QUẢ", 15, "Nguồn: rf_permutation_summary.csv; ridge_coefficients.csv")
    _slide_image(s, root, FIGURES["t13_permutation"], 0.55, 1.35, 8.0, 5.0)
    _table_slide(s, ["Nhóm", "Permutation ΔMAE"], [
        ["PM2.5", "52,9972"], ["PM10", "6,7182"], ["WSPM", "1,4520"],
        ["CO", "0,5619"], ["DEWP", "0,5168"],
    ], x=8.75, y=1.7, w=3.95, h=3.6, font=14)

    s = _slide_base(prs, "T17b · 9 NHÓM THÍ NGHIỆM BỔ SUNG", 16, "Tất cả Validation N=102.479 · không Test")
    _table_slide(s, ["Ứng viên", "Val MAE", "So Persistence"], [
        ["Rolling mean 3h", "14,0165", "−43,96%"],
        ["Cùng giờ hôm qua", "50,4168", "−417,81%"],
        ["Decision Tree B", "9,8648", "−1,32%"],
        ["Lasso B", "9,8143", "−0,80%"],
        ["HistGB B", "9,4868", "+2,57%"],
        ["RF B", "9,3798", "+3,67%"],
        ["RF B tuned", "9,5093", "+2,33%"],
        ["Fusion-3", "9,2746", "+4,75%"],
        ["OOF Ridge Stack", "9,2321", "+5,18%"],
    ], y=1.3, h=5.35, font=11)
    t17b_run_ids = "; ".join(f"{name}={row['run_id']}" for name, row in e["t17b"].items())
    _speaker_notes(
        s,
        f"parent_run_id={e['t17b_parent_run_id']}; validation candidates do not replace frozen RF A; "
        f"27-row summary T17a is the source. Candidate run IDs: {t17b_run_ids}",
    )

    s = _slide_base(prs, "T17b · KẾT QUẢ VALIDATION BỔ SUNG", 17, "Nguồn: t17b_validation_comparison.png; supplementary_experiments.md")
    _slide_image(s, root, FIGURES["t17b_validation"], 0.65, 1.35, 8.5, 4.85)
    textbox(s, "RF B 9,3798\nFusion-3 9,2746\nStack 9,2321\nỨng viên phát triển.\nRF A vẫn khóa.", 9.45, 2.0, 2.9, 3.2, 21, TEAL, True)

    s = _slide_base(prs, "DEMO T14 · DỰ BÁO NHÂN QUẢ", 18, "Streamlit local · video thật chưa có · Issue #35 là lỗi phần mềm")
    _slide_image(s, root, FIGURES["demo_screenshot"], 0.55, 1.3, 7.5, 5.3)
    textbox(s, "Chỉ dùng dữ liệu ≤t\nDự báo đúng t+1\nActual truy vấn sau predict\nIssue #35: guard pandas 3.0.6\nKhông refit T13/đổi weights\nThành viên, video, rubric: [CẦN BỔ SUNG]", 8.45, 1.75, 4.25, 4.7, 18)
    if len(prs.slides) != 18:
        raise ValueError("The final presentation must contain 18 slides")
    path = out / "NhomXX_DuBaoPM25_BacKinh_CuoiKy.pptx"
    prs.save(path)
    return path


def _poster_fonts():
    fonts = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
    regular, bold = fonts / "arial.ttf", fonts / "arialbd.ttf"
    if not regular.is_file() or not bold.is_file():
        raise FileNotFoundError("Arial fonts are required to render the Vietnamese poster")
    return str(regular), str(bold)


def _poster_png(root: Path, path: Path, e: dict, config: dict):
    width, height = 2400, 3200
    image = Image.new("RGB", (width, height), "#f4f8fa")
    draw = ImageDraw.Draw(image)
    regular_path, bold_path = _poster_fonts()
    title = ImageFont.truetype(bold_path, 82)
    heading = ImageFont.truetype(bold_path, 44)
    body = ImageFont.truetype(regular_path, 32)
    small = ImageFont.truetype(regular_path, 26)
    draw.rectangle((0, 0, width, 460), fill=f"#{NAVY}")
    draw.text((100, 70), "DỰ BÁO PM2.5 TRƯỚC 1 GIỜ", fill="white", font=title)
    draw.text((105, 195), "Tại 12 trạm quan trắc Bắc Kinh · UCI 501", fill="#CDECEF", font=heading)
    draw.text((105, 330), "BẢN NHÁP · Nhóm / thành viên / MSSV: [CẦN BỔ SUNG]", fill="#F6D991", font=small)
    gap, margin = 54, 75
    col_w = (width - 2 * margin - 2 * gap) // 3
    top_y, row_h, second_y = 520, 1160, 1730
    second_h = 1300

    def card(x, y, h, title_text, lines, image_rel=None, table_rows=None):
        draw.rounded_rectangle((x, y, x + col_w, y + h), radius=25, fill="white", outline="#CBD9DE", width=4)
        draw.rounded_rectangle((x, y, x + col_w, y + 100), radius=25, fill=f"#{TEAL}")
        draw.text((x + 25, y + 22), title_text, fill="white", font=heading)
        cursor = y + 130
        for line in lines:
            draw.text((x + 28, cursor), line, fill=f"#{INK}", font=body)
            cursor += 52
        if table_rows:
            cursor += 10
            for label, value in table_rows:
                draw.text((x + 30, cursor), label, fill=f"#{NAVY}", font=small)
                draw.text((x + 30, cursor + 34), value, fill=f"#{INK}", font=body)
                cursor += 95
        if image_rel:
            with Image.open(root / image_rel) as source:
                source = source.convert("RGB")
                source.thumbnail((col_w - 54, max(260, y + h - cursor - 35)))
                image.paste(source, (x + 27, max(cursor + 10, y + h - source.height - 35)))

    x1, x2, x3 = margin, margin + col_w + gap, margin + 2 * (col_w + gap)
    card(x1, top_y, row_h, "BÀI TOÁN & UCI 501",
         ["t → đúng t+1, cùng trạm", "18 cột · 420.768 dòng", "12 × 35.064 giờ", "Primary: 409.180 mẫu"],
         FIGURES["eda_missing"])
    card(x2, top_y, row_h, "PIPELINE CHỐNG RÒ RỈ",
         ["Join station + timestamp+1h", "A 20→65 · B 33→91", "C 12 nhóm→24 chiều", "Median + missing indicator", "Expanding CV · purge=12", "Fit tiền xử lý trong train/fold"])
    card(x3, top_y, row_h, "T13 · TEST SAU KHI KHÓA",
         ["N=101.836 · refit 307.344", "RF A đã chọn bằng Validation"],
         table_rows=[("Persistence", "MAE 10,1618"),
                     ("Ridge A", "10,3844 · −2,19%"),
                     ("RF A", "9,8772 · +2,80%")],
         image_rel=FIGURES["t13_actual_predicted"])
    card(x1, second_y, second_h, "T17b · VALIDATION",
         ["Ứng viên bổ sung, không dùng Test"],
         table_rows=[("RF B", "9,3798"),
                     ("Fusion-3", "9,2746"),
                     ("OOF Ridge Stack", "9,2321")],
         image_rel=FIGURES["t17b_validation"])
    card(x2, second_y, second_h, "RQ3 · LỖI & DEMO",
         ["JJA 7,6437 · DJF 13,2832", "≥150: MAE 20,5795", "|Δy|≥38: MAE 61,9229", "Đỉnh 835 µg/m³; giữ outlier"],
         FIGURES["t13_group_errors"])
    card(x3, second_y, second_h, "KẾT LUẬN & THÀNH VIÊN",
         ["RF A giảm MAE 2,80% trên Test", "Importance không là nhân quả", "Demo local; video chưa quay", "Tên/MSSV/%: [CẦN BỔ SUNG]", "Poster 36×48 in: [CẦN BỔ SUNG]"],
         FIGURES["demo_screenshot"])
    draw.rectangle((0, 3070, width, height), fill=f"#{NAVY}")
    draw.text((85, 3100), "Nguồn: UCI 501 · T13 artifacts · T17a/T17b Validation · docs/references.md", fill="white", font=small)
    draw.text((85, 3140), "Kết quả mô tả trên cohort đã đánh giá; chưa phải hướng dẫn/cảnh báo sức khỏe.", fill="#CDECEF", font=small)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", dpi=(100, 100), optimize=True)


def _poster_pptx(root: Path, out: Path, e: dict, config: dict):
    width = float(config["poster_size_inches"]["width"])
    height = float(config["poster_size_inches"]["height"])
    prs = Presentation()
    prs.slide_width, prs.slide_height = PptInches(width), PptInches(height)
    prs.core_properties.title = "Poster PM2.5 Bắc Kinh — bản nháp"
    prs.core_properties.author = "Nhóm [CẦN BỔ SUNG]"
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _hex("F4F8FA")
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, PptInches(6.6))
    band.fill.solid(); band.fill.fore_color.rgb = _hex(NAVY); band.line.fill.background()
    textbox(slide, "DỰ BÁO PM2.5 TRƯỚC 1 GIỜ", 1.2, 0.8, width - 2.4, 1.4, 52, "FFFFFF", True)
    textbox(slide, "Tại 12 trạm quan trắc Bắc Kinh · UCI 501", 1.25, 2.55, width - 2.5, 0.8, 30, "CDECEF", True)
    textbox(slide, "BẢN NHÁP · Thành viên/MSSV: [CẦN BỔ SUNG] · Kích thước 36×48 in: [CẦN BỔ SUNG]", 1.25, 4.3, width - 2.5, 0.7, 22, GOLD, True)
    columns = [1.0, 13.0, 25.0]
    column_width = 10.0
    row_y = [7.4, 28.0]
    card_w, card_h = 10.7, 19.4
    sections = [
        ("BÀI TOÁN & DỮ LIỆU", "t → t+1 cùng trạm\nUCI 501: 12×35.064 giờ\n420.768 dòng, 18 cột\nPrimary 409.180\nTarget join chính xác", FIGURES["eda_missing"]),
        ("PIPELINE CHỐNG RÒ RỈ", "A 20→65 · B 33→91\nC 12 nhóm→24\nMedian + MissingIndicator\nOneHotEncoder\nExpanding CV, purge=12\nFit trong fold-train", None),
        ("T13 · TEST SAU KHÓA", "N=101.836\nRefit 307.344\nPersistence 10,1618\nRidge A 10,3844 (−2,19%)\nRF A 9,8772 (+2,80%)\nModel chọn bằng Validation", FIGURES["t13_actual_predicted"]),
        ("T17b · VALIDATION", "RF B 9,3798\nFusion-3 9,2746\nStack 9,2321\nỨng viên bổ sung\nKhông chấm Test", FIGURES["t17b_validation"]),
        ("RQ3 · SAI SỐ & DEMO", "JJA 7,6437 · DJF 13,2832\nNhóm ≥150: MAE 20,5795\nBiến đổi nhanh: 61,9229\nĐỉnh 835 µg/m³\nDemo chỉ dùng input ≤t", FIGURES["t13_group_errors"]),
        ("KẾT LUẬN & NHÓM", "RF A giảm MAE 2,80%\nImportance không là nhân quả\nVideo chưa quay\nThành viên/đóng góp: [CẦN BỔ SUNG]\nRubric/poster: [CẦN BỔ SUNG]", FIGURES["demo_screenshot"]),
    ]
    for idx, (title, body, figure) in enumerate(sections):
        row, col = divmod(idx, 3)
        x, y = columns[col], row_y[row]
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, PptInches(x), PptInches(y), PptInches(card_w), PptInches(card_h))
        box.fill.solid(); box.fill.fore_color.rgb = _hex("FFFFFF")
        box.line.color.rgb = _hex("CBD9DE")
        textbox(slide, title, x + 0.3, y + 0.25, card_w - 0.6, 1.0, 24, TEAL, True)
        textbox(slide, body, x + 0.35, y + 1.55, card_w - 0.7, 4.4, 19, NAVY)
        if figure:
            _slide_image(slide, root, figure, x + 0.45, y + 6.0, card_w - 0.9, card_h - 6.5)
    textbox(slide, "Kết quả mô tả trên cohort đã đánh giá; không phải hướng dẫn/cảnh báo sức khỏe.", 1.0, 47.15, 33.5, 0.45, 16, GRAY)
    if len(prs.slides) != 1:
        raise ValueError("Poster PowerPoint must contain exactly one slide")
    path = out / "NhomXX_DuBaoPM25_BacKinh_Poster.pptx"
    prs.save(path)
    return path


def _traceability(root: Path, e: dict) -> list[dict]:
    trace = []
    for table_id, title, paths in TABLES:
        trace.append({
            "id": table_id, "kind": "table", "title": title,
            "source_paths": paths,
            "sources": [{"path": p, **e["source_hashes"][p]} for p in paths],
            "run_ids": (
                list(T13_RUNS.values()) if table_id in {"T04", "T05", "T06", "T07"}
                else e["summary_run_ids"] if table_id == "T09"
                else [e["t17b_parent_run_id"], *[row["run_id"] for row in e["t17b"].values()]] if table_id == "T10"
                else []
            ),
            "scope": "saved artifacts only",
        })
    for figure_id, title, path in FIGURE_INDEX:
        trace.append({
            "id": figure_id, "kind": "figure", "title": title,
            "source_paths": [path],
            "sources": [{"path": path, **e["source_hashes"][path]}],
            "run_ids": [e["models"]["random_forest"]["run_id"]] if figure_id in {"H03", "H04", "H05", "H06", "H07", "H08"} else [],
            "scope": "saved source image, no new model output",
        })
    trace.append({
        "id": "T13_RUNS", "kind": "evaluation", "title": "T13 primary Test metrics",
        "source_paths": ["reports/final_evaluation/comparison.csv"],
        "sources": [{"path": "reports/final_evaluation/comparison.csv", **e["source_hashes"]["reports/final_evaluation/comparison.csv"]}],
        "run_ids": list(T13_RUNS.values()), "scope": "test already exposed in T13; not reopened",
    })
    trace.append({
        "id": "T17B", "kind": "validation", "title": "T17b supplementary validation candidates",
        "source_paths": ["reports/tables/experiment_summary.csv", "docs/supplementary_experiments.md"],
        "sources": [{"path": p, **e["source_hashes"][p]} for p in ("reports/tables/experiment_summary.csv", "docs/supplementary_experiments.md")],
        "run_ids": [row["run_id"] for row in e["t17b"].values()],
        "parent_run_id": e["t17b_parent_run_id"],
        "scope": "validation only; test not accessed",
    })
    return trace


def _write_indexes(root: Path, out: Path, e: dict):
    with (out / "figure_table_index.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "kind", "title", "source_paths", "run_ids", "metric_scope"])
        for index, title, paths in TABLES:
            run_ids = (
                e["summary_run_ids"] if index == "T09"
                else [e["t17b_parent_run_id"], *[row["run_id"] for row in e["t17b"].values()]] if index == "T10"
                else list(T13_RUNS.values()) if index in {"T04", "T05", "T06", "T07"}
                else []
            )
            writer.writerow([index, "table", title, ";".join(paths), ";".join(run_ids), "linked artifact"])
        for index, title, path in FIGURE_INDEX:
            writer.writerow([index, "figure", title, path, "", "existing figure"])
    _write_json(out / "traceability.json", {
        "schema_version": "t15-traceability-v1",
        "task_id": "T15",
        "source_commit": e["source_commit"],
        "generated_at": e["generated_at"],
        "source_hashes": e["source_hashes"],
        "items": _traceability(root, e),
        "t13_run_ids": T13_RUNS,
        "t17b_parent_run_id": e["t17b_parent_run_id"],
        "t17b_run_ids": {key: value["run_id"] for key, value in e["t17b"].items()},
        "protected_snapshot": e["protected_snapshot"],
        "test_raw_accessed": False,
        "model_fit_performed": False,
        "ledger_written": False,
    })
    _write_json(out / "verification.json", {
        "schema_version": "t15-verification-v1",
        "status": "DRAFT_BUILT",
        "generated_at": e["generated_at"],
        "source_commit": e["source_commit"],
        "report_files": [],
        "metrics_source": "reports/final_evaluation/comparison.csv and reports/tables/experiment_summary.csv",
        "source_hashes": e["source_hashes"],
        "protected_snapshot": e["protected_snapshot"],
        "evidence_conflicts": e["evidence_conflicts"],
        "limitations": [
            "Group member identities/contributions and lecturer rubric/poster dimensions remain [CẦN BỔ SUNG].",
            "Input-requested Dingling and JJA values do not match saved grouped_metrics.csv; report uses artifact values.",
            "Requested T17b run 3cc5790dd34d4ca29435f4da86b68ae7 is not in current ledger or artifacts.",
            "No new model training, tuning, refit, or raw test access performed.",
        ],
    })


def _needs_input(out: Path, e: dict, config: dict):
    lines = [
        "# BẢN NHÁP — cần hoàn thiện trước khi nộp",
        "",
        "Không điền thông tin cá nhân hoặc rubric bằng suy đoán. Nhóm cần tự xác nhận:",
        "",
        f"- Số nhóm: {config['group_number']}",
        "- Họ tên, MSSV, GitHub, vai trò, phần việc thật và minh chứng của từng thành viên.",
        "- Tỷ lệ đóng góp được nhóm xác nhận; tổng đúng 100%. Không suy phần trăm từ số commit.",
        "- Rubric chính thức, tài liệu bài giảng và trang/slide cụ thể.",
        f"- Kích thước/chiều poster: {config['poster_size_inches']['note']}.",
        "- Xác nhận thành viên đã đọc/hiểu/review phần nhận; video demo thật và yêu cầu nộp.",
        "",
        "Dữ liệu nhóm và rubric trống khiến toàn bộ báo cáo/slide/poster vẫn là bản nháp.",
        "",
        "## Sai khác nguồn cần đối chiếu",
        "",
        "- Yêu cầu tác vụ nêu RF Dingling MAE 8,6287 và JJA MAE 6,6666; `grouped_metrics.csv` hiện lưu 8,5951 và 7,6437. Báo cáo dùng số từ artifact.",
        "- Run T17b `3cc5790dd34d4ca29435f4da86b68ae7` không được tìm thấy trong ledger hiện tại; tài liệu supplementary ghi lỗi lần đầu ở Stack metadata.",
        "",
        "Không thay đổi artifact T13/T17b, `experiments/experiment_log.csv` hoặc `reports/midterm/` để làm biến mất khác biệt.",
    ]
    (out / "NEEDS_GROUP_INPUT.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def build_final_deliverables(root: Path = ROOT, output_dir: Path | None = None) -> dict:
    root = Path(root).resolve()
    out = Path(output_dir).resolve() if output_dir else root / "reports/final"
    out.mkdir(parents=True, exist_ok=True)
    evidence = collect_evidence(root)
    config = read_json(root / "configs/final_deliverables.json")
    _build_docx(root, out, evidence)
    _build_slides(root, out, evidence)
    _poster_png(root, out / "NhomXX_DuBaoPM25_BacKinh_Poster.png", evidence, config)
    _poster_pptx(root, out, evidence, config)
    _write_indexes(root, out, evidence)
    _needs_input(out, evidence, config)
    files = sorted(path for path in out.iterdir() if path.is_file() and path.name != "verification.json")
    check = {
        "status": "DRAFT_BUILT",
        "task_id": "T15",
        "files": [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in files],
        "model_fit_performed": False,
        "raw_test_samples_accessed": False,
        "experiment_log_written": False,
    }
    print(json.dumps(check, ensure_ascii=True))
    return check


def _office_text(path: Path) -> tuple[str, int, int]:
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError(f"Office archive CRC failed: {path.name}")
    if path.suffix == ".docx":
        doc = Document(path)
        text = "\n".join([p.text for p in doc.paragraphs] + [c.text for t in doc.tables for row in t.rows for c in row.cells])
        return text, len(doc.paragraphs), len(doc.tables)
    prs = Presentation(path)
    text = "\n".join(shape.text for slide in prs.slides for shape in slide.shapes if shape.has_text_frame)
    return text, len(prs.slides), sum(1 for slide in prs.slides for shape in slide.shapes if shape.has_table)


def verify_final_deliverables(root: Path = ROOT, output_dir: Path | None = None) -> dict:
    root = Path(root).resolve()
    out = Path(output_dir).resolve() if output_dir else root / "reports/final"
    evidence = collect_evidence(root)
    trace = read_json(out / "traceability.json")
    expected_snapshot = trace["protected_snapshot"]
    current_snapshot = protected_snapshot(root)
    if current_snapshot["ledger_sha256"] != expected_snapshot["ledger_sha256"]:
        raise AssertionError("experiments/experiment_log.csv changed since T15 build")
    if current_snapshot["midterm_tree_sha256"] != expected_snapshot["midterm_tree_sha256"]:
        raise AssertionError("reports/midterm changed since T15 build")
    for relative, expected_hash in trace["source_hashes"].items():
        if sha256(root / relative) != expected_hash["sha256"]:
            raise AssertionError(f"Source artifact changed since build: {relative}")
    files = {
        "docx": out / "NhomXX_DuBaoPM25_BacKinh_CuoiKy.docx",
        "slides": out / "NhomXX_DuBaoPM25_BacKinh_CuoiKy.pptx",
        "poster_pptx": out / "NhomXX_DuBaoPM25_BacKinh_Poster.pptx",
        "poster_png": out / "NhomXX_DuBaoPM25_BacKinh_Poster.png",
    }
    for path in files.values():
        if not path.is_file() or path.stat().st_size == 0:
            raise AssertionError(f"Missing/empty final deliverable: {path.name}")
    doc_text, doc_paragraphs, doc_tables = _office_text(files["docx"])
    slides_text, slide_count, slide_tables = _office_text(files["slides"])
    poster_text, poster_slide_count, _ = _office_text(files["poster_pptx"])
    required = [
        "Chương 1 — Giới thiệu", "Chương 2 — Cơ sở lý thuyết",
        "Chương 3 — Dữ liệu và phương pháp", "Chương 4 — Thực nghiệm",
        "Chương 5 — Kết luận", "10,1618", "10,3844", "9,8772",
        "Nongzhanguan__20170127T21", "2369ca5", "a819acf",
        "9,3798", "9,2746", "9,2321", "2512bc9c844a4b39a150c52f6bded9db",
        "23/33", PLACEHOLDER,
    ]
    missing = [phrase for phrase in required if phrase not in doc_text]
    if missing:
        raise AssertionError("Report missing required content: " + ", ".join(missing))
    if not (16 <= slide_count <= 20):
        raise AssertionError(f"Expected 16–20 slides, got {slide_count}")
    if poster_slide_count != 1 or "[CẦN BỔ SUNG]" not in poster_text:
        raise AssertionError("Poster deck is missing the placeholder or single-page layout")
    if PLACEHOLDER not in slides_text or "9,8772" not in slides_text:
        raise AssertionError("Slides missing required placeholder or T13 result")
    with Image.open(files["poster_png"]) as poster:
        poster.verify()
    with Image.open(files["poster_png"]) as poster:
        poster_size = list(poster.size)
    if poster_size != [2400, 3200]:
        raise AssertionError(f"Unexpected poster PNG dimensions: {poster_size}")
    forbidden = [str(root).lower(), str(root).replace("\\", "/").lower()]
    for office_path in (files["docx"], files["slides"], files["poster_pptx"]):
        with zipfile.ZipFile(office_path) as archive:
            raw = b"\n".join(archive.read(name) for name in archive.namelist() if name.endswith(".xml")).lower()
        if any(path.encode("utf-8") in raw for path in forbidden):
            raise AssertionError(f"Personal absolute path embedded in {office_path.name}")
    conflicts = evidence["evidence_conflicts"]
    report = {
        "schema_version": "t15-verification-v1",
        "status": "PASS_WITH_DRAFT_PLACEHOLDERS_AND_SOURCE_CONFLICTS",
        "task_id": "T15",
        "source_commit": evidence["source_commit"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            key: {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for key, path in files.items()
        },
        "docx_paragraphs": doc_paragraphs,
        "docx_tables": doc_tables,
        "presentation_slides": slide_count,
        "presentation_tables": slide_tables,
        "poster_slides": poster_slide_count,
        "poster_png_dimensions": poster_size,
        "office_crc": "PASS",
        "required_report_content": "PASS",
        "personal_absolute_paths": "NONE",
        "traceability_source_hashes": "PASS",
        "protected_experiment_ledger_unchanged": current_snapshot["ledger_sha256"] == expected_snapshot["ledger_sha256"],
        "protected_midterm_tree_unchanged": current_snapshot["midterm_tree_sha256"] == expected_snapshot["midterm_tree_sha256"],
        "test_raw_samples_accessed": False,
        "model_fit_performed": False,
        "ledger_written": False,
        "t13_test_was_exposed_previously": True,
        "evidence_conflicts": conflicts,
        "notes": [
            "Automated checks validate file structure and text, not full-page visual review or Office rendering.",
            "Group identities, contributions, official rubric, poster dimensions, and video remain [CẦN BỔ SUNG].",
            "Source metric conflicts are explicit; report follows the checked aggregate artifacts.",
        ],
    }
    _write_json(out / "verification.json", report)
    print(json.dumps(report, ensure_ascii=True))
    return report
