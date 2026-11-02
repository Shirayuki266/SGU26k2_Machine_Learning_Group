"""Verify saved T06 tables, PNGs and clean notebook outputs against train only."""

import argparse
import ast
import base64
import hashlib
from io import StringIO
from pathlib import Path
import sys

import nbformat
import pandas as pd
from pandas.testing import assert_frame_equal

from beijing_air import eda
from beijing_air.data import sha256


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="reports/eda_train")
    parser.add_argument("--notebook", default="notebooks/01_train_eda.ipynb")
    args = parser.parse_args()
    report = eda.project_path(root, args.report)
    manifest = eda.read_json(report / "eda_manifest.json")
    assert manifest["status"] == "complete" and manifest["task_id"] == "T06"
    assert not manifest["model_experiment_run"] and not manifest["test_accessed"]
    for key, path in (("module_sha256", Path(eda.__file__)), ("eda_config_sha256", root / "configs/eda.json"),
                      ("default_config_sha256", root / "configs/default.json"), ("quality_config_sha256", root / "configs/data_quality.json")):
        assert sha256(path) == manifest[key], f"Code/config changed: {path}"
    for info in manifest["files"]:
        path = eda.project_path(root, info["path"])
        assert path.stat().st_size == info["bytes"] and sha256(path) == info["sha256"], path
        if path.suffix == ".png":
            assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), path
    data, provenance = eda.load_training_data(root, manifest["provenance"]["split_manifest"])
    assert provenance == manifest["provenance"]
    assert len(data) == manifest["source_train_rows"]
    if manifest["mode"] == "smoke":
        data = data.groupby("station", sort=True).head(manifest["config"]["smoke_rows_per_station"])
    assert len(data) == manifest["analyzed_rows"] and data.is_primary.sum() == manifest["primary_rows"]
    tables = eda.build_tables(data, eda.read_json(root / "configs/data_quality.json")["review_ranges"],
                              tuple(manifest["config"]["autocorrelation_lags_hours"]))
    for name, computed in tables.items():
        # Same CSV representation handles dates, NA and schema strings uniformly.
        expected = pd.read_csv(StringIO(computed.to_csv(index=False, na_rep="NA")))
        saved = pd.read_csv(report / f"{name}.csv")
        assert_frame_equal(saved, expected, check_dtype=False, rtol=1e-10, atol=1e-10)
    index = pd.read_csv(report / "figure_index.csv")
    captions = eda.findings(tables, provenance)
    assert set(index.figure_id) == set(captions) and not index.figure_id.duplicated().any()
    for row in index.itertuples():
        assert row.commentary_vi == captions[row.figure_id]
        assert eda.project_path(root, row.path).is_file()
    notebook = nbformat.read(eda.project_path(root, args.notebook), as_version=4)
    nbformat.validate(notebook)
    cells = [c for c in notebook.cells if c.cell_type == "code"]
    assert [c.execution_count for c in cells] == list(range(1, len(cells)+1))
    assert not any(o.output_type == "error" for c in cells for o in c.outputs)
    parameters = next(c for c in cells if "parameters" in c.metadata.get("tags", []))
    values = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(parameters.source).body}
    assert values["MODE"] == manifest["mode"] and values["SPLIT_MANIFEST"] == provenance["split_manifest"]
    rendered_pngs = [o["data"]["image/png"] for c in cells for o in c.outputs
                     if o.output_type in ("display_data", "execute_result") and "image/png" in o.get("data", {})]
    assert len(rendered_pngs) == len(index)
    for embedded, path in zip(rendered_pngs, index.path):
        assert hashlib.sha256(base64.b64decode(embedded)).hexdigest() == sha256(eda.project_path(root, path))
    print(f"PASS: {len(tables)} tables recomputed from train; {len(index)} PNGs/captions; {len(cells)} executed notebook cells; checksums intact")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
