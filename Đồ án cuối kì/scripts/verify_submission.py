"""Verify ZIP paths/CRC/SHA, real runs and report evidence without training.

Extraction is explicit and only to a new directory; no existing tree is replaced.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

from openpyxl import load_workbook

from beijing_air.midterm_evidence import collect, read, sha
# Embedded Python's ._pth may omit the script directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_midterm import verify_office


def check_zip(path, destination):
    destination = Path(destination).resolve()
    if destination.exists(): raise ValueError("Extraction destination must not exist")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(n.casefold() for n in names)):
            raise ValueError("Duplicate or case-colliding ZIP names")
        if len(names) > 5000 or sum(i.file_size for i in archive.infolist()) > 2_000_000_000:
            raise ValueError("Unexpected package size")
        roots = set()
        for info in archive.infolist():
            # ZipInfo.filename normalizes foreign backslashes on Windows;
            # inspect the original header name before trusting that normalization.
            name = info.orig_filename
            p = PurePosixPath(name)
            if "\\" in name or ":" in name or p.is_absolute() or ".." in p.parts:
                raise ValueError("Unsafe ZIP path")
            if not p.parts or any(c in p.parts for c in (".git", ".venv", "__pycache__", ".aws", ".codex", ".agents")):
                raise ValueError("Forbidden ZIP entry")
            if stat.S_ISLNK(info.external_attr >> 16): raise ValueError("ZIP symlink")
            roots.add(p.parts[0])
        if len(roots) != 1: raise ValueError("Expected one submission root")
        prefix = next(iter(roots))+"/"
        manifest_name = prefix+"resources/submission_manifest.json"
        manifest = json.loads(archive.read(manifest_name))
        expected = {prefix+i["path"] for i in manifest["files"]} | {manifest_name}
        if expected != set(names): raise ValueError("Manifest/file coverage differs")
        if archive.testzip() is not None: raise ValueError("ZIP CRC failed")
        for info in manifest["files"]:
            payload = archive.read(prefix+info["path"])
            if len(payload) != info["bytes"] or hashlib.sha256(payload).hexdigest() != info["sha256"]:
                raise ValueError(f"ZIP checksum differs: {info['path']}")
        # No future partition measurements or downloaded data are allowed.
        for name in names:
            if "/source/data/raw/" in name and not name.endswith(".gitkeep"):
                raise ValueError("Raw data unexpectedly included")
            if name.endswith(("samples_full/test.csv", "samples_full/validation.csv", "sample_ids/test.csv")):
                raise ValueError("Holdout samples unexpectedly included")
        destination.mkdir(parents=True)
        archive.extractall(destination)
    return destination / prefix.rstrip("/"), manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--extract-to", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package, manifest = check_zip(args.zip, args.extract_to)
    root = package / "source"
    before = sha(root / "experiments/experiment_log.csv")
    evidence = collect(root)
    _, _, office = verify_office(root)
    frozen = read(root / "reports/ablation/frozen_model.json")
    if frozen["selected_run_id"] != evidence["frozen"]["selected_run_id"]:
        raise ValueError("Frozen model differs")
    book = load_workbook(package / "experiment_logs/run_index.xlsx")
    sheet = book.active
    if sheet.max_row != manifest["runs"]+1: raise ValueError("Excel/CSV row count differs")
    for row in sheet.iter_rows(min_row=2):
        for cell in row[-3:]:
            target = (package / "experiment_logs" / cell.hyperlink.target).resolve()
            if not target.is_relative_to(package) or not target.is_file():
                raise ValueError("Excel link is broken")
    for doc in ("docx", "pptx"):
        folder = "report" if doc == "docx" else "slides"
        if sha(package / folder / f"{package.name}.{doc}") != sha(root / "reports/midterm" / f"{package.name}.{doc}"):
            raise ValueError("Convenience document differs from canonical copy")
    if sha(root / "experiments/experiment_log.csv") != before or before != manifest["ledger_sha256"]:
        raise ValueError("Historic ledger changed")
    if not manifest["draft"] or manifest["ready_to_submit"]:
        raise ValueError("This package must remain a draft until group information is supplied")
    result = {"task_id": "MK02", "checked_at": datetime.now(timezone.utc).isoformat(),
              "status": "DRAFT_CHECKED", "ready_to_submit": False,
              "zip_sha256": sha(args.zip), "zip_bytes": args.zip.stat().st_size,
              "files_including_manifest": len(manifest["files"])+1,
              "zip_crc_paths_checksums": "PASS", "excel_links": "PASS",
              "evidence": evidence["checks"], "office": office,
              "common_validation_ids": "PASS: six full runs, same ordered primary IDs",
              "ledger_unchanged": before, "model_fit_performed": False,
              "test_samples_accessed": False, "missing": manifest["missing_group_fields"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": main()
