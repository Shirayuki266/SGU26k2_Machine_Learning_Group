"""Run from project root: python -m streamlit run app/streamlit_app.py."""

from pathlib import Path

from beijing_air.demo_ui import render


render(Path(__file__).resolve().parents[1])
