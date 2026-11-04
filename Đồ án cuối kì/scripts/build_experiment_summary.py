"""T17a: read existing runs/predictions and export deterministic summary tables."""

import argparse
import json
from pathlib import Path

from beijing_air.experiment_summary import Reader, build_summary, export_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", default="reports/tables")
    parser.add_argument("--no-plans", action="store_true", help="Omit empty T17b/ensemble placeholders")
    args = parser.parse_args()
    reader = Reader(args.root)
    before = reader.ledger.read_bytes()
    rows, evidence = build_summary(reader, include_plans=not args.no_plans)
    report = export_summary(reader, rows, evidence, output=args.output)
    if reader.ledger.read_bytes() != before:
        raise AssertionError("Official experiment log changed during summary generation")
    counts = {status: sum(c["status"] == status for c in report["checks"]) for status in ("OK", "KHÁC", "CHƯA CÓ")}
    print(json.dumps({"task": "T17a", "rows": len(rows), "ledger_records": report["ledger_rows"],
                      "checks": counts, "xlsx": report["xlsx_available"], "output": args.output,
                      "new_runs": 0, "training": False, "raw_test_samples_read": False}, ensure_ascii=True))


if __name__ == "__main__":
    main()
