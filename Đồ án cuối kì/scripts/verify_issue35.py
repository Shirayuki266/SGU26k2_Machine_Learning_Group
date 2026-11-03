"""TEST_ONLY before/after compatibility check; no dataset reads, fit or model log."""

import argparse
import hashlib
import inspect
import json
from importlib.metadata import version
from pathlib import Path
import platform
import sys

import joblib
import numpy as np
import pandas as pd

from beijing_air.data import sha256
from beijing_air.demo import load_demo_model, model_fingerprint
from beijing_air.eda import read_json
from beijing_air.final_evaluation import validate_frozen, write_json
from beijing_air.preprocessing import FeatureSchema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_issue35 import fixed_features  # Synthetic features only; imports never fit/read data.


def snapshot():
    model = load_demo_model(ROOT)
    state = read_json(ROOT / "reports/final_evaluation/execution.json")
    pipelines = {name: joblib.load(ROOT / "artifacts/experiments" / state["child_run_ids"][name] / "artifacts/model/pipeline.joblib")
                 for name in ("ridge", "random_forest")}
    protected = [*sorted((ROOT / "configs").glob("*.json")), ROOT / "experiments/experiment_log.csv",
                 ROOT / "reports/ablation/frozen_model.json", ROOT / "reports/final_evaluation/final_model.json",
                 ROOT / "reports/final_evaluation/execution.json", ROOT / "reports/final_evaluation/t13_runs.zip"]
    for rid in state["child_run_ids"].values():
        folder = ROOT / "artifacts/experiments" / rid
        protected.extend(folder / name for name in ("config.json", "metadata.json", "metrics.json"))
        if (folder / "artifacts/model/pipeline.joblib").is_file():
            protected.append(folder / "artifacts/model/pipeline.joblib")
    cases = {}
    for dtype in ("object", "string[python]", "string[pyarrow]"):
        for kind in ("valid", "mixed_missing_unknown"):
            x = fixed_features(model, dtype)
            if kind == "mixed_missing_unknown":
                x.loc[x.index[0], "wd"] = "TEST_ONLY_UNSEEN_WIND"
                x.loc[x.index[1], "wd"] = pd.NA
            cases[f"{dtype}:{kind}"] = {
                "fixture_sha256": hashlib.sha256(x.to_json(orient="split").encode()).hexdigest(),
                "sample_ids": x.index.tolist(),
                "predictions": {name: pipeline.predict(x).tolist() for name, pipeline in pipelines.items()}}
    # The old guard already works for object all-missing: preserve this reference.
    x = fixed_features(model)
    x["wd"] = pd.Series([np.nan]*len(x), index=x.index, dtype=object)
    cases["object:all_missing"] = {
        "fixture_sha256": hashlib.sha256(x.to_json(orient="split").encode()).hexdigest(),
        "sample_ids": x.index.tolist(),
        "predictions": {name: pipeline.predict(x).tolist() for name, pipeline in pipelines.items()}}
    design = read_json(ROOT / "configs/final_evaluation.json")
    try:
        validate_frozen(ROOT, design)  # Reads pinned code/config metadata, not sample CSVs.
        gate = {"accepted": True, "error": None}
    except ValueError as error:
        gate = {"accepted": False, "error": str(error)}
    return {
        "issue": 35, "artifact_type": "TEST_ONLY_fixture_compatibility_not_experiment",
        "environment": {"python": platform.python_version(), **{p: version(p) for p in ("pandas", "numpy", "scikit-learn", "joblib", "pyarrow")}},
        "source_sha256": sha256(ROOT / "src/beijing_air/preprocessing.py"),
        "guard_source_sha256": hashlib.sha256(inspect.getsource(FeatureSchema._validated).encode()).hexdigest(),
        "class_path": FeatureSchema.__module__+"."+FeatureSchema.__qualname__,
        "constructor_signature": str(inspect.signature(FeatureSchema)),
        "package_version": version("beijing-air-quality"),
        "fitted_state_hashes": {name: joblib.hash(pipeline) for name, pipeline in pipelines.items()},
        "protected_files_sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in protected},
        "T14_model_cache_fingerprint": model_fingerprint(ROOT),
        "T13_frozen_source_gate": gate,
        "cases": cases, "data_scope": "synthetic TEST_ONLY fixture; no train/validation/test samples or saved predictions read",
        "fit_calls": 0, "model_artifacts_rewritten": False, "experiment_log_written": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/issue35")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to(ROOT):
        parser.error("Keep TEST_ONLY evidence inside the project")
    before_path = output / "before.json"
    target = output / (args.phase+".json")
    if target.exists():
        raise FileExistsError("Evidence exists; choose a new output directory rather than overwrite")
    current = snapshot()
    if args.phase == "before":
        assert current["T13_frozen_source_gate"]["accepted"]
    else:
        before = read_json(before_path)
        for key in ("environment", "class_path", "constructor_signature", "package_version", "protected_files_sha256", "T14_model_cache_fingerprint"):
            assert before[key] == current[key], key
        assert before["source_sha256"] != current["source_sha256"]
        assert current["T13_frozen_source_gate"] == {
            "accepted": False, "error": "Frozen input changed: src/beijing_air/preprocessing.py"}
        maximum = 0.
        count = 0
        for name, expected in before["cases"].items():
            actual = current["cases"][name]
            assert actual["fixture_sha256"] == expected["fixture_sha256"]
            assert actual["sample_ids"] == expected["sample_ids"]
            for model, values in expected["predictions"].items():
                np.testing.assert_allclose(actual["predictions"][model], values, rtol=0, atol=1e-12)
                maximum = max(maximum, float(np.max(np.abs(np.asarray(values)-actual["predictions"][model]))))
                count += len(values)
        current["comparison"] = {"status": "PASS", "prediction_values_compared": count,
                                 "rtol": 0, "atol": 1e-12, "max_absolute_difference": maximum,
                                 "frozen_gate_change_expected": True,
                                 "action": "Keep T13 source fingerprint immutable; replay old verification at its commit. Restart app after code update; no automatic artifact migration."}
        current["in_memory_hash_caveat"] = (
            "RF joblib.hash varies across independent loads of the same file due to node-buffer padding; "
            "not used as a cross-process equality assertion. Immutable weight-file SHA and fixture "
            "predictions are compared; tests check each instance unchanged within its own lifecycle. "
            "See hash_diagnostic.json for a two-load check with equal named tree fields.")
    write_json(target, current)
    print(json.dumps({"phase": args.phase, "output": target.relative_to(ROOT).as_posix(),
                      "comparison": current.get("comparison"), "source_gate": current["T13_frozen_source_gate"]}))


if __name__ == "__main__":
    main()
