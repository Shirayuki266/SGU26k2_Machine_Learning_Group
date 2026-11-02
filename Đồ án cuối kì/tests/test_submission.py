"""Synthetic test ZIPs only; never touch the official experiment ledger."""

import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


spec = importlib.util.spec_from_file_location(
    "submission_validator", Path(__file__).resolve().parents[1] / "scripts/verify_submission.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


@pytest.mark.parametrize("name", ["TEST/../../outside.txt", "C:/outside.txt", "TEST\\outside.txt"])
def test_rejects_unsafe_zip_before_extraction(tmp_path, name):
    archive = tmp_path / "TEST_unsafe.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(name.replace("\\", "/"), "synthetic TEST only")
    # Windows ZipInfo normalizes backslashes when writing. Patch both headers
    # to exercise a foreign ZIP carrying the actual forbidden separator.
    if "\\" in name:
        archive.write_bytes(archive.read_bytes().replace(name.replace("\\", "/").encode(), name.encode()))
    destination = tmp_path / "not_created"
    with pytest.raises(ValueError, match="Unsafe"):
        validator.check_zip(archive, destination)
    assert not destination.exists()


def test_rejects_case_colliding_names(tmp_path):
    archive = tmp_path / "TEST_collision.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("TEST/readme.md", "TEST")
        stream.writestr("TEST/README.md", "TEST")
    with pytest.raises(ValueError, match="case-colliding"):
        validator.check_zip(archive, tmp_path / "not_created")


def test_detects_manifest_tampering(tmp_path):
    archive = tmp_path / "TEST_tampered.zip"
    manifest = {"files": [{"path": "TEST.txt", "bytes": 4,
                           "sha256": hashlib.sha256(b"TEST").hexdigest()}]}
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("TEST/TEST.txt", b"FAIL")
        stream.writestr("TEST/resources/submission_manifest.json", json.dumps(manifest))
    with pytest.raises(ValueError, match="checksum differs"):
        validator.check_zip(archive, tmp_path / "not_created")


def test_manifest_coverage_and_relative_extraction(tmp_path):
    archive = tmp_path / "TEST_valid.zip"
    payload = "TEST: tiếng Việt, không phải run mô hình".encode("utf-8")
    manifest = {"files": [{"path": "notes/TEST.txt", "bytes": len(payload),
                           "sha256": hashlib.sha256(payload).hexdigest()}]}
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("TEST/notes/TEST.txt", payload)
        stream.writestr("TEST/resources/submission_manifest.json", json.dumps(manifest))
    extracted, _ = validator.check_zip(archive, tmp_path / "new")
    assert (extracted / "notes/TEST.txt").read_bytes() == payload
    with pytest.raises(ValueError, match="must not exist"):
        validator.check_zip(archive, tmp_path / "new")
