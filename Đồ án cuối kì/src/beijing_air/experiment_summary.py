"""Read-only T17a summaries. Never import a training runner or load raw samples."""

from dataclasses import dataclass
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import re
import subprocess
import textwrap
import zipfile

import numpy as np
import pandas as pd

from beijing_air.metrics import regression_metrics


GROUPS = ("Baseline", "Basic", "Tuned", "+Lag/rolling (B)", "+Chọn đặc trưng (C)",
          "Bổ sung (T17b)", "Gộp mô hình")
LABELS = {
    "no": "No", "group": "Nhóm", "method": "Method", "input": "Input", "approach": "Approach",
    "cv_pooled_mae": "CV pooled MAE", "cv_pooled_rmse": "CV pooled RMSE",
    "cv_fold_description": "CV MAE mean ± std theo fold (chỉ mô tả)",
    "validation_mae": "Validation MAE", "validation_rmse": "Validation RMSE",
    "validation_r2": "Validation R²", "mae_reduction_pct": "Δ MAE validation so với persistence (%)",
    "test_mae": "Test MAE (chỉ mô hình T13)", "test_run_id": "test_run_id",
    "locked": "Đã khóa (T12/T13)", "run_id": "run_id (validation/CV)",
    "cv_run_id": "cv_run_id", "status": "Trạng thái", "best_validation": "Tốt nhất validation (mô tả)",
    "validation_n": "Validation N", "notes": "Ghi chú",
}
NOTE = ("Đơn vị MAE/RMSE: µg/m³. Tô theo Validation MAE trên cùng primary IDs/coverage, chỉ mô tả; "
        "không đổi phương án khóa T12/T13. Test ML: T13 refit train+validation; persistence không fit, test_run_id riêng; "
        "không lấy chênh lệch/trung bình validation-test. CV mean±std ddof=0 chỉ mô tả, không là khoảng tin cậy.")


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def pooled_folds(metrics, frames=None):
    """Prefer complete OOF. Missing counts cannot be replaced with equal weights."""
    if not metrics:
        return None
    frames = frames or [None]*len(metrics)
    if len(frames) != len(metrics):
        raise ValueError("Fold metrics/predictions length mismatch")
    if all(frame is not None for frame in frames):
        pooled = pd.concat(frames, ignore_index=True)
        if pooled.sample_id.duplicated().any():
            raise ValueError("OOF sample IDs overlap across folds")
        values = [regression_metrics(f.y_true, f.y_pred) for f in frames]
        result = regression_metrics(pooled.y_true, pooled.y_pred)
        source = "saved_OOF_predictions"
    else:
        values = metrics
        counts = [number(m.get("n_scored")) for m in values]
        if any(n is None or n <= 0 or n != int(n) for n in counts):
            return None
        if any(number(m.get(k)) is None for m in values for k in ("MAE", "RMSE")):
            return None
        n = sum(counts)
        result = {"MAE": sum(c*m["MAE"] for c, m in zip(counts, values))/n,
                  "RMSE": float(np.sqrt(sum(c*m["RMSE"]**2 for c, m in zip(counts, values))/n)),
                  "n_scored": int(n)}
        source = "weighted_fold_metrics"
    return {"MAE": float(result["MAE"]), "RMSE": float(result["RMSE"]),
            "n_scored": int(result["n_scored"]), "folds": values, "source": source,
            "fold_mean": {k: float(np.mean([m[k] for m in values])) for k in ("MAE", "RMSE")},
            "fold_std": {k: float(np.std([m[k] for m in values], ddof=0)) for k in ("MAE", "RMSE")},
            "std_ddof": 0}


@dataclass
class Run:
    row: dict
    parameters: dict
    metrics: dict
    artifacts: list

    @property
    def id(self):
        return self.row["run_id"]

    @property
    def stage(self):
        return self.parameters.get("stage", "validation")

    @property
    def completed(self):
        return self.row.get("status") == "completed"


class Reader:
    """Allowlisted inputs: ledger, its run metrics and registered predictions only."""

    def __init__(self, root, ledger="experiments/experiment_log.csv"):
        self.root = Path(root).resolve()
        self.ledger = self.inside(ledger)
        self.sources, self.warnings, self.checks, self.frames = {}, [], [], {}
        self.metric_checks = set()

    def inside(self, name, *, base=None):
        path = ((base or self.root)/name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Input path escapes the project")
        return path

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def read(self, path, role, expected=None):
        name = self.relative(path)
        if not path.is_file():
            self.warnings.append("Chưa có: "+name)
            self.sources[name] = {"role": role, "exists": False}
            return None
        data = path.read_bytes()
        sha = digest(data)
        if expected and sha != expected:
            raise ValueError("Registered prediction checksum differs: "+name)
        self.sources[name] = {"role": role, "exists": True, "bytes": len(data), "sha256": sha}
        return data

    def load(self):
        data = self.read(self.ledger, "official_ledger")
        if data is None:
            raise FileNotFoundError("Official experiment log is missing")
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        if len({r["run_id"] for r in rows}) != len(rows):
            raise ValueError("Duplicate run_id in ledger")
        runs = []
        for row in rows:
            params = json.loads(row.get("parameters") or "{}")
            artifacts = json.loads(row.get("artifacts") or "[]")
            metrics = json.loads(row.get("metrics") or "{}")
            name = row.get("metrics_path")
            if name:
                path = self.inside(name, base=self.ledger.parent)
                expected_dir = self.root/"artifacts/experiments"/row["run_id"]
                if path != expected_dir/"metrics.json":
                    raise ValueError("metrics_path does not belong to run")
                raw = self.read(path, "run_metrics")
                if raw is not None:
                    metrics = json.loads(raw)
                elif metrics:
                    self.warnings.append("Dùng metric nhúng trong ledger: "+row["run_id"])
            runs.append(Run(row, params, metrics, artifacts))
        by_id = {r.id: r for r in runs}
        for run in runs:
            parent = by_id.get(run.row.get("parent_run_id"))
            if run.row.get("task_id") == "T12" and parent and "alpha" not in run.parameters:
                inherited = parent.parameters.get("signature", {}).get("design", {}).get("alpha")
                if inherited is not None:
                    run.parameters = {**run.parameters, "alpha": inherited}
        return runs

    def prediction(self, run, partition):
        key = (run.id, partition)
        if key in self.frames:
            return self.frames[key]
        matches = [a for a in run.artifacts if isinstance(a, dict) and
                   Path(a.get("path", "")).name in (partition+".csv", partition+".csv.gz") and
                   "/artifacts/predictions/" in a.get("path", "").replace("\\", "/")]
        if len(matches) > 1:
            raise ValueError("Ambiguous registered predictions for "+run.id)
        frame = None
        if matches:
            item = matches[0]
            path = self.inside(item["path"], base=self.ledger.parent)
            allowed = self.root/"artifacts/experiments"/run.id/"artifacts/predictions"
            if path.parent != allowed:
                raise ValueError("Prediction path does not belong to run")
            # A test artifact is never opened for a non-T13 or parent run.
            if partition == "test" and (run.row.get("task_id") != "T13" or
                    run.row.get("model") not in ("persistence", "ridge", "random_forest") or
                    run.stage != "final_refit_test" or not run.completed):
                raise ValueError("Only completed T13 child test predictions are allowed")
            raw = self.read(path, "saved_"+partition+"_predictions", item.get("sha256"))
            if raw is not None:
                frame = pd.read_csv(io.BytesIO(raw), compression="gzip" if path.suffix == ".gz" else None,
                    usecols=lambda c: c in {"sample_id", "y_true", "y_pred", "is_primary", "run_id"})
                if not {"sample_id", "y_true", "y_pred"}.issubset(frame):
                    raise ValueError("Prediction schema missing required columns")
                if "is_primary" in frame:
                    primary = frame.is_primary.astype(str).str.lower()
                    if not primary.isin(["true", "false"]).all():
                        raise ValueError("Invalid primary cohort flag")
                    frame = frame.loc[primary.eq("true")].copy()
                if frame.sample_id.isna().any() or frame.sample_id.duplicated().any():
                    raise ValueError("Invalid/duplicate prediction sample IDs")
                if "run_id" in frame and not frame.run_id.eq(run.id).all():
                    raise ValueError("Prediction run_id differs from ledger")
                frame = frame.sort_values("sample_id", kind="stable").reset_index(drop=True)
        self.frames[key] = frame
        return frame

    def check(self, label, observed, expected, run_id, tolerance=1e-6):
        actual, wanted = number(observed), number(expected)
        status = "CHƯA CÓ" if actual is None or wanted is None else (
            "OK" if abs(actual-wanted) <= tolerance else "KHÁC")
        self.checks.append({"check": label, "run_id": run_id, "observed": actual,
                            "expected": wanted, "tolerance": tolerance, "status": status})


def effective_parameters(run):
    p = run.parameters
    sig = p.get("signature", {})
    return p.get("actual_model_parameters") or sig.get("effective_model_parameters") or p


def alpha(run):
    return number(effective_parameters(run).get("alpha"))


def same_configuration(a, b):
    hyperparameters = {"alpha", "fit_intercept", "positive", "solver", "tol", "max_iter", "copy_X", "random_state",
                       "n_estimators", "max_depth", "min_samples_leaf", "max_features", "criterion", "bootstrap"}
    ap, bp = effective_parameters(a), effective_parameters(b)
    compatible = all(key in ap and ap[key] == value for key, value in bp.items() if key in hyperparameters)
    return (compatible and a.row.get("model") == b.row.get("model") and
            a.row.get("feature_set") == b.row.get("feature_set") and
            json.loads(a.row.get("preprocessing") or "{}") == json.loads(b.row.get("preprocessing") or "{}") and
            alpha(a) == alpha(b) and a.parameters.get("k_groups") == b.parameters.get("k_groups"))


def group(run):
    task, model, fs = (run.row.get(k, "") for k in ("task_id", "model", "feature_set"))
    if model in ("fusion", "stack", "stacking", "fusion_3"):
        return GROUPS[6]
    if task.upper().startswith("T17B"):
        return GROUPS[5]
    if model == "persistence":
        return GROUPS[0]
    if fs == "C":
        return GROUPS[4]
    if fs == "B":
        return GROUPS[3]
    return GROUPS[2] if task == "T11" else GROUPS[1]


def row_description(run):
    model, fs = run.row.get("model", ""), run.row.get("feature_set", "")
    if model == "persistence":
        age = run.parameters.get("signature", {}).get("baseline_config", {}).get("max_history_age_hours")
        fallback = f"history≤{age}h" if age is not None else "history theo config"
        return "Persistence", "PM2.5(t)", "PM2.5(t+1)=PM2.5(t); fallback "+fallback+" rồi median train"
    name = {"ridge": "Ridge", "random_forest": "Random Forest"}.get(model, model)
    if model == "ridge":
        approach = "Ridge alpha="+str(alpha(run))
    elif model == "random_forest":
        p = effective_parameters(run)
        approach = "; ".join(f"{k}={p[k]}" for k in ("n_estimators", "max_depth", "min_samples_leaf", "n_jobs") if k in p)
    else:
        approach = "; ".join(f"{k}={v}" for k, v in effective_parameters(run).items()
                             if isinstance(v, (int, float, bool)) and k not in ("is_test",))
    desc = {"A": "A: số đo t, station/wd, lịch t+1", "B": "B: A + lag/rolling PM2.5",
            "C": "C: chọn nhóm từ B"}.get(fs, fs)
    if run.parameters.get("k_groups") is not None:
        approach += "; k_groups="+str(run.parameters["k_groups"])
    return name+" "+fs, desc, approach or "tham số: xem ledger"


def metric_match(reader, run, partition, metric):
    frame = reader.prediction(run, partition)
    if frame is not None and (run.id, partition) not in reader.metric_checks:
        reader.metric_checks.add((run.id, partition))
        measured = regression_metrics(frame.y_true, frame.y_pred, allow_unavailable=True)
        for key in ("MAE", "RMSE", "R2", "n_scored"):
            reader.check(partition+" predictions vs log: "+key, measured.get(key), metric.get(key), run.id)
    return frame


def cv_evidence(reader, candidate, by_id):
    ids = candidate.metrics.get("fold_run_ids", [])
    if (not candidate.completed or len(ids) != 3 or len(set(ids)) != len(ids) or
            any(i not in by_id or not by_id[i].completed for i in ids) or candidate.metrics.get("failed_fold_run_ids")):
        return None
    folds = [by_id[i] for i in ids]
    if any(f.row.get("parent_run_id") != candidate.id for f in folds):
        raise ValueError("Fold/candidate provenance mismatch")
    metrics = [f.metrics.get("evaluation", {}) for f in folds]
    frames = [metric_match(reader, f, "evaluation", m) for f, m in zip(folds, metrics)]
    result = pooled_folds(metrics, frames)
    if result:
        for key in ("MAE", "RMSE"):
            reader.check("CV pooled "+key+" vs log", result[key], candidate.metrics.get("pooled", {}).get(key), candidate.id)
        result["fold_run_ids"] = ids
    return result


def same_evaluation(frame, baseline):
    return (frame is not None and baseline is not None and
            frame.sample_id.equals(baseline.sample_id) and
            np.array_equal(frame.y_true.to_numpy(), baseline.y_true.to_numpy()) and
            np.isfinite(frame.y_pred).all() and np.isfinite(baseline.y_pred).all())


def build_summary(reader, *, include_plans=True):
    runs = reader.load()
    by_id = {r.id: r for r in runs}
    official = [r for r in runs if r.row.get("mode") == "full" and r.row.get("is_test", "").lower() != "true"]
    t17b_parent_status = {
        r.id: r.completed for r in official
        if r.row.get("task_id", "").upper() == "T17B" and r.stage == "search"
    }
    # Keep failed attempts in the audit export, but do not duplicate their completed children in the model table.
    official = [r for r in official if not (
        r.row.get("task_id", "").upper() == "T17B"
        and r.row.get("parent_run_id") in t17b_parent_status
        and not t17b_parent_status[r.row.get("parent_run_id")]
    )]
    candidates = [r for r in official if r.stage == "candidate"]
    finals = [r for r in official if r.row.get("task_id") != "T13" and r.stage not in ("candidate", "search", "fold")
              and not r.row.get("fold_id")]
    chosen = set()
    pairs = []
    for final in finals:
        related = [c for c in candidates if same_configuration(final, c) and
                   (final.parameters.get("selected_candidate_run_id") == c.id or
                    c.row.get("reference_run_id") == final.id)]
        if len(related) > 1:
            raise ValueError("Multiple CV sources for one validation configuration; keep provenance explicit")
        candidate = related[0] if related else None
        if candidate:
            chosen.add(candidate.id)
        pairs.append((final, candidate))
    pairs += [(c, c) for c in candidates if c.id not in chosen]
    locked_ids = {r.parameters.get("design", {}).get("development_selected_run_id") for r in official
                  if r.row.get("task_id") == "T13" and r.completed and r.row.get("model") == "locked_final_comparison"}
    locked_ids.discard(None)
    if len(locked_ids) > 1:
        raise ValueError("Conflicting historical deployment locks")
    locked_id = next(iter(locked_ids), None)
    baselines = [r for r in finals if r.row.get("model") == "persistence" and r.completed]
    if len(baselines) > 1:
        raise ValueError("Multiple full persistence baselines; select an explicit cohort reference")
    base = baselines[0] if baselines else None
    base_metric = base.metrics.get("validation_primary", {}) if base else {}
    base_frame = metric_match(reader, base, "validation", base_metric) if base else None
    rows, provenance = [], []
    for run, candidate in pairs:
        method, inputs, approach = row_description(run)
        metric = run.metrics.get("validation_primary", {}) if run.completed else {}
        frame = metric_match(reader, run, "validation", metric) if metric else None
        cv = cv_evidence(reader, candidate, by_id) if candidate else None
        comparable = bool(metric and same_evaluation(frame, base_frame) and number(metric.get("coverage")) == 1)
        notes = []
        inconsistent = any(c["run_id"] == run.id and c["status"] == "KHÁC" and
                           c["check"].startswith("validation predictions") for c in reader.checks)
        if inconsistent:
            comparable = False
            notes.append("Metric log KHÁC predictions; giữ số đã ghi, không tính Δ% hoặc tô")
        if not metric:
            notes.append("Chỉ CV; chưa chấm validation" if run.completed else "Run "+run.row.get("status", "unknown"))
        if candidate and not cv:
            notes.append("CV chưa đủ bằng chứng/fold/n_i")
        if metric and not comparable:
            notes.append("Chưa xác minh cùng validation IDs/targets/coverage; không tính Δ% hoặc tô")
        reduction = None
        mae, baseline_mae = number(metric.get("MAE")), number(base_metric.get("MAE"))
        if comparable and mae is not None and baseline_mae is not None and baseline_mae > 0:
            reduction = 100*(baseline_mae-mae)/baseline_mae
        elif comparable:
            notes.append("Δ% chưa có: baseline MAE≤0 hoặc thiếu metric")
        tests = [r for r in official if r.row.get("task_id") == "T13" and r.completed and
                 r.row.get("model") in ("persistence", "ridge", "random_forest") and
                 r.row.get("reference_run_id") == run.id and r.row.get("model") == run.row.get("model") and
                 r.row.get("feature_set") == "A" and run.row.get("feature_set") == "A" and
                 r.parameters.get("locked_parameters") == effective_parameters(run)]
        # Persistence T09 stores a descriptive feature-set string, unlike T13 A.
        if run.row.get("model") == "persistence":
            tests = [r for r in official if r.row.get("task_id") == "T13" and r.completed and
                     r.stage == "final_refit_test" and r.row.get("model") == "persistence" and
                     r.row.get("reference_run_id") == run.id and r.row.get("feature_set") == "A"]
        tests = [r for r in tests if r.stage == "final_refit_test" and "test_primary" in r.metrics]
        if len(tests) > 1:
            raise ValueError("Multiple T13 test runs for a development configuration")
        test = tests[0] if tests else None
        if test:
            metric_match(reader, test, "test", test.metrics["test_primary"])
            notes.append("Test: run persistence T13 riêng, quy tắc không fit; khác tập validation" if
                         run.row.get("model") == "persistence" else
                         "Test: T13 refit train+validation, fitted model khác bên validation")
        if locked_id == run.id:
            notes.append("Phương án đã khóa bằng validation T12/T13")
        if run.row.get("task_id", "").upper().startswith("T17B"):
            notes.append("ứng viên, chưa đánh giá độc lập")
        if candidate and candidate.id != run.id:
            notes.append("CV/validation khác run; liên kết cùng cấu hình, xem cv_run_id")
        row = {"no": None, "group": group(run), "method": method, "input": inputs, "approach": approach,
               "cv_pooled_mae": cv["MAE"] if cv else None, "cv_pooled_rmse": cv["RMSE"] if cv else None,
               "cv_fold_description": f"{cv['fold_mean']['MAE']:.6f} ± {cv['fold_std']['MAE']:.6f}" if cv else None,
               "validation_mae": mae, "validation_rmse": number(metric.get("RMSE")),
               "validation_r2": number(metric.get("R2")), "mae_reduction_pct": reduction,
               "test_mae": number(test.metrics["test_primary"].get("MAE")) if test else None,
               "test_run_id": test.id if test else None, "locked": run.id == locked_id,
               "run_id": run.id, "cv_run_id": candidate.id if candidate else None,
               "status": run.row.get("status"), "best_validation": False,
               "validation_n": int(metric["n_scored"]) if number(metric.get("n_scored")) is not None else None,
               "notes": "; ".join(notes), "comparable": comparable}
        rows.append(row)
        provenance.append({"run_id": run.id, "cv_run_id": row["cv_run_id"], "cv": cv,
                           "test_run_id": row["test_run_id"], "validation_source": run.row.get("metrics_path"),
                           "test_source": test.row.get("metrics_path") if test else None})
    valid = [r for r in rows if r["comparable"] and r["status"] == "completed" and r["validation_mae"] is not None]
    if valid:
        best = min(r["validation_mae"] for r in valid)
        for row in valid:
            row["best_validation"] = abs(row["validation_mae"]-best) <= 1e-12
    rows.sort(key=lambda r: (GROUPS.index(r["group"]), r["method"], r["approach"], r["run_id"]))
    if include_plans:
        for category in GROUPS[5:]:
            if not any(r["group"] == category for r in rows):
                blank = {k: None for k in LABELS}
                blank.update(group=category, method="Chưa chạy (kế hoạch)", input="chưa có", approach="chưa có",
                             status="not_run", locked=False, best_validation=False, comparable=False,
                             notes="Không có run hoặc số liệu; không tô")
                rows.append(blank)
    for i, row in enumerate(rows, 1):
        row["no"] = i
    historical_checks(reader, rows)
    inventory = [{"run_id": r.id, "task_id": r.row.get("task_id"), "mode": r.row.get("mode"),
                  "stage": r.stage, "fold_id": r.row.get("fold_id"), "model": r.row.get("model"),
                  "status": r.row.get("status"), "has_error": bool(r.row.get("error")),
                  "main_row": any(row["run_id"] == r.id for row in rows)} for r in runs]
    return rows, {"runs": inventory, "row_provenance": provenance, "locked_development_run_id": locked_id,
                  "checks": reader.checks, "warnings": sorted(set(reader.warnings)),
                  "ledger_rows": len(runs), "new_experiment_runs": 0, "raw_test_samples_read": False}


def historical_checks(reader, rows):
    specs = [
        ("persistence", None, None, "validation_mae", 9.736617),
        ("persistence", None, None, "validation_rmse", 19.240919),
        ("persistence", None, None, "validation_r2", .944804),
        ("ridge", "A", 1., "validation_mae", 10.200433),
        ("ridge", "A", 1., "validation_rmse", 18.907140),
        ("random_forest", "A", None, "validation_mae", 9.561488),
        ("random_forest", "A", None, "validation_rmse", 18.964825),
        ("ridge", "A", .1, "validation_mae", 10.200529),
        ("ridge", "A", .1, "cv_pooled_mae", 10.405534),
        ("ridge", "A", 1., "cv_pooled_mae", 10.412704),
        ("ridge", "B", .1, "validation_mae", 9.968755),
        ("ridge", "B", .1, "validation_rmse", 18.467071),
        ("ridge", "C", .1, "validation_mae", 9.903377),
        ("ridge", "C", .1, "validation_rmse", 18.501063)]
    # Stable historical run IDs: never apply old checkpoints to a new T17b model.
    for model, fs, a, field, expected in specs:
        name = {"ridge": "Ridge", "random_forest": "Random Forest", "persistence": "Persistence"}[model]
        matches = [r for r in rows if r["method"] == name+(" "+fs if fs else "") and
                   (a is None or "alpha="+str(a) in r["approach"]) and
                   r["group"] not in GROUPS[5:] and (field.startswith("cv_") or r["validation_mae"] is not None)]
        if field.startswith("cv_"):
            matches = [r for r in matches if r["cv_run_id"]]
        if model == "ridge" and fs == "C":
            matches = [r for r in matches if r["validation_mae"] is not None]
        row = matches[0] if len(matches) == 1 else None
        reader.check("historical "+name+" "+str(fs)+" "+str(a)+" "+field,
                     row.get(field) if row else None, expected, row["run_id"] if row else "")


def display_value(key, value):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "" if key in ("test_mae", "test_run_id", "run_id", "cv_run_id") else "chưa có"
    if key in ("locked", "best_validation"):
        return "Có" if value else ""
    if isinstance(value, (float, np.floating)):
        return f"{value:.6f}"
    return str(value)


def markdown_table(headers, records):
    def clean(value):
        return str(value).replace("|", "/").replace("\n", "<br>")
    return "\n".join(["| "+" | ".join(headers)+" |", "| "+" | ".join(["---"]*len(headers))+" |"]+
                     ["| "+" | ".join(clean(x) for x in row)+" |" for row in records])


def stable_xlsx(frame, audit, checks, footer, generated_at):
    """Canonical ZIP/core timestamps keep identical XLSX bytes across builds."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        return None
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, data in (("Summary", frame), ("All runs", pd.DataFrame(audit)), ("Checks", pd.DataFrame(checks))):
        sheet = workbook.create_sheet(name)
        sheet.append(list(data.columns))
        for row in data.itertuples(index=False, name=None):
            sheet.append([None if pd.isna(v) else v for v in row])
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="173548")
            cell.alignment = Alignment(wrap_text=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 44
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(45, max(14, len(str(col[0].value))+2))
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if isinstance(cell.value, float):
                    cell.number_format = "0.000000"
        if name == "Summary":
            best_col = list(data.columns).index(LABELS["best_validation"])+1
            lock_col = list(data.columns).index(LABELS["locked"])+1
            for row in sheet.iter_rows(min_row=2):
                if row[best_col-1].value is True:
                    for cell in row:
                        cell.fill = PatternFill("solid", fgColor="DEF0E7")
                if row[lock_col-1].value is True:
                    row[lock_col-1].font = Font(bold=True, color="006D77")
            for line in (NOTE, footer):
                sheet.append([line])
    buffer = io.BytesIO()
    workbook.save(buffer)
    canonical = io.BytesIO()
    iso = datetime.fromisoformat(generated_at).astimezone(timezone.utc).isoformat()
    with zipfile.ZipFile(buffer) as source, zipfile.ZipFile(canonical, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name in sorted(source.namelist()):
            data = source.read(name)
            if name == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:(?:created|modified)>)",
                              lambda m: m[1]+iso.encode()+m[2], data)
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            out.writestr(entry, data)
    return canonical.getvalue()


def table_png(rows, footer):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    top = ["no", "group", "method", "input", "approach", "cv_pooled_mae", "cv_fold_description",
           "validation_mae", "validation_rmse", "validation_r2", "mae_reduction_pct", "test_mae", "locked"]
    short_labels = ["No", "Nhóm", "Method", "Input", "Approach", "CV pooled\nMAE", "CV MAE\nmean ± std",
                    "Val MAE", "Val RMSE", "Val R²", "Δ MAE val\nvs pers. (%)", "Test MAE\nT13", "Đã khóa"]
    bottom = ["no", "run_id", "cv_run_id", "test_run_id", "status", "notes"]
    def wrap(value, width):
        return "\n".join(textwrap.wrap(value, width=width, break_long_words=True))
    def top_value(key, row):
        value = display_value(key, row.get(key))
        if key == "approach":
            for name, short in (("n_estimators=", "trees="), ("max_depth=", "depth="),
                                ("min_samples_leaf=", "leaf="), ("n_jobs=", "jobs=")):
                value = value.replace(name, short)
        return wrap(value, 25 if key == "approach" else 18)
    with plt.rc_context({"font.family": "DejaVu Sans"}):
        if not rows:
            fig, ax = plt.subplots(figsize=(12, 4))
            ax.axis("off"); ax.text(.02, .65, "Chưa có cấu hình đã chạy", fontsize=18)
            ax.text(.02, .15, footer, fontsize=8)
            buffer = io.BytesIO()
            fig.savefig(buffer, format="png", dpi=150, metadata={"Software": "T17a experiment summary"})
            plt.close(fig)
            return buffer.getvalue()
        fig = plt.figure(figsize=(27, 5.5+len(rows)*.8), facecolor="white")
        ax1 = fig.add_axes([.015, .50, .97, .41]); ax1.axis("off")
        ax2 = fig.add_axes([.015, .14, .97, .31]); ax2.axis("off")
        data = [[top_value(k, row) for k in top] for row in rows]
        widths = [.025, .085, .075, .11, .15, .065, .095, .06, .06, .055, .065, .06, .035]
        table = ax1.table(cellText=data, colLabels=short_labels, colWidths=widths, bbox=[0, 0, 1, 1], cellLoc="left")
        details = []
        for row in rows:
            values = []
            for key in bottom:
                value = display_value(key, row.get(key))
                if key.endswith("run_id"):
                    value = value[:12]
                values.append(wrap(value, 85 if key == "notes" else 20))
            details.append(values)
        table2 = ax2.table(cellText=details, colLabels=["No", "run_id val/CV (12 ký tự)", "cv_run_id (12 ký tự)",
                            "test_run_id (12 ký tự)", "Trạng thái", "Ghi chú / provenance"],
                          colWidths=[.025, .12, .12, .12, .07, .545], bbox=[0, 0, 1, 1], cellLoc="left")
        for table_ in (table, table2):
            table_.auto_set_font_size(False); table_.set_fontsize(8)
            for (i, j), cell in table_.get_celld().items():
                cell.set_edgecolor("#d4dee3"); cell.set_linewidth(.5)
                if i == 0:
                    cell.set_facecolor("#173548"); cell.get_text().set_color("white"); cell.get_text().set_weight("bold")
                elif rows[i-1]["best_validation"]:
                    cell.set_facecolor("#def0e7")
                elif rows[i-1]["status"] == "not_run":
                    cell.set_facecolor("#f2f4f6")
        fig.text(.02, .965, "PM2.5 · Bảng tổng hợp thí nghiệm", fontsize=20, weight="bold", color="#173548")
        fig.text(.02, .935, "Development và test refit được tách nguồn; không chọn lại mô hình bằng test", fontsize=12)
        fig.text(.02, .105, wrap(NOTE, 205), fontsize=10, va="top")
        fig.text(.02, .052, "ID trên ảnh rút gọn12ký tự; ID đầy đủ trong CSV/MD/XLSX. Xanh nhạt: tốt nhất validation; cột Đã khóa giữ độc lập.", fontsize=10)
        fig.text(.02, .025, footer, fontsize=9)
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=150, facecolor="white", metadata={"Software": "T17a experiment summary"})
        plt.close(fig)
    return buffer.getvalue()


def export_summary(reader, rows, evidence, output="reports/tables"):
    directory = reader.inside(output)
    directory.mkdir(parents=True, exist_ok=True)
    module_sha = digest(Path(__file__).read_bytes())
    cli = Path(__file__).resolve().parents[2]/"scripts/build_experiment_summary.py"
    generator_files = {"src/beijing_air/experiment_summary.py": module_sha,
                       "scripts/build_experiment_summary.py": digest(cli.read_bytes()) if cli.is_file() else None}
    environment = {}
    for name in ("pandas", "numpy", "matplotlib", "openpyxl"):
        try:
            environment[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            environment[name] = None
    signature = digest(json_bytes({"sources": reader.sources, "rows": rows, "generator_files": generator_files,
                                   "environment": environment}))
    previous_path = directory/"experiment_summary_provenance.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else {}
    if previous.get("input_signature") == signature:
        generated_at, commit = previous["generated_at"], previous["source_commit"]
    else:
        generated_at = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
        git = subprocess.run(["git", "-C", str(reader.root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False)
        commit = git.stdout.strip() if git.returncode == 0 else "unavailable"
    log_path = reader.relative(reader.ledger)
    footer = f"Nguồn: {log_path} | commit: {commit[:12]} | sinh: {generated_at}"
    frame = pd.DataFrame([{LABELS[k]: r.get(k) for k in LABELS} for r in rows], columns=list(LABELS.values()))
    frame["source_commit"], frame["generated_at"], frame["source_log"] = commit, generated_at, log_path
    output_rows = []
    for row in rows:
        values = [display_value(k, row.get(k)) for k in LABELS]
        if row["best_validation"]:
            values = ["**"+v+"**" if v else v for v in values]
        output_rows.append(values)
    text = "# Bảng tổng hợp thí nghiệm PM2.5\n\n"+markdown_table(list(LABELS.values()), output_rows)
    text += "\n\n"+footer+"\n\n"+NOTE+"\n\nÔ trống ở Test: cấu hình không có T13 tương ứng; chưa có không phải0. "
    text += "Dòng đậm tương ứng highlight validation. Parent/fold/smoke xem experiment_summary_runs.csv, không gọi mỗi hồ sơ là một model.\n\n"
    text += "## Đối chiếu artifact và số lịch sử (1e-6)\n\n"+markdown_table(
        ["Kiểm tra", "run_id", "Đo/đọc được", "Đã ghi/tham chiếu", "Trạng thái"],
        [[c["check"], c["run_id"], display_value("value", c["observed"]),
          display_value("value", c["expected"]), c["status"]] for c in evidence["checks"]])+"\n"
    if evidence["warnings"]:
        text += "\n## Thiếu bằng chứng\n\n"+"\n".join("- "+w for w in evidence["warnings"])+"\n"
    contents = {
        "experiment_summary.csv": frame.to_csv(index=False, float_format="%.15g", lineterminator="\n").encode("utf-8-sig"),
        "experiment_summary.md": text.encode("utf-8"),
        "experiment_summary_checks.csv": pd.DataFrame(evidence["checks"]).to_csv(index=False, float_format="%.15g", lineterminator="\n").encode("utf-8-sig"),
        "experiment_summary_runs.csv": pd.DataFrame(evidence["runs"]).to_csv(index=False, lineterminator="\n").encode("utf-8-sig"),
        "experiment_summary.png": table_png(rows, footer),
    }
    xlsx = stable_xlsx(frame, evidence["runs"], evidence["checks"], footer, generated_at)
    if xlsx is not None:
        contents["experiment_summary.xlsx"] = xlsx
    report = {**evidence, "input_signature": signature, "source_commit": commit, "generated_at": generated_at,
              "source_log": log_path, "generator_sha256": module_sha, "generator_files": generator_files, "environment": environment,
              "sources": reader.sources, "rows": rows, "note": NOTE,
              "outputs": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in contents.items()},
              "xlsx_available": xlsx is not None}
    contents["experiment_summary_provenance.json"] = json_bytes(report)
    for name, data in contents.items():
        path = directory/name
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
    return report
