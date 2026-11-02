"""TEST_ONLY one-hour fixtures. No project dataset reads, fit, or model metrics."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from beijing_air.data import RAW_COLUMNS, load_station_data, sha256
from beijing_air.samples import (
    build_samples, check_label_availability, summarize_splits, temporal_split,
)


def observations(station, times, values):
    return pd.DataFrame({"station": station, "timestamp": pd.to_datetime(times),
                         "PM2.5": pd.Series(values, dtype="Float64")})


def split(samples):
    return temporal_split(samples, validation_start="2015-03-01", test_start="2016-03-01")


def test_exact_join_never_crosses_stations_and_keeps_origins_unchanged():
    times = ["2014-01-01 00:00", "2014-01-01 01:00", "2014-01-01 02:00"]
    data = pd.concat([observations("TEST_ONLY_A", times, [10, 20, 30]),
                      observations("TEST_ONLY_B", times, [100, 200, 300])], ignore_index=True)
    original = data.copy(deep=True)
    result = build_samples(data)
    assert result.samples["target_pm25"].tolist() == [20, 30, 200, 300]
    assert result.samples["PM2.5"].tolist() == [10, 20, 100, 200]
    assert (result.samples["target_timestamp"] - result.samples["input_timestamp"]).eq(pd.Timedelta(hours=1)).all()
    assert result.exclusions["reason"].tolist() == ["end_of_series", "end_of_series"]
    assert result.totals["input_rows"] == 6 and result.totals["retained_primary"] == 4
    assert_frame_equal(data, original)


def test_gap_is_missing_hour_not_next_row_or_next_station():
    data = pd.concat([
        observations("TEST_ONLY_A", ["2014-01-01 00:00", "2014-01-01 02:00", "2014-01-01 03:00"], [1, 2, 3]),
        observations("TEST_ONLY_B", ["2014-01-01 01:00", "2014-01-01 02:00"], [100, 200]),
    ], ignore_index=True)
    result = build_samples(data)
    assert result.samples["target_pm25"].tolist() == [3, 200]
    assert result.totals["excluded_missing_target_timestamp"] == 1
    assert result.totals["excluded_end_of_series"] == 2
    assert result.exclusions.loc[result.exclusions["reason"].eq("missing_target_timestamp"), "station"].tolist() == ["TEST_ONLY_A"]


def test_missing_target_never_imputed_missing_origin_retained_in_operational_only():
    data = observations("TEST_ONLY_A", pd.date_range("2014-01-01", periods=4, freq="h"), [10, None, 30, 40])
    result = build_samples(data)
    assert result.samples["target_pm25"].tolist() == [30, 40]
    assert result.samples["is_primary"].tolist() == [False, True]
    assert pd.isna(result.samples.loc[0, "PM2.5"])
    assert result.totals == {
        "input_rows": 4, "retained_operational": 2, "retained_primary": 1, "excluded_total": 2,
        "missing_origin_pm25_total": 1, "retained_missing_origin_pm25": 1,
        "excluded_end_of_series": 1, "excluded_missing_target_timestamp": 0, "excluded_missing_target_value": 1,
    }
    assert set(result.exclusions["reason"]) == {"missing_target_value", "end_of_series"}
    assert "origin_pm25_observed" in result.exclusions and "target_pm25" not in result.exclusions


def test_ids_are_stable_under_input_order_index_provenance_and_value_changes():
    data = observations("KIỂM_THỬ_Đà_Nẵng", pd.date_range("2014-01-01", periods=3, freq="h"), [1, 2, 3])
    expected = build_samples(data).samples
    changed = data.sample(frac=1, random_state=42)
    changed.index = [20, 30, 10]
    changed = changed.assign(source_file="TEST_ONLY_another_source")
    changed["PM2.5"] = changed["PM2.5"] + 100
    result = build_samples(changed).samples
    assert result["sample_id"].tolist() == expected["sample_id"].tolist()
    assert result["sample_id"].str.fullmatch("[a-f0-9]{64}").all()
    other_station = build_samples(data.assign(station="TEST_ONLY_other")).samples
    assert set(other_station["sample_id"]).isdisjoint(expected["sample_id"])


def test_target_boundaries_are_shared_and_ids_disjoint_reproducible():
    times = ["2015-02-28 22:00", "2015-02-28 23:00", "2015-03-01 00:00",
             "2016-02-29 22:00", "2016-02-29 23:00", "2016-03-01 00:00", "2016-03-01 01:00"]
    data = pd.concat([observations(station, times, range(7)) for station in ["TEST_ONLY_A", "TEST_ONLY_B"]], ignore_index=True)
    result = split(build_samples(data).samples)
    for station in data["station"].unique():
        group = result.loc[result["station"].eq(station)].set_index("input_timestamp")
        assert group.loc[pd.Timestamp("2015-02-28 22:00"), "split"] == "train"
        assert group.loc[pd.Timestamp("2015-02-28 23:00"), "split"] == "validation"
        assert group.loc[pd.Timestamp("2016-02-29 22:00"), "split"] == "validation"
        assert group.loc[pd.Timestamp("2016-02-29 23:00"), "split"] == "test"
    ids = {name: set(result.loc[result["split"].eq(name), "sample_id"]) for name in ["train", "validation", "test"]}
    assert len(set.union(*ids.values())) == len(result)
    assert ids["train"].isdisjoint(ids["validation"] | ids["test"])
    assert ids["validation"].isdisjoint(ids["test"])
    assert_frame_equal(result, split(build_samples(data.iloc[::-1]).samples))
    summary = summarize_splits(result)
    assert summary.loc[summary["cohort"].eq("primary"), "samples"].tolist() == [2, 4, 4]


def test_all_rejected_and_absent_station_split_report_zero_not_fake_ranges():
    data = observations("TEST_ONLY_A", pd.date_range("2014-01-01", periods=2, freq="h"), [None, None])
    result = build_samples(data)
    assert result.samples.empty and result.totals["excluded_total"] == 2
    summary = summarize_splits(split(result.samples), by_station=True, station_names=["TEST_ONLY_A"])
    assert len(summary) == 6 and summary["samples"].eq(0).all()
    assert summary["target_timestamp_min"].isna().all()


@pytest.mark.parametrize("kind", ["duplicate", "missing_station", "non_hourly", "timezone", "negative", "infinite", "reserved", "No"])
def test_invalid_observations_fail_before_samples(kind):
    data = observations("TEST_ONLY_A", pd.date_range("2014-01-01", periods=2, freq="h"), [1, 2])
    if kind == "duplicate":
        data = pd.concat([data, data.iloc[[0]]], ignore_index=True)
    elif kind == "missing_station":
        data.loc[0, "station"] = " "
    elif kind == "non_hourly":
        data.loc[0, "timestamp"] += pd.Timedelta(minutes=1)
    elif kind == "timezone":
        data["timestamp"] = data["timestamp"].dt.tz_localize("UTC")
    elif kind in ("negative", "infinite"):
        data.loc[0, "PM2.5"] = -1 if kind == "negative" else float("inf")
    elif kind == "reserved":
        data["target_pm25"] = 1
    else:
        data["No"] = 1
    with pytest.raises(ValueError):
        build_samples(data)


@pytest.mark.parametrize("horizon", [0, 2, -1, True])
def test_horizon_other_than_one_is_rejected(horizon):
    data = observations("TEST_ONLY_A", pd.date_range("2014-01-01", periods=2, freq="h"), [1, 2])
    with pytest.raises(ValueError, match="horizon_hours"):
        build_samples(data, horizon_hours=horizon)


def test_invalid_split_boundaries_and_mutated_horizon_are_rejected():
    samples = build_samples(observations("TEST_ONLY_A", pd.date_range("2014-01-01", periods=2, freq="h"), [1, 2])).samples
    for first, second in [("2016-03-01", "2015-03-01"), ("2015-03-01", "2015-03-01"), ("2015-03-01T00:00:00Z", "2016-03-01")]:
        with pytest.raises(ValueError):
            temporal_split(samples, validation_start=first, test_start=second)
    samples["target_timestamp"] += pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match="exactly one hour"):
        split(samples)


def test_label_availability_equality_holdout_strict_cv_and_explicit_cutoff():
    fit = pd.DataFrame({"target_timestamp": pd.to_datetime(["2015-02-28 22:00", "2015-02-28 23:00"])})
    evaluation = pd.DataFrame({"input_timestamp": pd.to_datetime(["2015-02-28 23:00", "2015-03-01 00:00"])})
    check = check_label_availability(fit, evaluation)
    assert check["status"] == "passed" and check["comparison"] == "<=" and check["fitted"] is False
    with pytest.raises(ValueError, match="strictly precede"):
        check_label_availability(fit, evaluation, strict_before_origin=True)
    assert check_label_availability(fit.iloc[:1], evaluation, strict_before_origin=True)["comparison"] == "<"
    for cutoff in ["2015-02-28 22:00", "2015-03-01 00:00"]:
        with pytest.raises(ValueError, match="unavailable"):
            check_label_availability(fit, evaluation, fit_cutoff=cutoff)
    with pytest.raises(ValueError, match="empty"):
        check_label_availability(fit.iloc[:0], evaluation)


def test_label_guard_is_global_for_shared_model_not_separate_station_cutoffs():
    fit = pd.DataFrame({"station": ["TEST_ONLY_B"], "target_timestamp": pd.to_datetime(["2015-03-01 00:00"])})
    evaluation = pd.DataFrame({"station": ["TEST_ONLY_A"], "input_timestamp": pd.to_datetime(["2015-02-28 23:00"])})
    with pytest.raises(ValueError, match="unavailable"):
        check_label_availability(fit, evaluation)


@pytest.fixture
def sample_project(tmp_path):
    root = tmp_path / "TEST_ONLY_sample_project"
    for name in ["scripts", "configs", "data/raw", "data/processed", "reports/quality_full", "reports/quality_smoke"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    project = Path(__file__).resolve().parents[1]
    shutil.copyfile(project / "scripts/build_samples.py", root / "scripts/build_samples.py")
    config = json.loads((project / "configs/default.json").read_text(encoding="utf-8"))
    (root / "configs/default.json").write_text(json.dumps(config), encoding="utf-8")
    times = pd.to_datetime(["2015-02-28 22:00", "2015-02-28 23:00", "2015-03-01 00:00",
                            "2016-02-29 22:00", "2016-02-29 23:00", "2016-03-01 00:00", "2016-03-01 01:00"])
    paths = []
    for number, station in enumerate(["TEST_ONLY_A", "TEST_ONLY_B"]):
        records = []
        for index, timestamp in enumerate(times):
            row = dict.fromkeys(RAW_COLUMNS, 1)
            row.update(No=index+1, year=timestamp.year, month=timestamp.month, day=timestamp.day, hour=timestamp.hour,
                       station=station, wd="N", TEMP=10, DEWP=5, PRES=1010)
            row["PM2.5"] = 10 + 100 * number + index
            records.append(row)
        path = root / "data/raw" / f"PRSA_Data_{station}_20130301-20170228.csv"
        pd.DataFrame(records, columns=RAW_COLUMNS).to_csv(path, index=False)
        paths.append(path)
    result = load_station_data(paths)
    source_manifest = {"dataset_id": "TEST_ONLY", "files": [{"path": path.relative_to(root).as_posix(), "sha256": sha256(path)} for path in paths]}
    (root / "reports/data_manifest.json").write_text(json.dumps(source_manifest), encoding="utf-8")
    for mode in ["full", "smoke"]:
        subset = result.data if mode == "full" else result.data.groupby("station").head(2)
        output = root / f"data/processed/merged_unimputed_{mode}.csv"
        subset.to_csv(output, index=False, na_rep="NA", date_format="%Y-%m-%d %H:%M:%S")
        audit = {**result.summary, "mode": mode, "status": "passed", "merged_output_written": True,
                 "merged_sha256": sha256(output), "output_rows": len(subset)}
        (root / f"reports/quality_{mode}/summary.json").write_text(json.dumps(audit), encoding="utf-8")
    return root


def invoke(root, mode="full", *, output_tag=None):
    command = [sys.executable, str(root / "scripts/build_samples.py"), "--mode", mode]
    if output_tag is not None:
        command += ["--output-tag", output_tag]
    return subprocess.run(command,
                          cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)


def test_cli_manifest_ids_accounting_and_idempotent_reuse(sample_project):
    root = sample_project
    result = invoke(root)
    assert result.returncode == 0, result.stderr
    path = root / "reports/splits_full/split_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["totals"]["input_rows"] == 14 and manifest["totals"]["retained_primary"] == 10
    assert manifest["artifact_type"] == "data_preparation_audit" and manifest["model_experiment_run"] is False
    assert all(item["status"] == "passed" and item["fitted"] is False for item in manifest["label_availability"].values())
    ids = []
    for name in ["train", "validation", "test"]:
        subset = pd.read_csv(root / manifest["files"][f"{name}_ids"]["path"])
        ids.extend(subset["sample_id"])
    assert len(ids) == len(set(ids)) == 10
    assert all(sha256(root / info["path"]) == info["sha256"] for info in manifest["files"].values())
    before = path.read_bytes()
    result = invoke(root)
    assert result.returncode == 0 and "Verified existing" in result.stdout, result.stderr
    assert path.read_bytes() == before


def test_cli_smoke_empty_partitions_have_null_ranges_and_no_false_fit_claim(sample_project):
    result = invoke(sample_project, "smoke")
    assert result.returncode == 0, result.stderr
    manifest = json.loads((sample_project / "reports/splits_smoke/split_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "smoke" and "prefix" in manifest["input_scope"]
    assert all(item["status"] == "not_evaluated_empty_partition" for item in manifest["label_availability"].values())
    empty = [row for row in manifest["split_summary"] if row["samples"] == 0]
    assert empty and all(row["target_timestamp_min"] is None for row in empty)


def test_cli_refuses_tampered_input_before_output(sample_project):
    source = sample_project / "data/processed/merged_unimputed_full.csv"
    with source.open("a", encoding="utf-8") as stream:
        stream.write("TEST_ONLY changed input\n")
    result = invoke(sample_project)
    assert result.returncode != 0 and "checksum" in result.stderr
    assert not (sample_project / "data/processed/samples_full").exists()


def test_cli_refuses_to_overwrite_tampered_snapshot(sample_project):
    assert invoke(sample_project).returncode == 0
    path = sample_project / "data/processed/samples_full/test.csv"
    path.write_bytes(b"TEST_ONLY tampered output")
    result = invoke(sample_project)
    assert result.returncode != 0 and "checksum differs" in result.stderr
    assert path.read_bytes() == b"TEST_ONLY tampered output"


def test_cli_refuses_changed_problem_contract(sample_project):
    path = sample_project / "configs/default.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["problem"]["target_column"] = "PM10"
    path.write_text(json.dumps(config), encoding="utf-8")
    result = invoke(sample_project)
    assert result.returncode != 0 and "problem contract" in result.stderr
    assert not (sample_project / "data/processed/samples_full").exists()


def test_cli_rejects_incomplete_manifest_even_if_remaining_files_match(sample_project):
    assert invoke(sample_project).returncode == 0
    path = sample_project / "reports/splits_full/split_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["files"]["test_samples"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = invoke(sample_project)
    assert result.returncode != 0 and "manifest is incomplete" in result.stderr


def test_fresh_checkout_can_reproduce_with_tag_without_overwriting_committed_report(sample_project):
    root = sample_project
    assert invoke(root).returncode == 0
    path = root / "reports/splits_full/split_manifest.json"
    original = path.read_bytes()
    old = json.loads(original)
    # TEST_ONLY: imitate a checkout containing reports, without ignored data.
    shutil.rmtree(root / "data/processed/samples_full")
    assert invoke(root).returncode != 0
    result = invoke(root, output_tag="reproduce")
    assert result.returncode == 0, result.stderr
    new = json.loads((root / "reports/splits_full_reproduce/split_manifest.json").read_text(encoding="utf-8"))
    assert new["totals"] == old["totals"] and new["membership"] == old["membership"]
    assert path.read_bytes() == original
    assert (root / "data/processed/samples_full_reproduce/train.csv").is_file()


@pytest.mark.parametrize("tag", ["../outside", "bad/name", "C:outside"])
def test_output_tag_cannot_escape_project(sample_project, tag):
    result = invoke(sample_project, output_tag=tag)
    assert result.returncode != 0 and "output-tag must be" in result.stderr
