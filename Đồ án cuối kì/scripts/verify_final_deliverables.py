"""Verify T15 Office deliverables, provenance, and protected project history."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from beijing_air.final_deliverables import verify_final_deliverables


if __name__ == "__main__":
    verify_final_deliverables(ROOT)
