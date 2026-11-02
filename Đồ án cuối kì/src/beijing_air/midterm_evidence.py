"""Read-only midterm evidence checks. Never fit, log runs or open test samples."""

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from beijing_air.metrics import regression_metrics


RUNS = {
    "Persistence T09": "24cef47874a94d9faa7bfcbae29b5c58",
    "Ridge A T10": "aec8630115714bb59d5c89c8a6b368c1",
    "RF A T10": "780ecb7fb59d48bea58d5e4a076f1f26",
    "Ridge A T11": "32e65c5a4cbc489c905cf146b743867f",
    "Ridge B T12": "48d2f03be4614a25906f84d98df9e9dc",
    "Ridge C T12": "3a9f2500e4dd4ef28d7bc20def6f79c8",
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""): h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def safe_path(root, relative):
    p = (Path(root) / relative).resolve()
    if not p.is_relative_to(Path(root).resolve()): raise ValueError("Path escapes project")
    return p


def close_score(actual, expected):
    for key, value in actual.items():
        if key not in expected: raise ValueError(f"Missing recorded metric {key}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not np.isclose(value, expected[key], rtol=1e-10, atol=1e-10): raise ValueError(f"Metric differs: {key}")
        elif value != expected[key]: raise ValueError(f"Metric differs: {key}")


def verify_ledger(root):
    root = Path(root).resolve()
    ledger = root / "experiments/experiment_log.csv"
    before = sha(ledger)
    with ledger.open(encoding="utf-8", newline="") as stream: rows = list(csv.DictReader(stream))
    ids = [r["run_id"] for r in rows]
    if len(ids) != len(set(ids)): raise ValueError("Duplicate run ID")
    index, artifacts, scored = {}, 0, 0
    for row in rows:
        run_id = row["run_id"]
        if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id): raise ValueError("Invalid ID")
        d = root / "artifacts/experiments" / run_id
        cfg, meta, metrics = (read(d / f"{name}.json") for name in ("config", "metadata", "metrics"))
        if cfg["is_test"] or meta["status"] != "completed" or row["status"] != meta["status"]:
            raise ValueError("Expected real completed history for this report snapshot")
        if json.loads(row["metrics"]) != metrics: raise ValueError("CSV/metrics differ")
        for name in ("config", "metadata", "metrics", "notes"):
            if safe_path(root, Path("experiments") / row[f"{name}_path"]) != d / ("notes.md" if name == "notes" else f"{name}.json"):
                raise ValueError("CSV link differs")
        for info in meta["artifacts"]:
            p = (root / "experiments" / info["path"]).resolve()
            if not p.is_relative_to(d) or p.stat().st_size != info["size_bytes"] or sha(p) != info["sha256"]:
                raise ValueError(f"Artifact checksum/size/path differs: {info['path']}")
            artifacts += 1
            if "/predictions/" not in p.as_posix(): continue
            if p.name not in ("train.csv.gz", "validation.csv.gz", "validation.csv", "evaluation.csv.gz"):
                raise ValueError("Unapproved prediction partition")
            pred = pd.read_csv(p)
            if not pred.sample_id.is_unique or not pred.run_id.eq(run_id).all(): raise ValueError("Prediction IDs invalid")
            partition = p.name.split(".")[0]
            subset = pred.loc[pred.is_primary] if "is_primary" in pred else pred
            key = "evaluation" if partition == "evaluation" else f"{partition}_primary"
            close_score(regression_metrics(subset.y_true, subset.y_pred), metrics[key])
            if "negative_predictions" in metrics[key] and int(subset.y_pred.lt(0).sum()) != metrics[key]["negative_predictions"]:
                raise ValueError("Negative prediction count differs")
            if partition == "validation" and "validation_operational" in metrics:
                close_score(regression_metrics(pred.y_true, pred.y_pred, allow_unavailable=True), metrics["validation_operational"])
            scored += 1
        index[run_id] = {"config": cfg, "metadata": meta, "metrics": metrics}
    # Recompute candidate pooled and unweighted fold summary, not an average of R² for selection.
    for run_id, value in index.items():
        m = value["metrics"]
        if "fold_mean" not in m: continue
        frames = [pd.read_csv(root / "artifacts/experiments" / rid / "artifacts/predictions/evaluation.csv.gz") for rid in m["fold_run_ids"]]
        if len(frames) != 3: raise ValueError("Candidate missing folds")
        pooled = pd.concat(frames, ignore_index=True)
        if not pooled.sample_id.is_unique: raise ValueError("OOF overlap")
        close_score(regression_metrics(pooled.y_true, pooled.y_pred), m["pooled"])
        for metric in ("MAE", "RMSE", "R2"):
            values = [regression_metrics(f.y_true, f.y_pred)[metric] for f in frames]
            mean = float(np.mean(values)) if all(v is not None for v in values) else None
            std = float(np.std(values, ddof=0)) if all(v is not None for v in values) else None
            close_score({metric: mean}, {metric: m["fold_mean"][metric]})
            close_score({metric: std}, {metric: m["fold_std"][metric]})
    if sha(ledger) != before: raise RuntimeError("Read-only verification changed ledger")
    return index, {"ledger_sha256": before, "runs": len(rows), "artifacts_checked": artifacts,
                   "prediction_files_recomputed": scored, "model_fit_performed": False, "test_samples_accessed": False}


def collect(root):
    root = Path(root).resolve()
    index, checks = verify_ledger(root)
    config = read(root / "configs/midterm.json")
    models, frozen_ids = [], None
    for label, run_id in RUNS.items():
        item = index[run_id]
        if item["config"]["mode"] != "full": raise ValueError("Report cannot use smoke as full")
        artifact = next(a for a in item["metadata"]["artifacts"] if "/predictions/validation.csv" in a["path"])
        pred = pd.read_csv(root / "experiments" / artifact["path"])
        pred = pred.loc[pred.is_primary]
        ids = pred.sample_id.tolist()
        if frozen_ids is None: frozen_ids = ids
        if ids != frozen_ids: raise ValueError("Models do not share primary validation IDs")
        m = item["metrics"]
        models.append({"label": label, "run_id": run_id, "task_id": item["config"]["task_id"], "mode": "full",
                       "feature_set": item["config"]["feature_set"], "N": len(pred),
                       **{key: m["validation_primary"][key] for key in ("MAE", "RMSE", "R2")},
                       "train": m.get("train_primary"), "timing_seconds": m.get("timing_seconds"),
                       "negative_predictions": int(pred.y_pred.lt(0).sum())})
    numeric = pd.read_csv(root / "reports/eda_train/numeric_summary.csv").set_index("column")
    splits = pd.read_csv(root / "reports/splits_full/split_summary.csv").to_dict("records")
    missing = []
    for key, label in (("group_number", "Số nhóm"), ("institution", "Trường/khoa"), ("class_code", "Lớp học phần"),
                       ("lecturer", "Giảng viên"), ("members", "Họ tên–MSSV"), ("confirmed_contributions", "Phân công/đóng góp có xác nhận"),
                       ("teacher_rubric_url", "Rubric/yêu cầu riêng của thầy"), ("submission_deadline", "Hạn nộp chính thức")):
        if not config.get(key): missing.append(label)
    try: commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except (OSError, subprocess.SubprocessError): commit = None
    return {"schema_version": "mk01-evidence-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit": commit, "draft": bool(missing), "missing": missing, "config": config,
            "checks": checks, "models": models, "split_config": read(root / "configs/default.json")["split"],
            "split_summary": splits, "raw_audit": read(root / "reports/raw_audit_full.json"),
            "data_manifest": read(root / "reports/data_manifest.json"),
            "eda_numeric": numeric.reset_index().to_dict("records"),
            "eda_figures": pd.read_csv(root / "reports/eda_train/figure_index.csv").to_dict("records"),
            "t11_candidates": pd.read_csv(root / "reports/tuning/candidates.csv").to_dict("records"),
            "t12_candidates": pd.read_csv(root / "reports/ablation/candidates.csv").to_dict("records"),
            "cv_folds": read(root / "artifacts/experiments/c895894bcf5a4ff28982fbb1ca9d69d9/artifacts/data/folds.json"),
            "frozen": read(root / "reports/ablation/frozen_model.json")}
