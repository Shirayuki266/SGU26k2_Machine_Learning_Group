"""Generate the T15 final report, presentation, poster, and indexes."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from beijing_air.final_deliverables import build_final_deliverables


if __name__ == "__main__":
    build_final_deliverables(ROOT)
