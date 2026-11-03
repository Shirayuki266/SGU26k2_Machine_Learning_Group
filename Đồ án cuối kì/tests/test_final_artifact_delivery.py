"""TEST_ONLY bundles: restoration must never overwrite history or the ledger."""

import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

spec=importlib.util.spec_from_file_location("TEST_ONLY_delivery",Path(__file__).resolve().parents[1]/"scripts/package_final_artifacts.py")
delivery=importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


def TEST_bundle(tmp_path):
    values={"artifacts/experiments/TEST_ONLY/config.json":b'{"is_test":true}',
            "artifacts/experiments/TEST_ONLY/artifacts/model/TEST_ONLY.joblib":b"TEST_ONLY_NOT_REAL_WEIGHTS"}
    manifest={"files":[{"path":name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()} for name,payload in values.items()]}
    path=tmp_path/"TEST_ONLY.zip"
    with zipfile.ZipFile(path,"w") as stream:
        for name,payload in values.items():stream.writestr(name,payload)
        stream.writestr("T13_manifest.json",json.dumps(manifest))
    return path,values


def test_restore_only_missing_files_and_never_ledger(tmp_path,monkeypatch):
    root=tmp_path/"TEST_ONLY_ROOT";root.mkdir()
    monkeypatch.setattr(delivery,"ROOT",root)
    path,values=TEST_bundle(tmp_path)
    first=next(iter(values));existing=root/first;existing.parent.mkdir(parents=True);existing.write_bytes(values[first])
    ledger=root/"experiments/experiment_log.csv";ledger.parent.mkdir();ledger.write_bytes(b"TEST_ONLY_LEDGER_DO_NOT_REPLACE")
    result=delivery.verify_or_restore(path,restore=True)
    assert result["restored_missing_files"]==1 and not result["ledger_written"]
    assert ledger.read_bytes()==b"TEST_ONLY_LEDGER_DO_NOT_REPLACE"
    for name,payload in values.items():assert (root/name).read_bytes()==payload
    assert delivery.verify_or_restore(path,restore=True)["restored_missing_files"]==0


def test_refuse_all_writes_if_existing_artifact_differs(tmp_path,monkeypatch):
    root=tmp_path/"TEST_ONLY_ROOT";root.mkdir()
    monkeypatch.setattr(delivery,"ROOT",root)
    path,values=TEST_bundle(tmp_path)
    last=list(values)[-1];existing=root/last;existing.parent.mkdir(parents=True);existing.write_bytes(b"TEST_ONLY_EXISTING_HISTORY")
    with pytest.raises(ValueError,match="refusing overwrite"):
        delivery.verify_or_restore(path,restore=True)
    assert existing.read_bytes()==b"TEST_ONLY_EXISTING_HISTORY"
    assert not (root/next(iter(values))).exists()
