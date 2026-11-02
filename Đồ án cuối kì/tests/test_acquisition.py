"""TEST_ONLY acquisition fixtures: no network, no project raw data or models."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

import pytest


POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for acquisition scripts")
ARCHIVE_NAME = "PRSA2017_Data_20130301-20170228.zip"


def quote_ps(value):
    return "'" + str(value).replace("'", "''") + "'"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def acquisition(tmp_path):
    project = tmp_path / "TEST_ONLY_project"
    (project / "scripts").mkdir(parents=True)
    (project / "configs").mkdir()
    source = Path(__file__).resolve().parents[1] / "scripts/download_uci.ps1"
    script = project / "scripts/download_uci.ps1"
    shutil.copyfile(source, script)
    config = {
        "dataset_id": "TEST_ONLY", "name": "TEST_ONLY synthetic archive",
        "source_url": "https://example.invalid/TEST_ONLY",
        "download_url": "https://example.invalid/TEST_ONLY.zip",
        "archive_name": ARCHIVE_NAME, "published_stations": 2,
        "license": "TEST_ONLY", "license_url": "https://example.invalid/TEST_ONLY-license",
        "doi": None,
    }
    (project / "configs/uci_501.json").write_text(json.dumps(config), encoding="utf-8")
    inner = tmp_path / ARCHIVE_NAME
    with ZipFile(inner, "w") as archive:
        for name in ["TEST_ONLY_A", "TEST_ONLY_B"]:
            archive.writestr(
                f"TEST_ONLY/PRSA_Data_{name}_20130301-20170228.csv",
                f"No,station\n1,{name}\n",
            )
    outer = tmp_path / "TEST_ONLY_outer.zip"
    with ZipFile(outer, "w") as archive:
        archive.write(inner, f"TEST_ONLY/{ARCHIVE_NAME}")
        archive.writestr("data.csv", "TEST_ONLY decoy,do not extract\n")
    return project, script, outer, inner


def invoke(acquisition, archive=None, downloaded_at=None, mock_download=None, reject_network=False):
    project, script, _, _ = acquisition
    command = ""
    if mock_download is not None:
        command += (
            "function Invoke-WebRequest { param($Uri,$OutFile,$TimeoutSec,[switch]$UseBasicParsing) "
            f"Copy-Item -LiteralPath {quote_ps(mock_download)} -Destination $OutFile }}; "
        )
    elif reject_network:
        command += "function Invoke-WebRequest { throw 'TEST_ONLY: network must not be used' }; "
    command += f"& {quote_ps(script)}"
    if archive is not None:
        command += f" -ZipPath {quote_ps(archive)}"
    if downloaded_at is not None:
        command += f" -DownloadedAt {quote_ps(downloaded_at)}"
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )


def manifest(project):
    return json.loads((project / "reports/data_manifest.json").read_text(encoding="utf-8-sig"))


def assert_ok(result):
    assert result.returncode == 0, result.stdout + result.stderr


def test_manual_outer_extracts_only_stations_unknown_date_stays_null(acquisition):
    project, _, outer, inner = acquisition
    assert_ok(invoke(acquisition, outer, reject_network=True))
    record = manifest(project)
    assert record["dataset_id"] == "TEST_ONLY" and record["downloaded_at"] is None
    assert record["acquisition"] == "manual" and len(record["files"]) == 2
    assert record["archive"]["sha256"] == digest(outer)
    assert record["prsa_archive"]["sha256"] == digest(inner)
    assert not (project / "data/raw/data.csv").exists()
    for item in record["files"]:
        assert item["sha256"] == digest(project / item["path"])


def test_manual_inner_reuses_outer_provenance_and_raw(acquisition):
    project, _, outer, inner = acquisition
    known_date = "2020-01-02T03:04:05+00:00"  # TEST_ONLY, not an actual acquisition.
    assert_ok(invoke(acquisition, outer, downloaded_at=known_date))
    before = manifest(project)
    raw_before = {path.name: digest(path) for path in (project / "data/raw").iterdir()}
    assert_ok(invoke(acquisition, inner, reject_network=True))
    after = manifest(project)
    assert after["archive"] == before["archive"]
    assert after["prsa_archive"] == before["prsa_archive"]
    assert after["downloaded_at"] == before["downloaded_at"]
    assert after["acquisition"] == before["acquisition"]
    assert {path.name: digest(path) for path in (project / "data/raw").iterdir()} == raw_before


def test_existing_archive_rerun_is_idempotent_and_does_not_download(acquisition):
    project, _, outer, _ = acquisition
    raw = project / "data/raw"
    raw.mkdir(parents=True)
    shutil.copyfile(outer, raw / "uci_501_download.zip")
    assert_ok(invoke(acquisition, reject_network=True))
    path = project / "reports/data_manifest.json"
    before = path.read_bytes()
    assert_ok(invoke(acquisition, reject_network=True))
    assert path.read_bytes() == before
    assert manifest(project)["downloaded_at"] is None


def test_download_path_records_real_call_time_with_network_mock(acquisition):
    project, _, outer, _ = acquisition
    started = datetime.now(timezone.utc)
    assert_ok(invoke(acquisition, mock_download=outer))
    record = manifest(project)
    recorded_download = datetime.fromisoformat(record["downloaded_at"])
    assert started <= recorded_download <= datetime.now(timezone.utc)
    assert record["acquisition"] == "download"


def test_manual_known_date_is_normalized_to_utc(acquisition):
    project, _, _, inner = acquisition
    assert_ok(invoke(acquisition, inner, downloaded_at="2020-01-02T03:04:05+07:00"))
    value = manifest(project)["downloaded_at"]
    assert datetime.fromisoformat(value) == datetime(2020, 1, 1, 20, 4, 5, tzinfo=timezone.utc)
    assert value.endswith("+00:00")


def test_changed_existing_raw_is_never_overwritten(acquisition):
    project, _, outer, _ = acquisition
    assert_ok(invoke(acquisition, outer))
    path = next((project / "data/raw").glob("*.csv"))
    path.write_bytes(b"TEST_ONLY changed raw")
    prior_manifest = (project / "reports/data_manifest.json").read_bytes()
    result = invoke(acquisition, outer)
    assert result.returncode != 0 and "refusing overwrite" in result.stderr
    assert path.read_bytes() == b"TEST_ONLY changed raw"
    assert (project / "reports/data_manifest.json").read_bytes() == prior_manifest


def test_incomplete_multi_site_archive_is_rejected(acquisition, tmp_path):
    project, _, _, _ = acquisition
    partial = tmp_path / "TEST_ONLY_partial.zip"
    with ZipFile(partial, "w") as archive:
        archive.writestr("PRSA_Data_TEST_ONLY_A_20130301-20170228.csv", "TEST_ONLY partial\n")
    result = invoke(acquisition, partial)
    assert result.returncode != 0
    assert not (project / "reports/data_manifest.json").exists()
    assert not list((project / "data/raw").glob("*.csv"))


def test_wrong_archive_is_rejected(acquisition, tmp_path):
    project, _, _, _ = acquisition
    wrong = tmp_path / "TEST_ONLY_wrong.zip"
    with ZipFile(wrong, "w") as archive:
        archive.writestr("data.csv", "TEST_ONLY wrong dataset\n")
    assert invoke(acquisition, wrong).returncode != 0
    assert not (project / "reports/data_manifest.json").exists()


def test_changed_archive_does_not_replace_existing_provenance(acquisition, tmp_path):
    project, _, outer, _ = acquisition
    assert_ok(invoke(acquisition, outer))
    prior = (project / "reports/data_manifest.json").read_bytes()
    changed = tmp_path / "TEST_ONLY_changed.zip"
    with ZipFile(changed, "w") as archive:
        archive.writestr("PRSA_Data_TEST_ONLY_C_20130301-20170228.csv", "TEST_ONLY changed\n")
    result = invoke(acquisition, changed)
    assert result.returncode != 0 and "refusing to replace provenance" in result.stderr
    assert (project / "reports/data_manifest.json").read_bytes() == prior


@pytest.mark.parametrize("value", ["2020-01-02T03:04:05", "TEST_ONLY invalid date"])
def test_ambiguous_or_invalid_date_does_not_create_manifest(acquisition, value):
    project, _, _, inner = acquisition
    assert invoke(acquisition, inner, downloaded_at=value).returncode != 0
    assert not (project / "reports/data_manifest.json").exists()


def test_existing_manifest_file_checksum_is_not_silently_replaced(acquisition):
    project, _, outer, _ = acquisition
    assert_ok(invoke(acquisition, outer))
    path = project / "reports/data_manifest.json"
    record = manifest(project)
    record["files"][0]["sha256"] = "TEST_ONLY incorrect checksum"
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    result = invoke(acquisition, outer)
    assert result.returncode != 0 and "Station provenance differs" in result.stderr
    assert path.read_bytes() == before


def test_manifest_metadata_drift_requires_review(acquisition):
    project, _, outer, _ = acquisition
    assert_ok(invoke(acquisition, outer))
    path = project / "reports/data_manifest.json"
    record = manifest(project)
    record["license"] = "TEST_ONLY unexpected license"
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    result = invoke(acquisition, outer)
    assert result.returncode != 0 and "Existing provenance metadata differs" in result.stderr
    assert path.read_bytes() == before


def test_network_failure_points_to_manual_fallback(acquisition):
    project, _, _, _ = acquisition
    result = invoke(acquisition, reject_network=True)
    assert result.returncode != 0 and "README manual ZIP instructions" in result.stderr
    assert not (project / "reports/data_manifest.json").exists()
    assert not (project / "data/raw/uci_501_download.zip").exists()


def test_incomplete_download_is_preserved_and_not_retried(acquisition):
    project, _, _, _ = acquisition
    path = project / "data/raw/uci_501_download.zip.part"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"TEST_ONLY incomplete download")
    result = invoke(acquisition, reject_network=True)
    assert result.returncode != 0 and "Incomplete download exists" in result.stderr
    assert path.read_bytes() == b"TEST_ONLY incomplete download"
    assert not (project / "reports/data_manifest.json").exists()
