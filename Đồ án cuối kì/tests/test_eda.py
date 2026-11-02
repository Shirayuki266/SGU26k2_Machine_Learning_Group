"""TEST_ONLY fixtures; no real train/validation/test files or model fits."""

import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from beijing_air.data import MEASUREMENTS, sha256
from beijing_air.eda import (
    build_tables, exact_hour_autocorrelation, ids_digest, load_training_data,
    plot_figures, read_json, run_eda, validate_training_frame,
)
from beijing_air.samples import ID_COLUMNS, build_samples


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def train():
    records = []
    for station, offset in (("TEST_ONLY_A", 0), ("TEST_ONLY_B", 30)):
        for hour in [0, 1, 2, 4, 5, 6, 7, 8, 9]:
            row = {name: float(hour + offset + 1) for name in MEASUREMENTS}
            row.update(station=station, timestamp=pd.Timestamp("2014-01-01")+pd.Timedelta(hours=hour),
                       wd="N" if hour % 2 else None, PRES=1010., TEMP=-5., DEWP=-7.)
            if hour == 5:
                row["PM2.5"] = None
            if hour == 7:
                row["PM2.5"] = 999.
            records.append(row)
    return build_samples(pd.DataFrame(records)).samples.assign(split="train")


@pytest.fixture
def snapshot(tmp_path, train):
    """Minimal complete TEST_ONLY T05 train; holdout paths deliberately invalid."""
    (tmp_path / "configs").mkdir()
    for name in ("default.json", "eda.json", "data_quality.json"):
        shutil.copyfile(ROOT / "configs" / name, tmp_path / "configs" / name)
    (tmp_path / "data/sample_ids").mkdir(parents=True)
    train.to_csv(tmp_path / "data/train.csv", index=False, na_rep="NA")
    train[ID_COLUMNS].to_csv(tmp_path / "data/sample_ids/train.csv", index=False, na_rep="NA")
    files = {}
    for name, relative in (("train_samples", "data/train.csv"), ("train_ids", "data/sample_ids/train.csv")):
        p = tmp_path / relative
        files[name] = {"path": relative, "sha256": sha256(p), "bytes": p.stat().st_size}
    files["test_samples"] = {"path": "TEST_ONLY_DO_NOT_OPEN/test.csv"}
    files["validation_samples"] = {"path": "TEST_ONLY_DO_NOT_OPEN/validation.csv"}
    membership = {}
    for cohort, subset in (("operational", train), ("primary", train.loc[train.is_primary])):
        membership[cohort] = {"samples": len(subset), "ordered_sample_ids_sha256": ids_digest(subset.sample_id)}
    manifest = {"task_id": "T05", "status": "complete", "mode": "full", "snapshot_id": "TEST_ONLY",
                "signature": {"split": read_json(tmp_path / "configs/default.json")["split"]},
                "files": files, "membership": {"train": membership}}
    (tmp_path / "reports/splits_full").mkdir(parents=True)
    path = tmp_path / "reports/splits_full/split_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, path, manifest


def test_loader_reads_only_train_files_and_matches_membership(snapshot, monkeypatch):
    root, _, _ = snapshot
    opened = []
    original = Path.open
    def tracked(path, *args, **kwargs):
        opened.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", tracked)
    data, provenance = load_training_data(root)
    assert data.split.eq("train").all()
    assert len(provenance["input_files_read"]) == 2
    assert not any("DO_NOT_OPEN" in p for p in opened)
    assert data["PM2.5"].max() == 999


@pytest.mark.parametrize("kind", ["checksum", "membership", "escape", "holdout", "split_protocol"])
def test_loader_rejects_untrusted_snapshot(snapshot, kind):
    root, path, manifest = snapshot
    if kind == "checksum":
        (root / "data/train.csv").write_text("TEST_ONLY tampered", encoding="utf-8")
    elif kind == "membership":
        manifest["membership"]["train"]["primary"]["samples"] += 1
    elif kind == "escape":
        manifest["files"]["train_samples"]["path"] = "../outside/train.csv"
    elif kind == "holdout":
        manifest["files"]["train_samples"]["path"] = "data/test.csv"
    else:
        manifest["signature"]["split"]["validation_start"] = "2020-01-01"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        load_training_data(root)


@pytest.mark.parametrize("kind", ["split", "boundary", "target_hour", "duplicate_id", "primary", "missing_target"])
def test_frame_contract_blocks_holdouts_and_bad_targets(train, kind):
    data = train.copy()
    if kind == "split": data.loc[0, "split"] = "test"
    elif kind == "boundary":
        data["input_timestamp"] += pd.Timedelta(days=800)
        data["target_timestamp"] += pd.Timedelta(days=800)
    elif kind == "target_hour": data.loc[0, "target_timestamp"] += pd.Timedelta(hours=1)
    elif kind == "duplicate_id": data.loc[0, "sample_id"] = data.loc[1, "sample_id"]
    elif kind == "primary": data.loc[0, "is_primary"] = not data.loc[0, "is_primary"]
    else: data.loc[0, "target_pm25"] = np.nan
    with pytest.raises(ValueError):
        validate_training_frame(data, validation_start="2015-03-01")


def test_tables_reconcile_missing_outliers_counts_and_never_mutate(train):
    before = train.copy(deep=True)
    ranges = read_json(ROOT / "configs/data_quality.json")["review_ranges"]
    tables = build_tables(train, ranges)
    summary = tables["numeric_summary"].set_index("column")
    assert summary.loc["PM2.5", "max"] == 999
    assert summary.loc["PM2.5", "review_flags"] == 2
    assert summary.loc["PM2.5", "missing"] == train["PM2.5"].isna().sum()
    assert summary["physical_invalid"].eq(0).all()
    assert tables["hourly"].rows.sum() == len(train)
    assert tables["station_summary"].primary.sum() == train.is_primary.sum()
    assert tables["daily_station"].observed.sum() == train["PM2.5"].notna().sum()
    assert tables["correlation_pairs"].set_index("column").loc["PM2.5", "target_pm25"] == train["PM2.5"].notna().sum()
    assert pd.isna(tables["pearson"].set_index("column").loc["PRES", "PM2.5"])
    assert tables["sample_gaps"].absent_supervised_origins.gt(0).all()
    assert_frame_equal(train, before)


def test_exact_hour_autocorrelation_never_bridges_gaps_or_stations():
    a = pd.DataFrame({"station": "TEST_ONLY_A", "input_timestamp": pd.to_datetime([
        "2014-01-01 00:00", "2014-01-01 01:00", "2014-01-01 03:00", "2014-01-01 04:00", "2014-01-01 05:00"]), "PM2.5": [1., 2., 100., 7., 9.]})
    b = a.assign(station="TEST_ONLY_B", **{"PM2.5": [99., 99., 99., 99., 99.]})
    result = exact_hour_autocorrelation(pd.concat([a, b], ignore_index=True), (1, 2)).set_index(["station", "lag_hours"])
    assert result.loc[("TEST_ONLY_A", 1), "pairs"] == 3
    assert result.loc[("TEST_ONLY_A", 1), "pearson_r"] == pytest.approx(pd.Series([2., 7., 9.]).corr(pd.Series([1., 100., 7.])))
    assert result.loc[("TEST_ONLY_A", 2), "pairs"] == 2
    assert pd.isna(result.loc[("TEST_ONLY_B", 1), "pearson_r"])


def test_test_only_export_png_index_checksums_and_no_overwrite(snapshot, monkeypatch):
    root, _, _ = snapshot
    monkeypatch.setenv("MPLCONFIGDIR", str(root / "TEST_ONLY_mpl"))
    result = run_eda(root, mode="smoke", output_tag="TEST_ONLY")
    manifest = result["manifest"]
    assert manifest["model_experiment_run"] is False and manifest["test_accessed"] is False
    assert manifest["mode"] == "smoke" and manifest["analyzed_rows"] == len(result["data"])
    for text_file in ("figure_index.md", "eda_manifest.json"):
        assert b"\r\n" not in (result["report_directory"] / text_file).read_bytes()
    for info in manifest["files"]:
        assert sha256(root / info["path"]) == info["sha256"]
    for fig in result["figures"]:
        assert (root / fig["path"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert fig["commentary_vi"]
    with pytest.raises(FileExistsError):
        run_eda(root, mode="smoke", output_tag="TEST_ONLY")
