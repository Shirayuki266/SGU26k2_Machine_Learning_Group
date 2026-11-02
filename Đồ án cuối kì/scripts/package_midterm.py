"""Package the existing midterm evidence; never fit or read test samples.

Run from a Git checkout or from source/ in an extracted submission. ZIP outputs
stay ignored: actual predictions make this package too large for a Git blob.
"""

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

from openpyxl import Workbook
from openpyxl.styles import Font

from beijing_air.midterm_evidence import read, sha, safe_path

ROOT = Path(__file__).resolve().parents[1]
STEM = "NhomXX_DuBaoPM25_BacKinh_GiuaKy"
OUT = ROOT / "reports/submission"
BLOCKED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
           ".ipynb_checkpoints", ".aws", ".codex", ".agents", "node_modules"}


def allowed(name):
    parts = PurePosixPath(name).parts
    return (bool(parts) and not any(p in BLOCKED for p in parts)
            and not any(p == ".env" or p.startswith(".env.") for p in parts)
            and not any(p.lower() in {"id_rsa", "id_ed25519", "credentials", "secrets.json"} for p in parts)
            and not name.startswith(("reports/submission/", "data/raw/", "data/processed/"))
            and not name.endswith((".pyc", ".pyo", ".pem", ".key")))


def inventory(root):
    root = Path(root).resolve()
    # An extracted package records its own canonical source inventory.
    recorded = root.parent / "resources/submission_manifest.json"
    if recorded.is_file():
        manifest = read(recorded)
        names = {f["path"][7:] for f in manifest["files"] if f["path"].startswith("source/") and allowed(f["path"][7:])}
    else:
        raw = subprocess.check_output(["git", "ls-files", "-z", "--", "."], cwd=root)
        names = {n.decode("utf-8") for n in raw.split(b"\0") if n and allowed(n.decode("utf-8"))}
    # Include these scripts/docs before the MK02 commit as well.
    names.update({"scripts/package_midterm.py", "scripts/verify_submission.py",
                  "scripts/verify_midterm.py", "docs/submission_checklist.md",
                  "tests/test_submission.py"})
    ledger = root / "experiments/experiment_log.csv"
    with ledger.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        directory = f"artifacts/experiments/{row['run_id']}"
        names.update(f"{directory}/{n}" for n in ("config.json", "metadata.json", "metrics.json", "notes.md"))
        for info in read(root / directory / "metadata.json")["artifacts"]:
            path = safe_path(root, Path("experiments") / info["path"])
            if not path.is_relative_to(root / directory):
                raise ValueError("Artifact escapes its run directory")
            if sha(path) != info["sha256"] or path.stat().st_size != info["size_bytes"]:
                raise ValueError(f"Historic artifact differs: {path}")
            names.add(path.relative_to(root).as_posix())
    # Minimal real data for a full train-only notebook replay. Validation IDs
    # have no feature/target measurements; no test file is opened or included.
    data_names = {"data/processed/samples_full/train.csv",
                  "data/processed/samples_full/sample_ids/train.csv",
                  "data/processed/samples_full/sample_ids/validation.csv"}
    manifest = read(root / "reports/splits_full/split_manifest.json")
    checked = set()
    for info in manifest["files"].values():
        if info["path"] in data_names:
            path = safe_path(root, info["path"])
            if sha(path) != info["sha256"] or path.stat().st_size != info["bytes"]:
                raise ValueError("Bundled train data/IDs differ from T05")
            checked.add(info["path"])
    if checked != data_names: raise ValueError("Missing T05 data provenance")
    names.update(data_names)
    qa_path = root / "reports/submission/qa.json"
    if not qa_path.is_file(): qa_path = root.parent / "resources/qa.json"
    if qa_path.is_file():
        for info in read(qa_path).get("replay_files", []):
            name = info["path"]
            if not name.startswith(("reports/eda_train_mk02_", "reports/figures/eda_train_mk02_",
                                    "artifacts/t06_runtime/executed_full_mk02_")):
                raise ValueError("Unexpected QA replay path")
            if sha(safe_path(root, name)) != info["sha256"]:
                raise ValueError("QA replay checksum differs")
            names.add(name)
    for name in names:
        path = safe_path(root, name)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing file or symlink: {name}")
        if not allowed(name) and name not in data_names:
            raise ValueError(f"Forbidden source file: {name}")
    return sorted(names), rows


def workbook(rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "Actual run history"
    keys = ["run_id", "task_id", "mode", "kind", "status", "reference_run_id", "parent_run_id", "fold_id", "started_at", "duration_seconds"]
    sheet.append(keys + ["metrics_json", "config_json", "metadata_json"])
    for row in rows:
        sheet.append([row[k] for k in keys] + ["metrics", "config", "metadata"])
        for col, kind in enumerate(("metrics", "config", "metadata"), len(keys)+1):
            cell = sheet.cell(sheet.max_row, col)
            cell.hyperlink = f"../source/artifacts/experiments/{row['run_id']}/{kind}.json"
            cell.style = "Hyperlink"
    for cell in sheet[1]: cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for col in sheet.columns:
        sheet.column_dimensions[col[0].column_letter].width = min(40, max(15, len(str(col[0].value))+3))
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names, rows = inventory(ROOT)
    before = sha(ROOT / "experiments/experiment_log.csv")
    evidence = read(ROOT / "reports/midterm/evidence.json")
    content = {"source/"+n: ROOT / n for n in names}
    for ext, folder in (("docx", "report"), ("pptx", "slides")):
        content[f"{folder}/{STEM}.{ext}"] = ROOT / f"reports/midterm/{STEM}.{ext}"
    content["report/report.pdf"] = ROOT / "reports/midterm/previews/report.pdf"
    content["slides/slides.pdf"] = ROOT / "reports/midterm/previews/slides.pdf"
    for name in names:
        if name.endswith(".png") and name.startswith(("reports/figures/", "reports/midterm/figures/")):
            content["figures/"+name.removeprefix("reports/")] = ROOT / name
    content["experiment_logs/run_index.xlsx"] = workbook(rows)
    content["experiment_logs/README.md"] = ("# Canonical log\n\nThe unchanged CSV is ../source/experiments/experiment_log.csv.\n"
        "Keep source/experiments/ beside source/artifacts/: CSV links are relative to that folder.\n"
        "The derived Excel index links to the same real JSON files. Rows include smoke, parents, candidates and folds; they are not independent models.\n").encode()
    content["resources/data_provenance.json"] = (ROOT / "reports/data_manifest.json")
    split_manifest = read(ROOT / "reports/splits_full/split_manifest.json")
    omitted = [{**info, "reason": "Not needed for train-only EDA/metric verification; holdout remains locked where applicable"}
               for info in split_manifest["files"].values() if info["path"] not in names]
    content["resources/reproduction_scope.json"] = json.dumps({
        "verified_scope": "Install/import, train notebook and existing predictions/metrics; no new model fit",
        "omitted_t05_files": omitted,
        "optional_feature_cache": "T07 matrices are omitted; recipes/configs are in source. Rebuild only for an authorized future task.",
        "raw_data": "Official download URL, CC BY 4.0 and SHA-256 are in data_provenance.json; no raw bundled.",
        "historical_absolute_paths": "Some immutable run metadata records the original author's environment. Portable artifact links use the relative registry paths, not these history fields."
    }, ensure_ascii=False, indent=2).encode("utf-8")
    content["resources/model_status.json"] = json.dumps({
        "selected_run_id": evidence["frozen"]["selected_run_id"],
        "weights_included": False, "reason": "No serialized model weights were saved by historical runs. Recipe only; T13 not executed.",
        "frozen_config": "../source/reports/ablation/frozen_model.json"}, indent=2).encode()
    content["README.md"] = (ROOT / "docs/submission_checklist.md")
    qa = OUT / "qa.json"
    if not qa.is_file(): qa = ROOT.parent / "resources/qa.json"
    if qa.is_file(): content["resources/qa.json"] = qa
    constraints = OUT / "constraints.txt"
    if not constraints.is_file(): constraints = ROOT.parent / "resources/constraints.txt"
    if not constraints.is_file(): raise ValueError("Record tested dependency constraints before packaging")
    content["resources/constraints.txt"] = constraints
    files = []
    for name, value in sorted(content.items()):
        payload = value.read_bytes() if isinstance(value, Path) else value
        files.append({"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    manifest = {"schema_version": "mk02-submission-v1", "task_id": "MK02", "draft": True,
        "ready_to_submit": False, "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() if not (ROOT.parent / "resources/submission_manifest.json").is_file() else None,
        "source_snapshot": "SHA-256 for every exact included file; commit is the base and may precede MK02 working changes",
        "missing_group_fields": evidence["missing"], "ledger_sha256": before,
        "runs": len(rows), "model_fit_performed": False, "test_samples_accessed": False,
        "raw_data_included": False, "dataset_provenance": "resources/data_provenance.json",
        "test_access_note": "Existing split count/date audit only. No test samples, predictions or new test metrics.",
        "manifest_note": "files covers every payload except this manifest itself; ZIP SHA-256 is the external sidecar.",
        "files": files}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2)+"\n").encode("utf-8")
    content["resources/submission_manifest.json"] = manifest_bytes
    path = OUT / (STEM+".zip")
    pending = path.with_suffix(".zip.partial")
    with zipfile.ZipFile(pending, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, value in sorted(content.items()):
            target = STEM+"/"+name
            if isinstance(value, Path): archive.write(value, target)
            else: archive.writestr(target, value)
    pending.replace(path)
    if sha(ROOT / "experiments/experiment_log.csv") != before: raise RuntimeError("Ledger changed")
    (OUT / "submission_manifest.json").write_bytes(manifest_bytes)
    (OUT / (STEM+".zip.sha256")).write_text(sha(path)+"  "+path.name+"\n", encoding="ascii", newline="\n")
    print(json.dumps({"zip": path.name, "bytes": path.stat().st_size, "files": len(content), "runs": len(rows), "draft": True}))


if __name__ == "__main__": main()
