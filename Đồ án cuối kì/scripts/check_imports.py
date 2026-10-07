"""Check the installed package and initial dependencies without loading data."""

from importlib import import_module


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


def main():
    failures = []
    for name in MODULES:
        try:
            import_module(name)
        except Exception as exc:
            failures.append(name)
            print(f"FAIL {name}: {exc}")
        else:
            print(f"OK   {name}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
