"""Run the predeclared T17b experiments without opening test data."""

import argparse
import json
from pathlib import Path

from beijing_air.supplementary_experiments import run_supplementary_experiments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("smoke", "full"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = run_supplementary_experiments(args.root, mode=args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
