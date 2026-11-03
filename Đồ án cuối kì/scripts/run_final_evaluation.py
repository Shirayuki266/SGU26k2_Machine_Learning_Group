"""Preflight without test, or execute the locked T13 plan exactly once."""

import argparse
import json
from pathlib import Path
import sys

from beijing_air.final_evaluation import execute, preflight, write_json


def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight",action="store_true")
    group.add_argument("--execute",action="store_true")
    parser.add_argument("--technical-retry-reason")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if args.preflight:
        result=preflight(root)
        write_json(root / "reports/final_evaluation/preflight_before_test.json",result)
    else:
        result=execute(root,retry_reason=args.technical_retry_reason)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":main()
