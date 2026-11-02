"""Check the installed package and initial dependencies without loading data."""

from importlib import import_module
from importlib.metadata import version
import platform
import sys


MODULES = (
    "beijing_air",
    "pandas",
    "numpy",
    "sklearn",
    "matplotlib",
    "seaborn",
    "joblib",
    "streamlit",
    "pytest",
    "jupyter",
)
DIST_NAMES = {"beijing_air": "beijing-air-quality", "sklearn": "scikit-learn"}


def main():
    # Paths in this project contain Vietnamese; keep captured output readable
    # on Windows even when the console's default code page is different.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"Python {platform.python_version()} ({platform.python_implementation()})")
    print(f"Executable: {sys.executable}")
    failures = []
    for name in MODULES:
        try:
            module = import_module(name)
            installed_version = version(DIST_NAMES.get(name, name))
        except Exception as exc:
            failures.append(name)
            print(f"FAIL {name}: {exc}")
        else:
            print(f"OK   {name}: {installed_version}")
            if name == "beijing_air":
                print(f"     Source: {module.__file__}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
