"""T14 read-only historical inference. No fitting, logger writes, or test selection."""

from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform
import sqlite3

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline

from beijing_air.data import MEASUREMENTS, sha256
from beijing_air.eda import project_path, read_json
from beijing_air.features import feature_registry, features_for_prediction
from beijing_air.preprocessing import FeatureSchema


class DemoError(ValueError):
    """A problem with actionable feedback for a demo user."""


@dataclass(frozen=True)
class DemoModel:
    pipeline: object
    config: dict
    handoff: dict
    stations: tuple
    feature_names: tuple
    metadata: dict


@dataclass(frozen=True)
class Forecast:
    station: str
    origin: pd.Timestamp
    target: pd.Timestamp
    sample_id: str
    predicted_pm25: float
    current_pm25: float | None
    missing_inputs: tuple
    history: pd.DataFrame
    features: pd.DataFrame
    model_run_id: str


def check_runtime(metadata):
    expected = metadata["environment"]
    if platform.python_version().split(".")[:2] != expected["python"].split(".")[:2]:
        raise DemoError(f"Model yêu cầu Python {expected['python']}; hãy dùng môi trường trong hướng dẫn demo.")
    for name in ("scikit-learn", "numpy", "pandas", "joblib"):
        actual = version(name)
        wanted = expected["packages"][name]
        if actual != wanted:
            raise DemoError(f"Phiên bản {name} đang là {actual}; model đã lưu dùng {wanted}. Xem docs/demo.md.")


def model_fingerprint(root):
    """Small manifests + weight identity invalidate Streamlit's resource cache."""
    root = Path(root).resolve()
    try:
        handoff_path = root / "reports/final_evaluation/final_model.json"
        handoff = read_json(handoff_path)
        paths = [handoff_path, project_path(root, handoff["weights"]["path"]),
                 project_path(root, handoff["metadata_path"]), root / "configs/default.json",
                 root / "reports/ablation/frozen_model.json"]
        return hashlib.sha256("|".join(sha256(p) for p in paths).encode()).hexdigest()
    except FileNotFoundError as error:
        raise DemoError("Chưa có model hoặc metadata T13. Khôi phục gói artifact theo docs/demo.md.") from error


def load_demo_model(root):
    """Load only the trusted, checksummed validation-selected T13 pipeline."""
    root = Path(root).resolve()
    try:
        handoff = read_json(root / "reports/final_evaluation/final_model.json")
        meta = read_json(project_path(root, handoff["metadata_path"]))
        run_dir = root / "artifacts/experiments" / handoff["final_run_id"]
        run_cfg = read_json(run_dir / "config.json")
        frozen = read_json(root / "reports/ablation/frozen_model.json")
        design = read_json(root / "configs/final_evaluation.json")
        config = read_json(root / "configs/default.json")
        weights = project_path(root, handoff["weights"]["path"])
        if not weights.is_relative_to(run_dir):
            raise DemoError("Đường dẫn model không thuộc run đã bàn giao.")
        if sha256(weights) != handoff["weights"]["sha256"] or weights.stat().st_size != handoff["weights"]["bytes"]:
            raise DemoError("Checksum model không khớp T13. Khôi phục đúng gói artifact, không thay model khác.")
        if (handoff["selected_by"] != "development_validation_MAE" or handoff["test_used_for_selection"]
                or handoff["selected_model"] != "random_forest" or handoff["selected_feature_set"] != "A"
                or handoff["fit_partition"] != "train+validation primary"
                or handoff["fit_samples"] != run_cfg["sample_counts"]["fit"]
                or handoff["fit_samples"] != run_cfg["data"]["preflight"]["refit_rows"]
                or handoff["selected_development_run_id"] != frozen["selected_run_id"]
                or handoff["final_run_id"] != meta["run_id"] or meta["status"] != "completed"
                or run_cfg["task_id"] != "T13" or run_cfg["model"] != "random_forest"
                or run_cfg["feature_set"] != "A" or run_cfg["reference_run_id"] != frozen["selected_run_id"]):
            raise DemoError("Metadata không xác nhận đúng RF A đã chọn bằng validation và refit T13.")
        if (sha256(root / "configs/default.json") != design["files_sha256"]["configs/default.json"]
                or config["features"] != frozen["features"]["definitions"]
                or run_cfg["preprocessing"] != frozen["preprocessing"]
                or handoff["parameters"] != frozen["model"]["parameters"]
                or run_cfg["parameters"]["locked_parameters"] != handoff["parameters"]
                or handoff["postprocessing"] != "identity"):
            raise DemoError("Config/schema/params đã khác recipe nghiên cứu; demo dừng để kiểm tra.")
        check_runtime(meta)  # Check versions before deserializing the trusted local file.
        pipeline = joblib.load(weights)
        registry = feature_registry(config)
        names = tuple(registry.loc[registry.feature_sets.str.split(";").map(lambda x: "A" in x), "feature_name"])
        if (not isinstance(pipeline, Pipeline) or list(pipeline.named_steps) != ["preprocess", "model"]
                or not isinstance(pipeline.named_steps["model"], RandomForestRegressor)):
            raise DemoError("File model không chứa đầy đủ pipeline RF nghiên cứu.")
        pre = pipeline.named_steps["preprocess"]
        if (not isinstance(pre.named_steps["schema"], FeatureSchema)
                or tuple(pre.named_steps["schema"].get_feature_names_out()) != names
                or pipeline.named_steps["model"].get_params() != handoff["parameters"]
                or len(pre.get_feature_names_out()) != pipeline.named_steps["model"].n_features_in_):
            raise DemoError("Feature names hoặc cấu trúc pipeline không khớp model đã lưu.")
        summary = read_json(run_dir / "artifacts/model/pipeline_summary.json")
        if list(pre.get_feature_names_out()) != summary["output_feature_names"] or list(names) != summary["input_feature_names"]:
            raise DemoError("Schema model không khớp pipeline summary của run.")
        columns = pre.named_steps["columns"]
        cat_names = list(next(t[2] for t in columns.transformers_ if t[0] == "categorical"))
        vocab = columns.named_transformers_["categorical"].named_steps["one_hot"].categories_
        stations = tuple(str(s) for s in vocab[cat_names.index("station")] if s != "__MISSING__")
        if not stations:
            raise DemoError("Model không có danh sách trạm đã huấn luyện.")
        return DemoModel(pipeline, config, handoff, stations, names, {
            "python": meta["environment"]["python"], "packages": meta["environment"]["packages"],
            "fit_samples": handoff["fit_samples"], "fit_partition": handoff["fit_partition"],
            "first_fit_target": frozen["data"]["train"]["first_target"],
            "last_fit_target": run_cfg["data"]["preflight"]["latest_fit_target"],
            "input_dimensions": len(names), "encoded_dimensions": len(pre.get_feature_names_out()),
            "run_id": handoff["final_run_id"], "feature_set": "A", "selection": handoff["selected_by"]})
    except FileNotFoundError as error:
        raise DemoError("Thiếu model/metadata T13. Xem docs/demo.md để lấy và khôi phục gói artifact.") from error
    except (KeyError, TypeError, AttributeError) as error:
        raise DemoError("Metadata/schema model chưa hợp lệ. Khôi phục đúng artifact T13 theo docs/demo.md.") from error


def valid_origin(value):
    if not isinstance(value, (str, pd.Timestamp)):
        raise DemoError("Giờ t phải là timestamp từ bộ dữ liệu minh họa.")
    try:
        origin = pd.Timestamp(value)
    except (ValueError, TypeError) as error:
        raise DemoError("Không đọc được giờ t.") from error
    if pd.isna(origin) or origin.tzinfo is not None or origin != origin.floor("h"):
        raise DemoError("Giờ t phải tròn giờ, theo timestamp gốc, không gắn múi giờ khác.")
    return origin


class DemoStore:
    """Open one read-only SQLite connection per query; never cache measurements."""

    def __init__(self, path, manifest, *, observer=None):
        self.path = Path(path).resolve()
        self.manifest = manifest
        self.observer = observer

    def emit(self, event):
        if self.observer is not None:
            self.observer(event)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            yield connection
        finally:
            connection.close()

    @classmethod
    def from_project(cls, root):
        root = Path(root).resolve()
        try:
            manifest = read_json(root / "app/resources/demo_manifest.json")
            path = project_path(root, manifest["database"]["path"])
            if sha256(path) != manifest["database"]["sha256"]:
                raise DemoError("Dữ liệu minh họa không khớp checksum; chạy lại bước chuẩn bị theo docs/demo.md.")
            store = cls(path, manifest)
            with store.connect() as connection:
                expected = {"observations":set(["station","timestamp",*MEASUREMENTS,"wd"]), "actuals":{"station","target_timestamp","pm25"}}
                for table, columns in expected.items():
                    actual = {row[1] for row in connection.execute("PRAGMA table_info("+table+")")}
                    if actual != columns:
                        raise DemoError("Schema dữ liệu minh họa không đúng; khôi phục resource T14.")
            return store
        except FileNotFoundError as error:
            raise DemoError("Thiếu dữ liệu minh họa. Xem docs/demo.md để chuẩn bị dữ liệu.") from error

    def origins(self, stations):
        self.emit("origin_index")
        query = "SELECT station,timestamp FROM observations WHERE timestamp>=? AND timestamp<? ORDER BY station,timestamp"
        with self.connect() as connection:
            result = pd.read_sql_query(query, connection, params=[self.manifest["selection"]["start"], self.manifest["selection"]["end"]])
        result = result.loc[result.station.isin(stations)].copy()
        result["timestamp"] = pd.to_datetime(result.timestamp)
        return result

    def past(self, station, origin, *, hours=48):
        self.emit("past_observations")
        columns = ",".join('"'+name+'"' for name in ["station", "timestamp", *MEASUREMENTS, "wd"])
        query = f"SELECT {columns} FROM observations WHERE station=? AND timestamp>=? AND timestamp<=? ORDER BY timestamp"
        with self.connect() as connection:
            result = pd.read_sql_query(query, connection, params=[station, str(origin-pd.Timedelta(hours=hours-1)), str(origin)])
        result["timestamp"] = pd.to_datetime(result.timestamp)
        for name in MEASUREMENTS:
            result[name] = pd.to_numeric(result[name], errors="raise").astype("float64")
        result["station"] = result.station.astype("string")
        result["wd"] = result.wd.astype("string")
        if result.empty or not result.timestamp.eq(origin).any():
            raise DemoError("Không có quan sát đúng trạm và giờ t đã chọn; không tạo mẫu giả.")
        if not result.timestamp.le(origin).all() or not result.station.eq(station).all():
            raise DemoError("Lỗi giới hạn dữ liệu tại giờ t.")
        return result

    def actual_after(self, forecast):
        if not isinstance(forecast, Forecast) or forecast.target != forecast.origin+pd.Timedelta(hours=1):
            raise DemoError("Chỉ đọc số đo đối chiếu sau khi đã có kết quả dự báo.")
        self.emit("future_actual")
        with self.connect() as connection:
            row = connection.execute("SELECT pm25 FROM actuals WHERE station=? AND target_timestamp=?", [forecast.station, str(forecast.target)]).fetchone()
        if row is None or row[0] is None:
            return None
        value = float(row[0])
        if not np.isfinite(value) or value < 0:
            raise DemoError("Số đo đối chiếu không hợp lệ; không thay thế bằng 0.")
        return value


def forecast_at(model, store, *, station, origin):
    if not isinstance(station, str) or station not in model.stations:
        raise DemoError("Chỉ chọn một trạm đã được model huấn luyện.")
    origin = valid_origin(origin)
    if origin < pd.Timestamp(model.metadata["last_fit_target"]):
        raise DemoError("Giờ t phải sau hoặc bằng nhãn fit cuối của model để minh họa dự báo theo thời gian.")
    if not pd.Timestamp(store.manifest["selection"]["start"]) <= origin < pd.Timestamp(store.manifest["selection"]["end"]):
        raise DemoError("Giờ t nằm ngoài phạm vi dữ liệu minh họa.")
    history = store.past(station, origin)
    result = features_for_prediction(history, station=station, origin=origin, config=model.config)
    X = result.select("A")
    # T08 accepts string-or-missing object categoricals. Pandas3's empty
    # StringDtype.map can keep string dtype when a single wd is missing.
    # Normalize representation only; no fill/imputation or fitted-state change.
    for column in model.config["features"]["A"]["categorical"]:
        X[column] = X[column].astype(object).where(X[column].notna(),np.nan)
    if tuple(X.columns) != model.feature_names:
        raise DemoError("Feature đầu vào không khớp schema model.")
    store.emit("predict_start")
    predicted = np.asarray(model.pipeline.predict(X), dtype=float)
    if predicted.shape != (1,) or not np.isfinite(predicted).all():
        raise DemoError("Pipeline không trả về một dự báo hữu hạn.")
    store.emit("predict_complete")
    current = history.loc[history.timestamp.eq(origin)].iloc[0]
    return Forecast(station, origin, origin+pd.Timedelta(hours=1), str(X.index[0]), float(predicted[0]),
        None if pd.isna(current["PM2.5"]) else float(current["PM2.5"]), tuple(X.columns[X.iloc[0].isna()]),
        history, X, model.handoff["final_run_id"])
