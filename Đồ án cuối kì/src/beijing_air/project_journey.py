"""NB01: evidence presentation only; never import model runners or load weights."""

import ast
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import re
import subprocess

import pandas as pd
from IPython.display import Code, Image, Markdown, display


P = "24cef47874a94d9faa7bfcbae29b5c58"
R = "aec8630115714bb59d5c89c8a6b368c1"
F = "780ecb7fb59d48bea58d5e4a076f1f26"
TUNE = "c895894bcf5a4ff28982fbb1ca9d69d9"
RA = "32e65c5a4cbc489c905cf146b743867f"
RB = "48d2f03be4614a25906f84d98df9e9dc"
RC = "3a9f2500e4dd4ef28d7bc20def6f79c8"
FINAL = "a8cb7fda3f1441968b31c26c18e57ebf"
RF_FINAL = "24cd6d765f214d52aa26e5988380e2cd"
REPO_URL = "https://github.com/Shirayuki266/SGU26k2_Machine_Learning_Group"
TITLE = "PM25_Project_Journey_T01_T14"


def project_root(start=None):
    start = Path(start or Path.cwd()).resolve()
    for path in (start, *start.parents):
        if (path/"pyproject.toml").is_file() and (path/"src/beijing_air").is_dir():
            return path
    raise FileNotFoundError("Run inside the final project containing pyproject.toml")


def safe_text(text):
    """Do not reproduce historical personal paths, including in code excerpts."""
    text = re.sub(r"(?<!\w)[A-Za-z]:[\\/][^\s\"'<>]+", "[LOCAL_PATH_REDACTED]", str(text))
    return re.sub(r"/(?:Users|home)/[^\s\"'<>]+", "[LOCAL_PATH_REDACTED]", text)


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", check=False)
    return result.stdout.strip() if result.returncode == 0 else "Không xác minh được"


def locate(symbol, search_dirs):
    """AST positions, with class qualification; never import the inspected modules."""
    results = []
    for directory in search_dirs:
        path = Path(directory)
        files = [path] if path.is_file() else sorted(path.rglob("*.py"))
        for file in files:
            if not file.is_file() or file.suffix != ".py":
                continue
            tree = ast.parse(file.read_text(encoding="utf-8-sig"))

            def visit(nodes, prefix=""):
                for node in nodes:
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        name = prefix+node.name
                        if name == symbol or ("." not in symbol and node.name == symbol):
                            results.append({"path": file, "symbol": name, "start": node.lineno,
                                            "end": node.end_lineno, "docstring": ast.get_docstring(node)})
                        visit(node.body, name+".")
            visit(tree.body)
    return results


def last_commit(path, root=None):
    root = Path(root or project_root())
    path = Path(path)
    path = path if path.is_absolute() else root/path
    return git(root, "log", "-1", "--format=%h %ad", "--date=short", "--", str(path)) or "Chưa commit"


def code_excerpt(path, start, end, max_lines=60):
    """Bound long symbols to their signature/docstring and report actual AST range."""
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    selected = lines[start-1:end]
    if Path(path).suffix != ".py":
        return safe_text("\n".join(selected[:max_lines-2]+(
            [f"# ... excerpt; actual source lines {start}-{end}"] if len(selected) > max_lines else [])))
    if len(selected) > max_lines:
        tree = ast.parse("\n".join(lines))
        node = next((n for n in ast.walk(tree) if getattr(n, "lineno", None) == start
                     and isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))), None)
        body = node.body if node else []
        stop = body[0].lineno-1 if body else start
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            stop = body[0].end_lineno
        selected = lines[start-1:min(stop, start+max_lines-4)]
        selected += [f"# ... omitted; actual source lines {start}-{end} ({end-start+1} lines)"]
    return safe_text("\n".join(selected))


def show_code(path, start, end):
    language = {".ps1": "powershell", ".json": "json"}.get(Path(path).suffix, "python")
    display(Code(code_excerpt(path, start, end), language=language))


def related_tests(root, module, symbol):
    """Only return AST-existing tests which mention the module or symbol.

    Module-level matches are supporting module tests, not a claimed call graph.
    """
    results = []
    token = symbol.split(".")[-1] if symbol else ""
    specific = token not in {"", "main", "fit", "transform", "render", "execute", "load", "save"}
    for file in sorted((root/"tests").glob("test_*.py")):
        source = file.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        imports_module = any(isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[-1] == module
                             for n in ast.walk(tree))
        imports_module |= any(isinstance(n, ast.Import) and any(a.name.split(".")[-1] == module for a in n.names)
                              for n in ast.walk(tree))
        names_script = module+".py" in source
        if not imports_module and not names_script and not (specific and re.search(r"\b"+re.escape(token)+r"\b", source)):
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                body = ast.get_source_segment(source, node) or ""
                if token and re.search(r"\b"+re.escape(token)+r"\b", body):
                    results.append(file.relative_to(root).as_posix()+"::"+node.name)
        if not any(item.startswith(file.relative_to(root).as_posix()+"::") for item in results):
            # A real module test is still relevant, explicitly documented as such.
            tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
            results.extend(file.relative_to(root).as_posix()+"::"+n.name for n in tests[:2])
    return results


class Evidence:
    """Read presentation artifacts, rejecting data samples and model binaries."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.sources = {}
        self.missing = []

    def path(self, name):
        path = (self.root/name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Evidence path escapes project")
        rel = path.relative_to(self.root)
        if rel.parts[0] == "data" or path.suffix.lower() in {".joblib", ".pkl", ".pickle", ".sqlite3"}:
            raise ValueError("Raw/processed samples and model loading are forbidden in NB01")
        return path

    def read(self, name):
        path = self.path(name)
        name = path.relative_to(self.root).as_posix()
        if not path.is_file():
            message = "Không tìm thấy artifact: "+name
            if message not in self.missing:
                self.missing.append(message)
            self.sources[name] = {"exists": False, "bytes": None, "sha256": None}
            display(Markdown(message))
            return None
        data = path.read_bytes()
        self.sources[name] = {"exists": True, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        return data

    def json(self, name):
        raw = self.read(name)
        return json.loads(raw.decode("utf-8-sig")) if raw is not None else {}

    def csv(self, name):
        raw = self.read(name)
        return pd.read_csv(io.BytesIO(raw)) if raw is not None else pd.DataFrame()


# Task definitions are historical interpretation; all numbers/positions below are read at execution.
# No Issue number is inferred from a task number.
TASKS = {
    "T01": ("Môi trường và cấu trúc", 2, 8, "", "scripts/check_imports.py", "main",
            "Cài/import được trước khi xử lý dữ liệu?",
            "Dùng package src/beijing_air, đường dẫn tương đối, seed 42/horizon 1; smoke tách full. Chủ đề 02: quy trình.",
            "docs/t01_environment_verification.md", "T01 chủ yếu xác minh file hiện có; script import trả kết quả terminal, không sinh một file môi trường giả."),
    "T02": ("Đặc tả dự báo/CRISP-DM", 3, 9, "", "configs/default.json", "",
            "Input đến t và output cùng trạm đúng t+1 được định nghĩa nhất quán?",
            "Hồi quy cuốn chiếu trên trạm đã quan sát; split theo target time; khóa test. Chủ đề 02/05: protocol và đánh giá.",
            "docs/problem_definition.md", "Đặc tả là quyết định thiết kế, không phải kết quả thực nghiệm; T13 refit train+validation theo quyền bổ sung."),
    "T03": ("Nguồn UCI 501", 4, 10, "", "scripts/download_uci.ps1", "",
            "Đúng bộ PRSA2017 nhiều trạm, có nguồn/checksum/license?",
            "Giữ raw; manifest ghi ngày tải thật nếu biết; No là chỉ số hàng, không là feature. Chủ đề 02/03: dữ liệu.",
            "reports/data_manifest.json", "Đọc manifest/audit đã lưu; NB01 không tải lại hay mở raw. Kiểu dữ liệu audit khác dtype runtime pandas."),
    "T04": ("Hợp nhất và audit", 5, None, "", "src/beijing_air/data.py", "load_station_data",
            "Khóa station–timestamp và giá trị có hợp lệ trước tạo target?",
            "Từ chối khóa trùng; không impute, không xóa đỉnh bằng IQR; tách audit khỏi model log. Chủ đề 03.",
            "reports/quality_full/summary.json", "Giữ nồng độ cao hợp lệ để nghiên cứu; warning không đồng nghĩa phải loại dòng. Không có PR riêng T04 được xác minh."),
    "T04-LOG": ("Nhật ký thực nghiệm", 6, 7, "", "src/beijing_air/experiment_logging.py", "ExperimentLogger.start_run",
                "Truy vết mỗi run, config, metric, trạng thái và artifact thế nào?",
                "Run ID riêng, CSV upsert và file riêng từng run; failed run giữ lỗi. Audit/fixture không là run mô hình. Chủ đề 02/05.",
                "experiments/experiment_log.csv", "Số hồ sơ gồm parent/candidate/fold/smoke/refit; không phải số model độc lập. Không sửa/ghi ledger trong NB01."),
    "T05": ("Target đúng giờ và split", 1, 11, "", "src/beijing_air/samples.py", "build_samples",
            "Có ghép nhãn đúng một giờ khi thiếu giờ và split chung mọi trạm?",
            "Join station/t+1h, không shift theo hàng, không impute target; fit label phải sẵn có trước origin đánh giá. Chủ đề 03/05.",
            "reports/splits_full/split_summary.csv", "Chỉ đọc audit số mẫu/ngày. Bảng CV bên dưới là đầu ra T11 liên hệ lại T05, không nhận là T05 đã search."),
    "T06": ("EDA chỉ train", 12, 13, "", "src/beijing_air/eda.py", "run_eda",
            "Missing, đỉnh ô nhiễm, chu kỳ và khác biệt trạm gợi ý xử lý gì?",
            "EDA train operational; không EDA test, không suy tương quan thành nhân quả. Chủ đề 03/Lab03.",
            "reports/eda_train/numeric_summary.csv", "Hình/tables đã sinh từ train. Dùng missing để thiết kế imputation/indicator; lag là giả thuyết cần A/B kiểm chứng."),
    "T07": ("Feature A/B có tính nhân quả", 14, 15, "", "src/beijing_air/features.py", "build_features",
            "Lag/rolling đúng giờ riêng trạm, không tạo quan sát giả?",
            "A dùng số đo t và lịch t+1; B thêm lag 1/3/6/12/24, rolling 3/6/12/24 kết thúc t, min_periods=window. Chủ đề 03/04.",
            "reports/features_full/feature_registry.csv", "Giữ sample ID; lịch sử thiếu để missing, không backfill. Registry/missing là artifact chuẩn bị, không metric mô hình."),
    "T08": ("Pipeline preprocessing", 16, 17, "", "src/beijing_air/preprocessing.py", "FeatureSchema._validated",
            "Các bước học có chỉ fit train/fold và dùng lại cho inference?",
            "Numeric median/indicator; categorical imputer/OHE unknown-ignore; Ridge scale, RF không; policy dự báo âm identity. Chủ đề 03/06/Ensemble.",
            "configs/preprocessing.json", "T08 chỉ factories/fixture. Issue #35 được phát hiện ở T14, đã sửa PR #37; không refit hoặc thay model lịch sử."),
    "T09": ("Persistence baseline", 18, 19, P, "src/beijing_air/baseline.py", "predict_persistence",
            "Mốc validation MAE/RMSE/R² cho dự báo trước một giờ?",
            "PM2.5(t+1)=PM2.5(t); fallback lịch sử cùng trạm tối đa 24h rồi median train; cùng primary IDs. Chủ đề 05.",
            f"artifacts/experiments/{P}/metrics.json", "Primary yêu cầu PM2.5(t) có sẵn nên fallback=0; operational mới đo ảnh hưởng thiếu t. Smoke không thay full."),
    "T10": ("Ridge/RF ban đầu", 20, 21, R+"; "+F, "scripts/run_initial_models.py", "execute_model",
            "Hai mô hình đơn giản bộ A có vượt persistence và chi phí bao nhiêu?",
            "Một config full/model sau smoke; Ridge alpha1, RF ngân sách nhỏ; cố định sample IDs/features. Chủ đề 05/06/Ensemble.",
            "reports/initial_models/comparison.csv", "Gap âm ở giai đoạn này không chứng minh không overfit: train/validation có phân phối theo mùa khác nhau; cần CV theo thời gian."),
    "T11": ("Tuning temporal CV hữu hạn", 22, 23, TUNE, "scripts/run_tuning.py", "execute_search",
            "Điều chuẩn Ridge thay đổi có cải thiện validation?",
            "4 alpha × 3 expanding folds, purge nhãn biên, refit preprocessing từng fold; không RF search do ngân sách. Chủ đề 05/06.",
            "reports/tuning/candidates.csv", "Pooled theo số mẫu khác mean±std fold; std là mô tả, không khoảng tin cậy. Train chỉ khoảng hai năm, fold sớm thiếu mùa đánh giá."),
    "T12": ("A/B/C và khóa phương án", 24, 25, RB+"; "+RC, "src/beijing_air/feature_selection.py", "GroupRidgeSelector.fit",
            "Lag/rolling và chọn nhóm feature đóng góp gì khi giữ alpha cố định?",
            "Ridge alpha0.1 A/B/C; selector theo nhóm raw giữ toàn bộ one-hot của nhóm; tối đa3k ×3fold. Chọn triển khai bằng validation. Chủ đề04/05/06.",
            "reports/ablation/comparison.csv", "So sánh cố định alpha không phải tối ưu riêng từng bộ. Không chấm B/C trên test; frozen snapshot giữ lịch sử trước T13."),
    "T13": ("Đánh giá test sau khóa", 32, 33, FINAL, "src/beijing_air/final_evaluation.py", "execute",
            "Phương án khóa từ development tổng quát hóa trên kỳ test ra sao?",
            "Refit train+validation, chấm cùng test IDs một lần/config; phân tích nhóm/importance chỉ chẩn đoán. Chủ đề05/06/Ensemble/04.",
            "reports/final_evaluation/comparison.csv", "T13 artifact, chỉ đọc. Không chọn lại model bằng test; lỗi/importance không là bằng chứng nhân quả. RF chưa có temporal CV."),
    "T14": ("Demo pipeline đã chọn", 34, 36, RF_FINAL, "src/beijing_air/demo.py", "forecast_at",
            "Demo cùng mẫu có khớp pipeline đã lưu mà không fit lại?",
            "Cache model, kiểm schema/version, quan sát đến t; actual chỉ đọc sau predict; không tự đổi AQI. Chủ đề05/Ensemble.",
            "reports/demo/inference_verification.json", "T13 artifact, chỉ đọc: chỉ phát lại QA/screenshot đã lưu. Không load weights, chạy inference mới, deploy hay tuyên bố đã có video."),
}

EXTRA_COMPONENTS = {
    "T03": [("scripts/audit_raw.ps1", "")],
    "T04": [("src/beijing_air/data.py", "validate_temporal_integrity")],
    "T04-LOG": [("src/beijing_air/experiment_logging.py", s) for s in
                 ("ExperimentLogger.log_metrics", "ExperimentLogger.log_artifact", "ExperimentLogger.finish_run")],
    "T05": [("src/beijing_air/samples.py", s) for s in ("temporal_split", "check_label_availability")],
    "T07": [("src/beijing_air/features.py", "features_for_prediction")],
    "T08": [("src/beijing_air/preprocessing.py", s) for s in ("make_preprocessor", "make_regression_pipeline")],
    "T09": [("src/beijing_air/metrics.py", "regression_metrics"), ("src/beijing_air/baseline.py", "fit_persistence")],
    "T11": [("src/beijing_air/temporal_cv.py", "expanding_folds"), ("src/beijing_air/tuning.py", "aggregate_folds")],
    "T12": [("src/beijing_air/feature_selection.py", "make_ablation_pipeline")],
    "T13": [("src/beijing_air/final_evaluation.py", "validate_frozen"), ("scripts/run_final_evaluation.py", "main")],
    "T14": [("src/beijing_air/demo.py", "load_demo_model"), ("src/beijing_air/demo_ui.py", "render")],
}

# A source file is not a generated result. These roles explain each task's hand-off.
OUTPUT_ROLES = {
    "T01": [("scripts/check_imports.py", "script xác minh", "Kiểm import/package/version; kết quả terminal, không tự sinh file B"),
            ("docs/t01_environment_verification.md", "biên bản kiểm đã chạy", "Ghi lệnh, phiên bản, kết quả và giới hạn T01"),
            ("pyproject.toml", "cấu hình môi trường kế thừa/cập nhật", "Nguồn dependencies duy nhất, không requirements.txt song song")],
    "T02": [("docs/problem_definition.md", "đặc tả", "Input/output/RQ, phạm vi hồi quy và giả định khả dụng t"),
            ("docs/experiment_plan.md", "thiết kế thực nghiệm", "A/B/C, baseline/metric/CV và luật không leakage"),
            ("docs/project_plan.md", "kế hoạch", "Mapping task/CRISP-DM; không phải metric mô hình")],
    "T03": [("scripts/download_uci.ps1", "script nguồn", "Tải/kiểm ZIP PRSA nhiều trạm; fallback thủ công"),
            ("reports/data_manifest.json", "kết quả provenance", "Nguồn, license, ngày tải đã ghi và SHA nội dung"),
            ("reports/raw_audit_full.json", "kết quả audit raw", "Đếm số file/trạm/dòng/cột/giờ mà không impute")],
    "T04": [("src/beijing_air/data.py", "loader/audit nguồn", "Ghép timestamp/station, kiểm khóa; không tạo target"),
            ("reports/quality_full/summary.json", "kết quả audit", "Thống kê trước/sau, missing, warning/error và quy tắc"),
            ("reports/quality_full/stations.csv", "kết quả theo trạm", "Khóa/giờ khuyết/trùng; dữ liệu merged ở data/processed không mở trong NB01")],
    "T04-LOG": [("src/beijing_air/experiment_logging.py", "hạ tầng nguồn", "start/metrics/artifact/finish, failure và upsert"),
                ("experiments/experiment_log.csv", "ledger tích lũy từ T09 trở đi", "Một hàng một run ID; logger task không tự tạo metric giả"),
                (f"artifacts/experiments/{P}/metrics.json", "ví dụ run thật T09", "Metric và link cấu hình/artifact riêng theo run")],
    "T05": [("scripts/build_samples.py", "script gọi module", "Tạo target exact +1h và snapshot split"),
            ("reports/splits_full/split_manifest.json", "manifest kết quả", "Nguồn, mốc, schema và checksum/IDs truy vết"),
            ("reports/splits_full/split_summary.csv", "bảng kết quả", "Số mẫu/ngày operational và primary; không phải score test")],
    "T06": [("notebooks/01_train_eda.ipynb", "notebook EDA gọi module", "Bài EDA train gốc, không tái chạy trong NB01"),
            ("reports/eda_train/numeric_summary.csv", "bảng EDA", "Phân phối/missing/outlier flags làm căn cứ xử lý"),
            ("docs/eda_findings.md", "diễn giải kết quả", "Quyết định T07/T08 từ các bảng/hình train")],
    "T07": [("scripts/build_features.py", "script gọi module", "Tạo A/B nhân quả, giữ sample IDs"),
            ("reports/features_full/feature_registry.csv", "dictionary kết quả", "Tên/kiểu/nguồn/thời điểm khả dụng và bộ feature"),
            ("reports/features_full/missing_summary.csv", "audit feature", "Phân biệt thiếu hiện tại, thiếu giờ/giá trị lag và warm-up")],
    "T08": [("src/beijing_air/preprocessing.py", "factory nguồn", "Cùng config dựng pipeline cho train/CV/inference"),
            ("configs/preprocessing.json", "quyết định trước fit", "Imputation/OHE/scaling và hậu xử lý nhất quán"),
            ("docs/preprocessing.md", "biên bản kiểm fixture", "Train-only, unseen category, names và save/load; chưa full model ở T08")],
    "T09": [("scripts/run_baseline.py", "CLI smoke/full", "Gọi persistence và logger trên validation IDs cố định"),
            (f"artifacts/experiments/{P}/metrics.json", "kết quả run full", "Mốc MAE/RMSE/R² và fallback theo cohort"),
            ("reports/evaluation/validation_manifest.json", "manifest so sánh", "Khóa sample IDs/nguồn cho các model sau")],
    "T10": [("scripts/run_initial_models.py", "CLI smoke/full", "Một cấu hình đầu/model dùng A/pipeline T08"),
            ("reports/initial_models/comparison.csv", "bảng kết quả", "Train/validation, gap, thời gian và dự báo âm"),
            ("docs/initial_findings.md", "nhận xét", "Cơ sở chọn vấn đề tuning; không buộc ML phải thắng")],
    "T11": [("scripts/run_tuning.py", "search runner", "Ridge alpha hữu hạn, refit preprocessing từng fold"),
            ("reports/tuning/candidates.csv", "kết quả CV", "Pooled và mean/std khác nhau; giữ mọi candidate"),
            ("reports/tuning/before_after.csv", "kết quả refit validation", "Chứng minh CV tốt hơn không đảm bảo val tốt hơn")],
    "T12": [("src/beijing_air/feature_selection.py", "selector nguồn", "Chọn nhóm raw, giữ cả nhóm one-hot; fit trong fold"),
            ("reports/ablation/comparison.csv", "bảng A/B/C", "Đóng góp lag/rolling/selection khi giữ alpha"),
            ("reports/ablation/frozen_model.json", "công thức khóa T12", "Chọn RF A từ validation; không có weights ở thời điểm khóa")],
    "T13": [("scripts/run_final_evaluation.py", "runner gốc đã dùng", "Refit train+val rồi chấm test sau khóa; NB01 không gọi"),
            ("reports/final_evaluation/execution.json", "biên bản test thật", "Lần mở test, child IDs và lựa chọn từ development"),
            ("reports/final_evaluation/comparison.csv", "kết quả test đã lưu", "MAE/RMSE/R²/%giảm baseline, không chọn lại phương án")],
    "T14": [("app/streamlit_app.py", "entry point demo", "Gọi UI/cache/pipeline đã lưu, không train khi rerun"),
            ("reports/demo/inference_verification.json", "kết quả QA đã lưu", "Cùng sample: dự báo khớp saved T13 prediction"),
            ("docs/demo_video_storyboard.md", "kịch bản", "Hướng dẫn thành viên quay; không phải video đã hoàn thành")],
}


class Journey:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.evidence = Evidence(self.root)
        self.code_rows = []
        self.checks = []
        self.run_rows = None
        self.started = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")

    def md(self, text):
        display(Markdown(safe_text(text)))

    def table(self, frame, source, columns=None, limit=16, run_id="— (không phải model run)"):
        if columns and not frame.empty:
            frame = frame[[c for c in columns if c in frame.columns]]
        if frame.empty:
            self.md("Không có hàng để hiển thị; xem thông báo thiếu artifact.")
        else:
            display(frame.head(limit).style.format(precision=6, na_rep="chưa có"))
            if len(frame) > limit:
                self.md(f"Hiển thị {limit}/{len(frame)} hàng; file nguồn giữ đầy đủ.")
        self.md(f"Nguồn: `{source}` · run_id: `{run_id}`. MAE/RMSE/PM2.5: µg/m³; R² và tỷ lệ: không đơn vị; thời gian: giây.")

    def csv(self, path, **kwargs):
        frame = self.evidence.csv(path)
        self.table(frame, path, **kwargs)
        return frame

    def image(self, path, caption, run_id="— (EDA/audit train)"):
        data = self.evidence.read(path)
        if data is not None:
            self.md("**"+caption+"**")
            display(Image(data=data, width=1050))
            self.md(f"Ảnh gốc: `{path}` · run_id: `{run_id}`. Nồng độ/sai số: µg/m³; số mẫu: count; tương quan: không đơn vị.")

    def doc(self, path, max_lines=30):
        raw = self.evidence.read(path)
        if raw is not None:
            # Render as excerpt, with original line numbers to avoid implying complete quotation.
            text = raw.decode("utf-8-sig").splitlines()
            self.md(f"Trích `{path}` dòng 1–{min(max_lines, len(text))} (tổng {len(text)} dòng):\n\n"+
                    "\n".join("> "+line for line in text[:max_lines]))

    def environment(self, light=False, heavy=False):
        self.md("**Cờ mặc định:** RERUN_LIGHT="+str(light)+", RERUN_HEAVY="+str(heavy)+
                ". NB01 không cung cấp đường gọi huấn luyện/tuning. Tính lại metric rẻ từ predictions là kiểm chứng, không phải run gốc.")
        versions = {"Python": platform.python_version()}
        for package in ("pandas", "numpy", "scikit-learn", "matplotlib", "nbconvert"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = "chưa cài"
        display(pd.DataFrame(versions.items(), columns=["Thành phần", "Phiên bản đang đọc notebook"]))
        dirty = bool(git(self.root, "status", "--porcelain"))
        self.md(f"Commit khi chạy: `{git(self.root, 'rev-parse', '--short=12', 'HEAD')}` · ngày commit: "
                f"`{git(self.root, 'show', '-s', '--format=%cs', 'HEAD')}` · thời điểm chạy: `{self.started}` · "
                f"git: **{'bẩn (đang sinh notebook/tài liệu)' if dirty else 'sạch'}**. "
                "Đây là source anchor khi sinh, không tự nhận hash của commit output tương lai. Issue #35 liên quan pandas 3.x.")

    def components(self, task):
        spec = TASKS[task]
        return list(dict.fromkeys([(spec[4], spec[5]), *EXTRA_COMPONENTS.get(task, [])]))

    def code_map(self, task, excerpt=True):
        spec = TASKS[task]
        rows = []
        for file, symbol in self.components(task):
            path = self.root/file
            raw = self.evidence.read(file)
            matches = locate(symbol, [path]) if raw is not None and symbol else []
            if symbol and not matches:
                self.md(f"Không tìm thấy `{symbol}`; đã tìm AST trong `{file}`.")
            if matches:
                match = matches[0]
                start, end, qualified = match["start"], match["end"], match["symbol"]
            else:
                start, end, qualified = (1, len(raw.decode('utf-8-sig').splitlines()), "toàn file") if raw else (None, None, "Không tìm thấy")
            tests = related_tests(self.root, Path(file).stem, symbol) if path.suffix == ".py" else []
            row = {"Task": task, "Thành phần": spec[0], "File": file, "Dòng bắt đầu": start,
                   "Dòng kết thúc": end, "Hàm/Lớp": qualified,
                   "Commit gần nhất (hash, ngày)": last_commit(path, self.root),
                   "Test liên quan": "; ".join(tests) or "Không có test riêng được tìm thấy; xem script/tài liệu xác minh",
                   "run_id/artifact": (spec[3]+" · " if spec[3] else "")+spec[8]}
            rows.append(row)
            if row not in self.code_rows:
                self.code_rows.append(row)
        # Full AST test names are exported; a compact actual subset keeps notebook readable.
        shown = pd.DataFrame(rows)
        shown["Test liên quan"] = shown["Test liên quan"].map(lambda s: "; ".join(s.split("; ")[:3]))
        self.table(shown, "AST + git log -1; đầy đủ ở docs/notebook_code_map.md", limit=8)
        self.md("Test liên quan tìm theo symbol hoặc module rồi xác nhận tên bằng AST; đây không phải call graph hay lời khẳng định vừa chạy toàn bộ test cũ.")
        if excerpt and rows:
            row = rows[0]
            if row["Dòng bắt đầu"] is not None:
                self.md(f"Đoạn mã chính `{row['File']}` L{row['Dòng bắt đầu']}–L{row['Dòng kết thúc']}; tối đa60 dòng:")
                show_code(self.root/row["File"], row["Dòng bắt đầu"], row["Dòng kết thúc"])

    def overview(self):
        rows = []
        for task, s in TASKS.items():
            links = f"[Issue #{s[1]}]({REPO_URL}/issues/{s[1]})"
            links += f" / [PR #{s[2]}]({REPO_URL}/pull/{s[2]}) đã merge" if s[2] else " / PR riêng: chưa có bằng chứng"
            rows.append({"Task": task, "Mục tiêu": s[0], "Trạng thái": "Có nguồn/minh chứng; xem giới hạn từng bước",
                         "Issue/PR": links, "run_id chính": s[3] or "không có model run", "Artifact chính": s[8],
                         "File mã chính": s[4], "Test": "; ".join(related_tests(self.root, Path(s[4]).stem, s[5])[:2]) or "script/tài liệu"})
        self.table(pd.DataFrame(rows), "Source và GitHub đã đối chiếu khi NB01 bắt đầu", limit=15)
        self.md("Đường dẫn trong notebook tính từ thư mục đồ án có README/pyproject.toml. File code **triển khai** phương pháp; "
                "config **quy định** cách chạy; artifact **ghi nhận** lần đã chạy. File hiện có có thể là file kế thừa/cập nhật, "
                "không tự nhận tất cả được tạo mới ở task đó. Hình có path/run ID ngay dưới; SHA/bytes trong phụ lục.")

    def task(self, task):
        s = TASKS[task]
        self.md(f"### a. Mục tiêu và câu hỏi\n\n{s[6]}\n\n### b. Quyết định và lý do\n\n{s[7]}\n\n"
                "File/trang bài giảng và rubric chính thức: [CẦN BỔ SUNG]. Tên chủ đề chỉ là mapping, không trích nội dung chưa có.\n\n"
                "### c. Vị trí mã nguồn và đoạn triển khai")
        self.code_map(task)
        self.md("### d. Bằng chứng từ file đã có")
        roles = [{"File": p, "Vai trò trong task": role, "Ý nghĩa/quan hệ đầu vào–đầu ra": meaning,
                  "Hiện có": self.evidence.path(p).is_file()} for p, role, meaning in OUTPUT_ROLES[task]]
        self.table(pd.DataFrame(roles), "Mapping NB01; path được kiểm hiện có, không nhận mọi file là tạo mới ở task")
        observations = self.task_evidence(task)
        self.md("### e. Nhận xét từ bằng chứng ngay trên\n\n"+observations+
                "\n\n### f. Kết luận và hạn chế\n\n"+s[9])

    def task_evidence(self, task):
        e = self.evidence
        if task == "T01":
            names = ("src", "scripts", "notebooks", "configs", "tests", "data", "artifacts", "reports", "docs", "app")
            display(pd.DataFrame({"Thư mục": names, "Hiện có": [(self.root/n).is_dir() for n in names]}))
            self.doc("docs/t01_environment_verification.md", 42)
            cfg = e.json("configs/default.json")
            self.md("Config hiện tại (khác snapshot lịch sử nếu có cập nhật): `"+json.dumps({k: cfg.get(k) for k in ("seed", "horizon_hours", "split")}, ensure_ascii=False)+"`.")
            self.doc("pyproject.toml", 30)
            self.doc(".gitignore", 32)
            return "Bảng tồn tại cho biết cấu trúc hiện tại. Báo cáo T01 là kết quả kiểm trước đây; các phiên bản runtime in ở đầu là hiện tại. Không coi tồn tại thư mục là chứng minh cài được trên mọi máy sạch."
        if task == "T02":
            self.doc("docs/problem_definition.md", 56)
            self.doc("docs/experiment_plan.md", 35)
            return "Đặc tả nêu input đến t/target t+1 và RQ; split dùng target timestamp. Các văn bản là đầu ra thiết kế, không phải một bảng metric đã chạy."
        if task == "T03":
            manifest, audit = e.json("reports/data_manifest.json"), e.json("reports/raw_audit_full.json")
            self.table(pd.DataFrame([{k: manifest.get(k) for k in ("dataset_id", "name", "source_url", "download_url", "license", "doi", "downloaded_at")}]), "reports/data_manifest.json")
            self.table(pd.DataFrame([{k: f.get(k) for k in ("file", "rows", "timestamp_min", "timestamp_max", "invalid_timestamps", "duplicate_timestamps", "hourly_gap_transitions", "sha256")} for f in audit.get("files", [])]), "reports/raw_audit_full.json", limit=12)
            self.table(pd.DataFrame([{"archive": k, **manifest.get(k, {})} for k in ("archive", "prsa_archive")]), "reports/data_manifest.json")
            self.doc("docs/data_dictionary.md", 29)
            return f"Audit đã lưu ghi {audit.get('observed_rows', 'chưa có')} dòng/{audit.get('observed_stations', 'chưa có')} trạm. Checksum là dấu vết nội dung gốc; NB01 không đọc lại raw để tái xác minh checksum này."
        if task == "T04":
            audit = e.json("reports/quality_full/summary.json")
            keys = ("input_files", "parsed_rows", "output_rows", "error_count", "warning_count", "duplicate_policy", "imputed", "outlier_removal", "no_column_in_features")
            self.table(pd.DataFrame([{k: audit.get(k) for k in keys}]), "reports/quality_full/summary.json")
            self.table(pd.DataFrame(list(audit.get("missing", {}).items()), columns=["Biến", "Missing count"]), "reports/quality_full/summary.json", limit=20)
            self.csv("reports/quality_full/stations.csv", limit=12)
            issues = e.csv("reports/quality_full/issues.csv")
            if not issues.empty:
                self.table(issues.head(6), "reports/quality_full/issues.csv")
                display(issues.groupby(list(issues.columns[:1]), dropna=False).size().rename("count").to_frame().head(8))
            return f"Trước/sau {audit.get('parsed_rows')}/{audit.get('output_rows')} dòng; {audit.get('error_count')} lỗi và {audit.get('warning_count')} cảnh báo. Các số missing không được coi là đã impute; đỉnh hợp lệ được giữ."
        if task == "T04-LOG":
            log = e.csv("experiments/experiment_log.csv")
            if log.empty:
                return "Chưa có ledger để kết luận."
            log["stage"] = log["parameters"].fillna("{}").map(lambda x: json.loads(x).get("stage", "validation"))
            self.table(log.groupby(["task_id", "mode", "stage", "status"], dropna=False).size().rename("hồ sơ").reset_index(), "experiments/experiment_log.csv", limit=30)
            row = log.loc[log.run_id.eq(P)].iloc[0]
            self.table(pd.DataFrame([{k: row.get(k) for k in ("run_id", "config_path", "metadata_path", "metrics_path", "notes_path")}]), "experiments/experiment_log.csv", run_id=P)
            return f"Ledger hiện có {len(log)} hồ sơ; trước T13 là {len(log.loc[log.task_id.ne('T13')])}, thêm {sum(log.task_id.eq('T13'))} hồ sơ T13. Có {(log.status != 'completed').sum()} hồ sơ không completed trong snapshot này; không bịa failed run khi chưa có. Logger hỗ trợ failure được kiểm bằng fixture."
        if task == "T05":
            frame = self.csv("reports/splits_full/split_summary.csv", limit=6)
            self.csv("reports/splits_full/exclusion_summary.csv", limit=15)
            self.fold_table()
            # Simple timeline rebuilt from aggregate timestamps, not observations.
            if not frame.empty:
                import matplotlib.pyplot as plt
                import matplotlib.dates as mdates
                fig, ax = plt.subplots(figsize=(10, 2.5))
                primary = frame.loc[frame.cohort.eq("primary")]
                for i, row in enumerate(primary.itertuples()):
                    lo, hi = pd.Timestamp(row.target_timestamp_min), pd.Timestamp(row.target_timestamp_max)
                    ax.plot([lo, hi], [i, i], lw=12, solid_capstyle="butt")
                ax.set_yticks(range(len(primary)), primary.split)
                ax.set_xlabel("Target timestamp (giờ địa phương nguồn)")
                ax.set_title("Timeline temporal split — aggregate audit, không mở mẫu test")
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
                fig.tight_layout(); display(fig); plt.close(fig)
                self.md("Vẽ lại từ `reports/splits_full/split_summary.csv`; trục thời gian, không có đơn vị nồng độ; không phải hình gốc/model run.")
            return "Operational giữ input thiếu PM2.5(t) để kiểm fallback; primary yêu cầu t có sẵn. Split theo target nên origin ở giờ ngay trước biên thuộc tập kế tiếp. Ba fold hiển thị là artifact T11 và có purge, không random K-fold."
        if task == "T06":
            numeric = self.csv("reports/eda_train/numeric_summary.csv", columns=["column", "unit", "rows", "missing", "missing_pct", "mean", "std", "min", "q50", "max"], limit=13)
            self.csv("reports/eda_train/schema.csv", limit=22)
            self.csv("reports/eda_train/categorical_counts.csv", limit=8)
            self.csv("reports/eda_train/correlation_pairs.csv", limit=8)
            self.csv("reports/eda_train/sample_gaps.csv", limit=12)
            self.csv("reports/eda_train/seasonal.csv", limit=12)
            ac = e.csv("reports/eda_train/autocorrelation.csv")
            if not ac.empty:
                self.table(ac.groupby("lag_hours").agg(station_mean_r=("pearson_r", "mean"), pairs=("pairs", "sum")).reset_index(), "reports/eda_train/autocorrelation.csv", limit=10)
            for file, caption in (("01_missing", "Missing theo biến"), ("02_distributions", "Phân phối đơn biến"),
                                  ("03_tails", "Đuôi phân phối/đỉnh cao"), ("04_correlations", "Tương quan train"),
                                  ("05_relationships", "PM2.5 và khí tượng/chất ô nhiễm"), ("06_stations", "Khác biệt trạm"),
                                  ("07_calendar", "Giờ/tháng/mùa"), ("08_timeline", "Chuỗi thời gian và khoảng trống"),
                                  ("09_autocorrelation", "Tự tương quan đúng timestamp")):
                self.image("reports/figures/eda_train/"+file+".png", caption)
            if numeric.empty:
                return "Chưa có thống kê train."
            row = numeric.loc[numeric.column.eq("PM2.5")].iloc[0]
            return f"PM2.5 train: missing {row['missing_pct']:.4f}%, max {row['max']:g} µg/m³. Giữ đuôi cao; impute học train và chỉ báo missing; so A/B để kiểm giả thuyết lag. Tương quan/chu kỳ chỉ gợi ý dự báo, không giải thích nhân quả."
        if task == "T07":
            registry = self.csv("reports/features_full/feature_registry.csv", limit=33)
            missing = e.csv("reports/features_full/missing_summary.csv")
            if not missing.empty:
                self.table(missing.sort_values("missing_pct", ascending=False), "reports/features_full/missing_summary.csv", limit=12)
            return f"Registry có {len(registry)} tên feature; bảng missing lớn nhất cho biết chi phí lịch sử/warm-up. Reindex phục vụ căn giờ, không sinh thêm mẫu forecast từ giờ không quan sát. Tính bất biến khi đổi tương lai được kiểm trong test T07 (xem code map), không chạy lại raw ở NB01."
        if task == "T08":
            cfg = e.json("configs/preprocessing.json")
            self.md("Config preprocessing hiện tại:\n```json\n"+json.dumps(cfg, ensure_ascii=False, indent=2)+"\n```")
            self.md("Sơ đồ: **FeatureSchema → ColumnTransformer(numeric median + indicators; categorical missing + OHE) → Ridge(scale numeric) / RF(no scaling)**. Mọi fit thuộc train của run/fold; identity giữ dự báo âm theo config.")
            self.doc("docs/preprocessing.md", 35)
            return "Config/pipeline tách cách học preprocessing khỏi inference. Output T08 là factories và kiểm fixture, không model full; Issue #35 sửa guard chuỗi rỗng, giữ missing cho imputer đã fit."
        if task == "T09":
            metrics = e.json(f"artifacts/experiments/{P}/metrics.json")
            self.table(pd.DataFrame([{"cohort": k, **v} for k, v in metrics.items() if k.startswith("validation") and isinstance(v, dict)]), f"artifacts/experiments/{P}/metrics.json", run_id=P)
            self.csv(f"reports/baseline/full/{P}/fallback.csv", run_id=P)
            self.image(f"reports/figures/baseline/full_{P}_validation_errors.png", "Sai số persistence validation", P)
            return "Primary và operational có tiêu chí mẫu khác nhau; tỷ lệ fallback chỉ so trong đúng cohort. Từ baseline này mới đo phần trăm MAE giảm; không buộc mô hình phức tạp phải thắng."
        if task == "T10":
            frame = self.csv("reports/initial_models/comparison.csv", limit=3, run_id=P+"; "+R+"; "+F)
            self.image("reports/figures/initial_models/comparison.png", "Train/validation và chi phí mốc ban đầu", R+"; "+F)
            self.run_parameters([R, F])
            if frame.empty:
                return "Chưa có bảng so sánh."
            ridge = frame.loc[frame.model.eq("ridge")].iloc[0]
            rf = frame.loc[frame.model.eq("random_forest")].iloc[0]
            return f"Ridge validation MAE {ridge.validation_MAE:.6f}, RF {rf.validation_MAE:.6f}; RF fit {rf.fit_seconds:.2f}s so Ridge {ridge.fit_seconds:.2f}s. Ridge có {int(ridge.negative_validation_predictions)} dự báo âm theo policy identity; không clipping sau khi thấy kết quả."
        if task == "T11":
            frame = self.csv("reports/tuning/candidates.csv", run_id=TUNE)
            self.csv("reports/tuning/fold_metrics.csv", limit=12, run_id=TUNE)
            before = self.csv("reports/tuning/before_after.csv", run_id=RA)
            self.image("reports/figures/tuning/comparison.png", "Tuning Ridge — pooled CV và validation", TUNE+"; "+RA)
            return "Chọn alpha từ pooled CV thấp nhất, không lấy trung bình đơn giản fold. Validation sau refit không cải thiện MAE so alpha1 T10 (đối chiếu số ở phần kiểm chứng). Bảng đầy đủ giữ cả alpha kém; không có CV RF để kết luận độ ổn định RF."
        if task == "T12":
            frame = self.csv("reports/ablation/comparison.csv", limit=5, run_id=RA+"; "+RB+"; "+RC+"; "+F)
            selected = e.csv("reports/ablation/selected_features.csv")
            if not selected.empty:
                self.table(selected.loc[selected.run_id.eq(RC)], "reports/ablation/selected_features.csv", limit=33, run_id=RC)
            frozen = e.json("reports/ablation/frozen_model.json")
            compact = {k: frozen.get(k) for k in ("schema_version", "status", "locked_at", "selected_run_id", "selected_variant", "selection", "features", "preprocessing", "model", "postprocessing", "refit_policy", "test_locked", "test_evaluated")}
            self.md("Frozen snapshot T12 — các trường chính, giữ nội dung lịch sử trước T13:\n```json\n"+json.dumps(compact, ensure_ascii=False, indent=2)+"\n```")
            self.image("reports/figures/ablation/comparison.png", "A/B/C — cố định tham số Ridge", RA+"; "+RB+"; "+RC)
            return "A→B→C giảm MAE Ridge và giảm số chiều ở C, nhưng RMSE C cao hơn B; RF A vẫn có MAE validation tốt nhất trong các phương án đã chạy. Vì vậy lock vẫn RF A; không lấy ranking test để đổi phương án."
        if task == "T13":
            comp = self.csv("reports/final_evaluation/comparison.csv", limit=3, run_id=FINAL)
            grouped = e.csv("reports/final_evaluation/grouped_metrics.csv")
            if not grouped.empty:
                rf = grouped.loc[grouped.model.eq("random_forest")]
                self.table(rf.loc[rf.group.eq("station")].sort_values("MAE", ascending=False), "reports/final_evaluation/grouped_metrics.csv", limit=12, run_id=RF_FINAL)
                self.table(rf.loc[~rf.group.eq("station")], "reports/final_evaluation/grouped_metrics.csv", limit=24, run_id=RF_FINAL)
            self.csv("reports/final_evaluation/generalization_gap.csv", limit=14, run_id=FINAL)
            self.csv("reports/final_evaluation/cv_summary.csv", limit=2, run_id=FINAL)
            self.csv("reports/final_evaluation/ridge_coefficients.csv", limit=6, run_id="51975d2c66ff4263b83ace6962f3d3f7")
            importance = e.csv("reports/final_evaluation/rf_permutation_summary.csv")
            if not importance.empty:
                self.table(importance.sort_values("mean", ascending=False), "reports/final_evaluation/rf_permutation_summary.csv", limit=16, run_id=RF_FINAL)
            self.run_parameters([FINAL])
            for file, caption in (("actual_predicted", "Actual–predicted T13"), ("residuals", "Residual T13"),
                                  ("timeline", "Đoạn chuỗi thời gian T13"), ("high_pollution_episode", "Đợt ô nhiễm cao T13"),
                                  ("group_errors", "Sai số theo nhóm T13"), ("ridge_coefficients", "Hệ số Ridge T13"),
                                  ("rf_permutation", "Permutation importance RF T13")):
                self.image("reports/figures/final_evaluation/"+file+".png", caption, FINAL)
            self.doc("docs/results_discussion.md", 25)
            if comp.empty:
                return "Thiếu artifact T13."
            rf = comp.loc[comp.model.eq("random_forest")].iloc[0]
            details = []
            if not grouped.empty:
                rf_groups = grouped.loc[grouped.model.eq("random_forest")]
                for group in ("station", "season", "concentration", "rapid_change", "episode_id"):
                    subset = rf_groups.loc[rf_groups.group.eq(group)]
                    if not subset.empty:
                        worst = subset.loc[subset.MAE.idxmax()]
                        details.append(f"{group}: nhóm MAE cao nhất `{worst['value']}`={worst.MAE:.3f} (N={int(worst.n_scored)})")
            return f"RF test MAE {rf.MAE:.6f}, giảm {rf.mae_reduction_vs_persistence_pct:.4f}% so persistence trên {int(rf.n_scored)} IDs. "+"; ".join(details)+". Kết quả này đo tổng quát hóa sau khóa; không chọn lại. Hệ số/importance bị ảnh hưởng tương quan; lý do đỉnh khó là giả thuyết, không suy nhân quả."
        if task == "T14":
            qa = e.json("reports/demo/inference_verification.json")
            self.table(pd.DataFrame([{k: qa.get(k) for k in ("model_run_id", "requests_checked", "saved_T13_predictions_matched", "max_absolute_difference", "new_training", "target_read_after_predict")}]), "reports/demo/inference_verification.json", run_id=RF_FINAL)
            self.table(pd.DataFrame(qa.get("rows", [])[:1]), "reports/demo/inference_verification.json#rows[0]", run_id=RF_FINAL)
            self.image("reports/demo/screenshots/02_forecast.png", "Demo đã chụp tại origin riêng trên UI (khác ví dụ QA rows[0] ở trên)", RF_FINAL)
            self.doc("docs/demo_video_storyboard.md", 18)
            return f"QA ghi {qa.get('saved_T13_predictions_matched')}/{qa.get('requests_checked')} ví dụ khớp, max|diff|={qa.get('max_absolute_difference')}; đây là kiểm đã lưu, không inference mới NB01. Actual đọc sau predict. Video mới có kịch bản, nhóm tự quay."
        raise KeyError(task)

    def fold_table(self):
        path = f"artifacts/experiments/{TUNE}/artifacts/data/folds.json"
        folds = self.evidence.json(path)
        rows = [{"fold": f["fold_id"], "fit N": f["fit"]["samples"], "eval N": f["evaluation"]["samples"],
                 "purge N": f["purged"]["samples"], "fit cuối": f["fit"]["last_target"],
                 "eval đầu": f["evaluation"]["first_target"], "eval cuối": f["evaluation"]["last_target"],
                 "label availability": f["label_availability"]["status"]} for f in folds] if isinstance(folds, list) else []
        self.table(pd.DataFrame(rows), path+" (đầu ra T11)", run_id=TUNE)

    def run_parameters(self, ids):
        log = self.evidence.csv("experiments/experiment_log.csv")
        if log.empty:
            return
        for rid in ids:
            found = log.loc[log.run_id.eq(rid)]
            if found.empty:
                self.md("Không tìm thấy artifact: experiments/experiment_log.csv#run_id="+rid)
                continue
            params = json.loads(found.iloc[0].parameters)
            keys = ("stage", "model", "actual_model_parameters", "effective_model_parameters", "budget", "feature_set", "design")
            compact = {k: params[k] for k in keys if k in params}
            signature = params.get("signature", {})
            compact["signature_selected_fields"] = {k: v for k, v in signature.items()
                                                     if k in {"model", "effective_model_parameters", "model_parameters", "feature_set", "preprocessing", "seed", "mode"}}
            self.md("Config các trường chính của run `"+rid+"` (đầy đủ ở ledger/config riêng):\n```json\n"+json.dumps(compact, ensure_ascii=False, indent=2)+"\n```")

    def synthesis(self):
        self.md("## Tổng hợp RQ1–RQ3 — T13 artifact, chỉ đọc\n\nDevelopment và test refit là hai lần fit khác nhau; giữ run ID riêng, không lấy chênh lệch hai cột như một phép thử paired cùng model.")
        self.csv("reports/initial_models/comparison.csv", limit=3, run_id=P+"; "+R+"; "+F)
        test = self.csv("reports/final_evaluation/comparison.csv", limit=3, run_id=FINAL)
        self.csv("reports/ablation/comparison.csv", limit=5, run_id=RA+"; "+RB+"; "+RC)
        self.md("**RQ1:** RF A được chọn bằng validation, test MAE giảm so persistence như bảng T13; Ridge kém MAE nhưng RMSE tốt hơn baseline. "
                "Bằng chứng giới hạn ở kỳ held-out và trạm đã quan sát, không bảo đảm mọi đợt tương lai.\n\n"
                "**RQ2:** Lag/rolling và selection giảm MAE Ridge A→B→C trên development; C không giảm RMSE so B. Không có B/C test, không tuyên bố tốt nhất tổng quát. "
                "Hệ số/importance chỉ liên hệ dự báo, không nhân quả.\n\n"
                "**RQ3:** Bảng theo trạm/mùa/nồng độ và đợt cao T13 cho biết sai số không đồng đều; đỉnh/thay đổi nhanh khó hơn là diễn giải/giả thuyết cần kiểm thêm. "
                "Không tính R² cho nhóm quá nhỏ hoặc không biến thiên. Train khoảng hai năm và CV sớm chưa bao phủ mọi mùa đánh giá; RF không có fold/std CV.")
        adverse = pd.DataFrame([
            ["T10 Ridge A", R, "MAE validation kém persistence; có dự báo âm", "reports/initial_models/comparison.csv"],
            ["T11 alpha0.1", RA, "CV chọn tốt hơn nhưng validation MAE không cải thiện alpha1", "reports/tuning/before_after.csv"],
            ["T12 C so B", RC, "MAE giảm, RMSE tăng; selection không cải thiện mọi metric", "reports/ablation/comparison.csv"],
            ["T13 Ridge", "51975d2c66ff4263b83ace6962f3d3f7", "MAE test kém persistence; policy identity giữ dự báo âm", "reports/final_evaluation/comparison.csv"],
            ["Issue #35", "không có model run mới", "Guard categorical thiếu lỗi trên pandas3; sửa PR37, không refit", "docs/changelog_issue35.md"],
        ], columns=["Nỗ lực/kết quả bất lợi", "run_id", "Nhận xét", "Nguồn"])
        self.table(adverse, "Các file nguồn ở cột cuối", limit=5)
        self.md("### Issue #35: phát hiện, tác động và trạng thái thật")
        self.doc("docs/changelog_issue35.md", 64)
        self.md("Issue **#35** là số Issue, PR sửa thực tế **#37** đã merge (không tự gọi là PR35 trên GitHub). "
                "Source guard đổi nên fingerprint nguồn khác; snapshot/config/model T13 giữ nguyên. NB01 không load lại weights hoặc chạy lại đánh giá test.\n\n"
                "**Hạn chế chung:** thiếu bài giảng/rubric gốc, thông tin nhóm và % đóng góp, video thật; model bundle lớn cần hướng dẫn tải/kiểm checksum; "
                "kết quả theo thời gian có dịch chuyển phân phối, chưa có đánh giá độc lập ngoài UCI501.")

    def crosscheck(self):
        """Cheap saved-prediction reconciliation, including existing T13 artifacts only."""
        from beijing_air.experiment_summary import Reader, build_summary
        reader = Reader(self.root)
        try:
            rows, evidence = build_summary(reader, include_plans=False)
        except (FileNotFoundError, ValueError) as exc:
            self.md("KHÁC/lỗi kiểm chứng: "+safe_text(str(exc))+". Không sửa artifact cũ.")
            self.checks = [{"check": "saved predictions reconciliation", "status": "KHÁC", "observed": str(exc), "expected": "matching artifacts"}]
            return
        self.checks = list(evidence["checks"])
        self.evidence.sources.update(reader.sources)
        self.evidence.missing.extend(w.replace("Chưa có: ", "Không tìm thấy artifact: ") for w in reader.warnings if w not in self.evidence.missing)
        initial = self.evidence.csv("reports/initial_models/comparison.csv")
        splits = self.evidence.csv("reports/splits_full/split_summary.csv")
        ablation = self.evidence.csv("reports/ablation/comparison.csv")
        extras = []
        for model, key, expected in (("ridge", "train_MAE", 11.286320), ("random_forest", "train_MAE", 9.837287),
                                     ("random_forest", "train_RMSE", 16.664335)):
            selected = initial.loc[initial.model.eq(model)] if "model" in initial else pd.DataFrame()
            extras.append(("T10 "+model+" "+key, selected.iloc[0][key] if not selected.empty else None, expected))
        for cohort, counts in (("primary", (204865, 102479, 101836)), ("operational", (205977, 103287, 102753))):
            for partition, count in zip(("train", "validation", "test"), counts):
                found = splits.loc[splits.cohort.eq(cohort) & splits.split.eq(partition)] if not splits.empty else pd.DataFrame()
                extras.append((f"T05 {cohort}/{partition} N", found.iloc[0].samples if not found.empty else None, count))
        for rid, dimensions, rmse in ((RA, 65, 18.907198), (RB, 91, 18.467071), (RC, 24, 18.501063)):
            found = ablation.loc[ablation.run_id.eq(rid)] if not ablation.empty else pd.DataFrame()
            for key, expected in (("model_dimensions", dimensions), ("RMSE", rmse)):
                extras.append(("T12 "+rid+" "+key, found.iloc[0][key] if not found.empty else None, expected))
        for name, value, expected in extras:
            observed = float(value) if value is not None else None
            self.checks.append({"check": name, "run_id": "xem tên/nguồn bảng", "observed": observed, "expected": expected,
                                "status": "OK" if observed is not None and abs(observed-expected) <= 1e-6 else "KHÁC"})
        checks = pd.DataFrame(self.checks)
        historical = checks.loc[checks.check.str.startswith(("historical", "T05", "T10", "T12"))]
        self.table(historical, "Số đối chiếu người dùng (1e-6), giá trị gốc không sửa", limit=40, run_id="xem từng hàng")
        self.table(checks.loc[~checks.index.isin(historical.index)].head(12), "Ví dụ kiểm metric/OOF/IDs từ saved predictions vs metrics.json", run_id="xem từng hàng")
        self.table(checks.groupby("status", dropna=False).size().rename("số kiểm chứng").reset_index(), "Tổng hợp tất cả kiểm chứng; đầy đủ journey_checks.csv")
        if checks.status.ne("OK").any():
            self.table(checks.loc[checks.status.ne("OK")], "Tất cả chỗ KHÁC", limit=40, run_id="xem từng hàng")
        self.md(f"**{sum(checks.status.eq('OK'))}/{len(checks)} OK; {sum(checks.status.ne('OK'))} KHÁC.** "
                "Giữ nguyên artifact/log dù KHÁC. Saved predictions được kiểm checksum/ID và tính lại metric; pooled từ OOF theo tổng số mẫu, "
                "không thay bằng mean fold. Test chỉ những child T13 đã chấm, không đọc sample test thô. ")
        self.run_rows = evidence["runs"]

    def appendix(self):
        self.md("## Phụ lục kiểm kê và tái lập\n\nMỗi SHA bên dưới được tính từ **file minh chứng đã đọc**; "
                "checksum raw/model nằm trong manifest lịch sử là checksum đã ghi, NB01 không đọc dữ liệu/weights để xác minh lại. "
                "Không thống kê số model bằng cách đếm hồ sơ ledger.")
        inventory = pd.DataFrame([{"path": k, **v} for k, v in sorted(self.evidence.sources.items())])
        self.table(inventory, "Các file thực sự đọc trong NB01", limit=18)
        self.md(f"Có {len(inventory)} file trong inventory đầy đủ: `reports/notebook/journey_inventory.csv`. "
                "Bảng AST đầy đủ: `docs/notebook_code_map.md`. Kết quả đối chiếu: `reports/notebook/journey_checks.csv`.")
        self.md("### Artifact không tìm thấy\n\n"+("\n".join("- "+m for m in self.evidence.missing) or "Không có artifact bắt buộc bị thiếu trong lần chạy này.")+
                "\n\n### Chỗ KHÁC số báo cáo/log\n\n"+("\n".join("- "+str(c['check']) for c in self.checks if c['status'] != 'OK') or "Không có chỗ KHÁC trong các kiểm chứng đã thực hiện.")+
                "\n\n### Cách chạy lại\n\nTừ thư mục đồ án, dùng môi trường đã cài `pip install -e .`; "
                "tạo notebook bằng `python scripts/build_project_journey.py`, thực thi/xuất bằng "
                "`python scripts/build_project_journey.py --execute`. CLI gọi `jupyter nbconvert --execute` trong kernel mới. "
                "Có thể dùng `python -m nbconvert --to notebook --execute --inplace notebooks/PM25_Project_Journey_T01_T14.ipynb` "
                "nếu kernel python3 đã trỏ đúng môi trường. Không cần dataset/model để đọc notebook/HTML đã có output; "
                "chạy lại cần các CSV/JSON/PNG/predictions đã commit và package cài đúng. Thiếu file sẽ ghi đường dẫn đã tìm, không dựng số.\n\n"
                "### AI disclosure và nhóm\n\nCodex hỗ trợ tạo helper AST, trình bày/chú giải, đối chiếu metric và kiểm thực thi; "
                "thành viên nhận Issue #42 hoanglecodingmachine phải rà soát/hiểu trước merge. Họ tên/MSSV/đóng góp % và người rà soát: "
                "[CẦN BỔ SUNG]. Xem `docs/ai_disclosure.md`, `docs/team_contributions.md`. Không tự gán đóng góp học thuật theo Git identity.")

    def export(self):
        """Only new NB01 evidence products are written, never an experiment artifact."""
        directory = self.root/"reports/notebook"
        directory.mkdir(parents=True, exist_ok=True)
        inventory = pd.DataFrame([{"path": k, **v} for k, v in sorted(self.evidence.sources.items())])
        inventory.to_csv(directory/"journey_inventory.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(self.checks).to_csv(directory/"journey_checks.csv", index=False, encoding="utf-8-sig")
        columns = ["Task", "Thành phần", "File", "Dòng bắt đầu", "Dòng kết thúc", "Hàm/Lớp", "Commit gần nhất (hash, ngày)", "Test liên quan", "run_id/artifact"]
        def cell(value):
            return str(value).replace("|", "\\|").replace("\n", " ")
        text = "# Bản đồ mã nguồn notebook hành trình T01–T14\n\n"
        text += "Sinh từ cell cuối `notebooks/"+TITLE+".ipynb`, bằng AST (không import module mô hình), git log -1 và AST tests.\n\n"
        text += f"Source anchor: `{git(self.root, 'rev-parse', 'HEAD')}`; sinh `{self.started}`. "
        text += "Dòng là inclusive; test match theo symbol/module, không là call graph hoặc xác nhận vừa chạy. Nhận xét trạng thái theo snapshot NB01.\n\n"
        text += "| "+" | ".join(columns)+" |\n|"+"|".join("---" for _ in columns)+"|\n"
        for row in self.code_rows:
            text += "| "+" | ".join(cell(row.get(k, "")) for k in columns)+" |\n"
        text += "\nĐọc cùng notebook/HTML: từng task có mục tiêu, quyết định, trích mã, bằng chứng, nhận xét và hạn chế. "
        text += "T13/T14 chỉ đọc artifact đã có. File nguồn có thể đã được cập nhật bởi task sau; commit gần nhất phản ánh file hiện tại.\n"
        (self.root/"docs/notebook_code_map.md").write_text(text, encoding="utf-8")
        report = {"task_id": "NB01", "artifact_type": "read_only_evidence_not_model_experiment",
                  "generated_at": self.started, "source_commit": git(self.root, "rev-parse", "HEAD"),
                  "tasks": list(TASKS), "code_map_rows": len(self.code_rows), "checks": len(self.checks),
                  "different": [c for c in self.checks if c["status"] != "OK"],
                  "missing": list(dict.fromkeys(self.evidence.missing)), "sources": len(self.evidence.sources),
                  "new_model_runs": 0, "raw_samples_read": False, "weights_loaded": False}
        (directory/"journey_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        self.md(f"Đã sinh code map {len(self.code_rows)} dòng AST và inventory/checks NB01; không ghi experiment_log.")
        return report
