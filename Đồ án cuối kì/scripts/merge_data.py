"""Merge raw PRSA2017 files and persist quality audits before any imputation."""

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from beijing_air.data import DataQualityError, load_station_data, sha256, validate_temporal_integrity


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "configs/default.json")
    parser.add_argument("--quality-config", type=Path, default=root / "configs/data_quality.json")
    parser.add_argument("--mode", choices=["smoke", "full"])
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace this mode's generated outputs")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    quality = json.loads(args.quality_config.read_text(encoding="utf-8-sig"))
    mode = args.mode or config["mode"]
    if mode not in ["smoke", "full"]:
        parser.error("Config mode must be smoke or full")
    raw = root / config["paths"]["raw_data"]
    processed = root / config["paths"]["processed_data"]
    reports = root / "reports" / f"quality_{mode}"
    merged = processed / f"merged_unimputed_{mode}.csv"
    if not args.overwrite and (merged.exists() or (reports.exists() and any(reports.iterdir()))):
        parser.error("Generated output exists; use --overwrite to explicitly replace it")
    manifest = json.loads((root / "reports/data_manifest.json").read_text(encoding="utf-8-sig"))
    expected_hashes = {Path(item["path"]).name: item["sha256"] for item in manifest["files"]}
    paths = sorted(raw.glob("PRSA_Data_*_20130301-20170228.csv"))
    failed = False
    try:
        result = load_station_data(paths, rows_per_file=quality["smoke_rows_per_file"] if mode == "smoke" else None,
                                   review_ranges=quality["review_ranges"], expected_hashes=expected_hashes,
                                   expected_start=quality["expected_start"] if mode == "full" else None,
                                   expected_end=quality["expected_end"] if mode == "full" else None)
    except DataQualityError as exc:
        result = exc.result
        failed = True
    reports.mkdir(parents=True, exist_ok=True)
    result.issues.to_csv(reports / "issues.csv", index=False)
    result.stations.to_csv(reports / "stations.csv", index=False)
    result.summary.update(mode=mode, seed=config["seed"], audited_at=datetime.now(timezone.utc).isoformat(),
                          python_version=platform.python_version(), pandas_version=pd.__version__,
                          quality_config=quality, status="failed" if failed else "passed", merged_output_written=False)
    if failed:
        # Never leave a previously approved output beside a failed fresh audit.
        if merged.exists():
            merged.unlink()
        (reports / "summary.json").write_text(json.dumps(result.summary, indent=2, ensure_ascii=False), encoding="utf-8")
        raise SystemExit(f"Quality errors; inspect {reports}. No merged output published.")
    validate_temporal_integrity(result.data)
    processed.mkdir(parents=True, exist_ok=True)
    result.data.to_csv(merged, index=False, na_rep="NA", date_format="%Y-%m-%d %H:%M:%S")
    result.summary.update(merged_output_written=True, merged_sha256=sha256(merged))
    (reports / "summary.json").write_text(json.dumps(result.summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{mode}: {len(result.data):,} rows; {result.summary['error_count']} errors; {result.summary['warning_count']} warnings")
    print(f"Merged: {merged}\nAudit: {reports}")


if __name__ == "__main__":
    main()
