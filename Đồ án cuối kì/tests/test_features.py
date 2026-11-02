"""TEST_ONLY causal fixtures; no real holdouts, preprocessing fit, or models."""

import json
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from beijing_air.data import MEASUREMENTS, RAW_COLUMNS, load_station_data, sha256
from beijing_air.features import build_features, feature_registry, features_for_prediction, missing_summary
from beijing_air.samples import ID_COLUMNS, _sample_id, build_samples
from beijing_air.eda import ids_digest, read_json


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return read_json(ROOT / "configs/default.json")


def observations(stations=("TEST_ONLY_A", "TEST_ONLY_B"), start="2014-01-01", periods=40):
    records = []
    for number, station in enumerate(stations):
        for hour, timestamp in enumerate(pd.date_range(start, periods=periods, freq="h")):
            row = {name: float(100+1000*number+hour) for name in MEASUREMENTS}
            row.update(station=station, timestamp=timestamp, wd="N", PRES=1010., TEMP=10., DEWP=5.)
            records.append(row)
    return pd.DataFrame(records)


def requests(history, hours):
    rows = []
    for station, group in history.groupby("station", sort=True):
        start = group.timestamp.min()
        for hour in hours:
            origin = start+pd.Timedelta(hours=hour)
            target = origin+pd.Timedelta(hours=1)
            rows.append({"sample_id": _sample_id(station, origin, target), "station": station,
                         "input_timestamp": origin, "target_timestamp": target})
    return pd.DataFrame(rows)


def test_registry_allowlist_current_lags_and_rolling_are_exact(config):
    registry = feature_registry(config)
    result = build_features(observations(), requests(observations(), [30]), config=config)
    assert len(result.select("A").columns) == 20 and len(result.select("B").columns) == 33
    assert registry.feature_name.tolist() == result.features.columns.tolist()
    assert registry.available_by.eq("origin_t").all()
    assert not set(["target_pm25", "sample_id", "target_timestamp", "input_timestamp", "source_row", "No", "hour"]).intersection(result.features)
    assert "pm25_lag_2h" not in result.features
    x = result.features.iloc[0]
    for lag in (1, 3, 6, 12, 24):
        assert x[f"pm25_lag_{lag}h"] == 130-lag
        assert result.features.iloc[1][f"pm25_lag_{lag}h"] == 1130-lag
    assert x.pm25_roll_mean_3h == 129 and x.pm25_roll_std_3h == pytest.approx(1.)
    assert x.pm25_roll_mean_24h == pytest.approx(np.mean(np.arange(107, 131)))
    assert x.pm25_roll_std_24h == pytest.approx(np.std(np.arange(107, 131), ddof=1))


def test_gap_is_not_previous_row_and_never_creates_requested_samples(config):
    history = observations()
    history = history.loc[history.timestamp.ne(pd.Timestamp("2014-01-01 20:00"))]
    request = requests(history, [21])
    result = build_features(history, request, config=config)
    assert len(result.features) == len(request) == 2
    assert result.features.pm25_lag_1h.isna().all()
    assert result.missing_reasons.pm25_lag_1h.eq(3).all()
    assert result.features.pm25_lag_3h.tolist() == [118., 1118.]
    assert result.features.pm25_roll_mean_3h.isna().all()
    assert result.features.pm25_roll_std_3h.isna().all()
    with pytest.raises(ValueError, match="no actual observation"):
        build_features(history, requests(history, [20]), config=config)


def test_missing_measurement_propagates_but_valid_peak_is_retained(config):
    history = observations()
    history.loc[history.timestamp.eq(pd.Timestamp("2014-01-02 01:00")), "PM2.5"] = np.nan
    history.loc[history.timestamp.eq(pd.Timestamp("2014-01-02 02:00")), "PM2.5"] = 999.
    result = build_features(history, requests(history, [26]), config=config)
    assert result.features["PM2.5"].eq(999).all()
    assert result.features.pm25_lag_1h.isna().all()
    assert result.missing_reasons.pm25_lag_1h.eq(4).all()
    assert result.features.pm25_roll_mean_3h.isna().all()
    assert result.missing_reasons.pm25_roll_mean_3h.eq(6).all()


def test_warmup_full_windows_and_constant_std(config):
    history = observations()
    history["PM2.5"] = 12.
    result = build_features(history, requests(history, [0, 1, 2, 23]), config=config)
    rows = result.features.iloc[:4]
    assert rows.pm25_lag_1h.isna().tolist() == [True, False, False, False]
    assert rows.pm25_roll_mean_3h.isna().tolist() == [True, True, False, False]
    assert rows.pm25_roll_std_3h.iloc[2] == 0.
    assert rows.pm25_roll_mean_24h.iloc[3] == 12.
    assert result.missing_reasons.pm25_roll_mean_24h.iloc[0] == 5


def test_future_changes_cannot_change_past_even_with_later_batch_origins(config):
    history = observations()
    request = requests(history, [5, 10, 30])
    before = build_features(history, request, config=config)
    changed = history.copy()
    future = changed.timestamp.gt(pd.Timestamp("2014-01-01 10:00"))
    changed.loc[future, MEASUREMENTS] *= 3
    changed.loc[future, "wd"] = "S"
    changed["target_pm25"] = -999999  # ignored label-like/provenance fields
    changed["No"] = -1
    request["target_pm25"] = 999999
    after = build_features(changed, request, config=config)
    past_ids = request.loc[request.input_timestamp.le(pd.Timestamp("2014-01-01 10:00")), "sample_id"]
    assert_frame_equal(before.features.loc[past_ids], after.features.loc[past_ids])
    assert_frame_equal(before.missing_reasons.loc[past_ids], after.missing_reasons.loc[past_ids])
    assert before.features.iloc[2]["PM2.5"] != after.features.iloc[2]["PM2.5"]


def test_other_station_and_future_invalid_values_do_not_affect_single_forecast(config):
    history = observations()
    original = features_for_prediction(history, station="TEST_ONLY_A", origin="2014-01-02 06:00", config=config)
    changed = history.copy()
    irrelevant = changed.station.eq("TEST_ONLY_B") | changed.timestamp.gt(pd.Timestamp("2014-01-02 06:00"))
    changed.loc[irrelevant, "PM2.5"] = -999.
    reproduced = features_for_prediction(changed, station="TEST_ONLY_A", origin="2014-01-02 06:00", config=config)
    assert_frame_equal(original.features, reproduced.features)


def test_forecast_calendar_rollover_and_cyclic_values_known_without_target(config):
    history = observations(stations=("TEST_ONLY_A",), start="2020-12-31", periods=24)
    result = features_for_prediction(history, station="TEST_ONLY_A", origin="2020-12-31 23:00", config=config)
    x = result.features.iloc[0]
    assert (x.target_hour, x.target_month, x.target_day_of_week) == (0, 1, 4)
    assert x.target_hour_sin == pytest.approx(0) and x.target_hour_cos == pytest.approx(1)
    assert x.target_month_sin == pytest.approx(0) and x.target_month_cos == pytest.approx(1)
    assert result.sample_metadata.target_timestamp.iloc[0] == pd.Timestamp("2021-01-01")
    assert "target_pm25" not in result.features


@pytest.mark.parametrize("origin", ["2015-02-28 23:00", "2015-03-01 00:00", "2016-02-29 23:00", "2016-03-01 00:00"])
def test_split_boundaries_can_use_observed_history_before_origin(config, origin):
    origin = pd.Timestamp(origin)
    history = observations(stations=("TEST_ONLY_A",), start=origin-pd.Timedelta(hours=30), periods=31)
    full = features_for_prediction(history, station="TEST_ONLY_A", origin=origin, config=config)
    assert full.features.pm25_lag_24h.iloc[0] == 106.
    assert full.features.pm25_roll_mean_24h.iloc[0] == pytest.approx(118.5)
    # Features never reset at a split boundary; the split column is metadata.
    request = full.sample_metadata.reset_index().assign(split="TEST_ONLY_EVALUATION")
    assert_frame_equal(full.features, build_features(history, request, config=config).features)


def test_order_single_forecast_matches_batch_and_inputs_unchanged(config):
    history = observations()
    request = requests(history, [5, 30]).sample(frac=1, random_state=42).reset_index(drop=True)
    before_h, before_r = history.copy(deep=True), request.copy(deep=True)
    batch = build_features(history, request, config=config)
    assert batch.features.index.tolist() == request.sample_id.tolist()
    for row in request.itertuples():
        single = features_for_prediction(history, station=row.station, origin=row.input_timestamp, config=config)
        assert_frame_equal(batch.features.loc[[row.sample_id]], single.features)
    assert_frame_equal(history, before_h)
    assert_frame_equal(request, before_r)


def test_missing_reports_account_for_each_reason_and_cohort(config):
    history = observations()
    history.loc[history.timestamp.eq(pd.Timestamp("2014-01-01 01:00")), ["PM2.5", "wd"]] = [np.nan, None]
    request = requests(history, [0, 1, 2, 30])
    request["is_primary"] = [True, False, True, True]*2
    result = build_features(history, request, config=config)
    for by_station in (False, True):
        table = missing_summary(result, by_station=by_station)
        causes = ["current_value_missing", "lag_before_history", "lag_hour_absent", "lag_value_missing", "rolling_warmup", "rolling_incomplete"]
        assert table[causes].sum(axis=1).equals(table.missing)
        assert table.observed.add(table.missing).equals(table.rows)
    assert missing_summary(result).query("feature == 'PM2.5' and cohort == 'primary'").missing.iloc[0] == 0


@pytest.mark.parametrize("kind", ["duplicate_history", "duplicate_id", "bad_id", "target_hour", "timezone", "missing_current", "nonnumeric", "infinite", "negative", "horizon", "origin_calendar", "partial_rolling"])
def test_contract_rejects_ambiguous_or_unsafe_inputs(config, kind):
    history = observations()
    request = requests(history, [10])
    if kind == "duplicate_history": history = pd.concat([history, history.iloc[[0]]], ignore_index=True)
    elif kind == "duplicate_id": request.loc[1, "sample_id"] = request.loc[0, "sample_id"]
    elif kind == "bad_id": request.loc[0, "sample_id"] = "TEST_ONLY_fake"
    elif kind == "target_hour": request.loc[0, "target_timestamp"] += pd.Timedelta(hours=1)
    elif kind == "timezone": request["input_timestamp"] = request.input_timestamp.dt.tz_localize("UTC")
    elif kind == "missing_current": history = history.loc[history.timestamp.ne(pd.Timestamp("2014-01-01 10:00"))]
    elif kind == "nonnumeric": history["PM2.5"] = "TEST_ONLY_invalid"
    elif kind == "infinite": history.loc[0, "PM2.5"] = float("inf")
    elif kind == "negative": history.loc[0, "PM2.5"] = -1
    elif kind == "horizon": config["horizon_hours"] = 2
    elif kind == "origin_calendar": config["features"]["A"]["calendar_reference"] = "input_timestamp"
    else: config["features"]["B"]["rolling_min_periods"] = 1
    with pytest.raises(ValueError):
        build_features(history, request, config=config)


@pytest.fixture
def feature_project(tmp_path, config):
    """TEST_ONLY complete regular raw prefix and minimal approved train manifest."""
    root = tmp_path / "TEST_ONLY_features_project"
    for name in ("scripts", "configs", "data/raw", "data/processed", "reports/quality_full", "reports/splits_full"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for name in ("build_features.py", "build_samples.py"):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    (root / "configs/default.json").write_text(json.dumps(config), encoding="utf-8")
    h = observations(periods=400)
    h.loc[h.timestamp.eq(pd.Timestamp("2014-01-01 11:00")), "PM2.5"] = np.nan
    paths = []
    for station, group in h.groupby("station"):
        raw = group.assign(No=np.arange(1, len(group)+1), year=group.timestamp.dt.year,
                           month=group.timestamp.dt.month, day=group.timestamp.dt.day, hour=group.timestamp.dt.hour)
        path = root / "data/raw" / f"PRSA_Data_{station}_20130301-20170228.csv"
        raw[RAW_COLUMNS].to_csv(path, index=False, na_rep="NA")
        paths.append(path)
    loaded = load_station_data(paths)
    raw_manifest = {"dataset_id": "TEST_ONLY", "files": [{"path": p.relative_to(root).as_posix(), "sha256": sha256(p)} for p in paths]}
    raw_path = root / "reports/data_manifest.json"
    raw_path.write_text(json.dumps(raw_manifest), encoding="utf-8")
    quality = {**loaded.summary, "status": "passed", "merged_sha256": "TEST_ONLY_MERGED_NOT_READ"}
    quality_path = root / "reports/quality_full/summary.json"
    quality_path.write_text(json.dumps(quality), encoding="utf-8")
    loaded.stations.to_csv(root / "reports/quality_full/stations.csv", index=False)
    train = build_samples(loaded.data).samples.assign(split="train")
    (root / "data/processed/ids").mkdir()
    train.to_csv(root / "data/processed/train.csv", index=False, na_rep="NA")
    train[ID_COLUMNS].to_csv(root / "data/processed/ids/train.csv", index=False)
    files = {}
    for name, path in (("train_samples", root / "data/processed/train.csv"), ("train_ids", root / "data/processed/ids/train.csv")):
        files[name] = {"path": path.relative_to(root).as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size}
    # Any accidental heldout access is fatal: these files do not exist.
    files["test_samples"] = {"path": "TEST_ONLY_DO_NOT_OPEN/test.csv"}
    files["validation_samples"] = {"path": "TEST_ONLY_DO_NOT_OPEN/validation.csv"}
    manifest = {"task_id": "T05", "status": "complete", "mode": "full", "snapshot_id": "TEST_ONLY",
                "signature": {"split": config["split"], "merged_sha256": quality["merged_sha256"],
                              "quality_summary_sha256": sha256(quality_path), "raw_manifest_sha256": sha256(raw_path)},
                "files": files, "membership": {"train": {}}}
    for cohort, subset in (("operational", train), ("primary", train.loc[train.is_primary])):
        manifest["membership"]["train"][cohort] = {"samples": len(subset), "ordered_sample_ids_sha256": ids_digest(subset.sample_id)}
    (root / "reports/splits_full/split_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def invoke(root, mode="smoke"):
    return subprocess.run([sys.executable, str(root / "scripts/build_features.py"), "--mode", mode], cwd=root,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)


def test_cli_full_prefix_history_no_target_filtering_and_idempotent_reuse(feature_project):
    root = feature_project
    first = invoke(root, "full")
    assert first.returncode == 0, first.stderr
    report = root / "reports/features_full/feature_manifest.json"
    manifest = read_json(report)
    assert not manifest["model_experiment_run"] and not manifest["fit_performed"] and not manifest["test_csv_accessed"]
    assert manifest["feature_counts"] == {"A": 20, "B": 33} and manifest["sample_membership_unchanged"]
    frame = pd.read_csv(root / manifest["files"]["train_B"]["path"])
    # Origin hour 10 was dropped by T05 because label at hour 11 is missing.
    # Its PM2.5 observation must still supply lag 3 at origin 13.
    target_id = _sample_id("TEST_ONLY_A", pd.Timestamp("2014-01-01 13:00"), pd.Timestamp("2014-01-01 14:00"))
    assert frame.set_index("sample_id").loc[target_id, "pm25_lag_3h"] == 110.
    assert all(sha256(root / info["path"]) == info["sha256"] for info in manifest["files"].values())
    before = report.read_bytes()
    second = invoke(root, "full")
    assert second.returncode == 0 and "Verified existing" in second.stdout, second.stderr
    assert report.read_bytes() == before
    with (root / manifest["files"]["train_A"]["path"]).open("a", encoding="utf-8") as stream:
        stream.write("TEST_ONLY_tampered\n")
    rejected = invoke(root, "full")
    assert rejected.returncode != 0 and "checksum differs" in rejected.stderr


def test_cli_smoke_reports_true_prefix_counts(feature_project):
    result = invoke(feature_project)
    assert result.returncode == 0, result.stderr
    manifest = read_json(feature_project / "reports/features_smoke/feature_manifest.json")
    assert manifest["mode"] == "smoke" and manifest["rows"] == 2*336
    assert manifest["signature"]["history_scope"]["last_timestamp"] == manifest["input_timestamp_max"]


@pytest.mark.parametrize("change", ["features_only", "seed", "split", "historical_hash"])
def test_historical_eda_guard_allows_only_feature_config_changes(tmp_path, monkeypatch, config, change):
    """TEST_ONLY Git bytes: preserve T06 evidence, reject unrelated drift."""
    spec = importlib.util.spec_from_file_location("TEST_ONLY_eda_verifier", ROOT / "scripts/verify_eda.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    old = json.loads(json.dumps(config))
    old["features"]["B"]["pm25_lag_hours"] = [1, 2, 3, 6, 12, 24]
    original_blob = json.dumps(old).encode("utf-8")+b"\n"
    original_windows = original_blob.replace(b"\n", b"\r\n")
    manifest = {"git_head_at_execution": "a"*40, "default_config_sha256": hashlib.sha256(original_windows).hexdigest()}
    (tmp_path / "configs").mkdir()
    if change == "seed": config["seed"] += 1
    elif change == "split": config["split"]["validation_start"] = "2015-04-01"
    elif change == "historical_hash": manifest["default_config_sha256"] = "0"*64
    (tmp_path / "configs/default.json").write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda args, **kwargs:
                        b"TEST_ONLY_PROJECT/\n" if args[1] == "rev-parse" else original_blob)
    if change == "features_only":
        verifier.verify_original_default_config(tmp_path, manifest)
    else:
        with pytest.raises(AssertionError):
            verifier.verify_original_default_config(tmp_path, manifest)
