"""Deliver T13 weights/records plus immutable T09 dependencies, without refitting."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import stat
import zipfile

from beijing_air.data import sha256
from beijing_air.eda import project_path,read_json
from beijing_air.final_evaluation import write_json

ROOT=Path(__file__).resolve().parents[1]


def verify_or_restore(path,*,restore=False):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:raise ValueError("CRC failed")
        infos=archive.infolist()
        names=[i.orig_filename for i in infos]
        if len(names)!=len(set(n.casefold() for n in names)) or sum(i.file_size for i in infos)>1_000_000_000:
            raise ValueError("Duplicate/oversized bundle")
        for info,name in zip(infos,names):
            parts=PurePosixPath(name).parts
            if "\\" in name or ":" in name or ".." in parts or PurePosixPath(name).is_absolute() or stat.S_ISLNK(info.external_attr>>16):
                raise ValueError("Unsafe archive path")
        manifest=json.loads(archive.read("T13_manifest.json"))
        if set(names)!={i["path"] for i in manifest["files"]}|{"T13_manifest.json"}:
            raise ValueError("Manifest coverage differs")
        for info in manifest["files"]:
            if not info["path"].startswith("artifacts/experiments/"):
                raise ValueError("Only run trees may be restored, never the CSV ledger")
            payload=archive.read(info["path"])
            if len(payload)!=info["bytes"] or hashlib.sha256(payload).hexdigest()!=info["sha256"]:
                raise ValueError("Bundle checksum differs")
            dest=project_path(ROOT,info["path"])
            if restore and dest.exists() and sha256(dest)!=info["sha256"]:
                raise ValueError("Existing artifact differs: refusing overwrite")
        written=0
        if restore:
            for info in manifest["files"]:
                dest=project_path(ROOT,info["path"])
                if dest.exists():continue
                dest.parent.mkdir(parents=True,exist_ok=True)
                with dest.open("xb") as stream:stream.write(archive.read(info["path"]))
                written+=1
    return {"status":"PASS","files":len(manifest["files"]),"restored_missing_files":written,"sha256":sha256(Path(path)),"ledger_written":False,"models_refitted":False}


def build():
    out=ROOT/"reports/final_evaluation"
    state=read_json(out/"execution.json")
    if state["status"]!="completed":raise ValueError("Cannot package an incomplete T13 attempt")
    parent=ROOT/"artifacts/experiments"/state["parent_run_id"]
    old=list(csv.DictReader(io.StringIO((parent/"artifacts/data/development_ledger_before.csv").read_text(encoding="utf-8"))))
    deps=[r["run_id"] for r in old if r["task_id"]=="T09"]
    ids=[state["parent_run_id"],*state["child_run_ids"].values(),*deps]
    files={}
    for rid in ids:
        d=ROOT/"artifacts/experiments"/rid
        meta=read_json(d/"metadata.json")
        if meta["status"]!="completed":raise ValueError("Only completed records may be delivered")
        paths=[d/n for n in ("config.json","metadata.json","metrics.json","notes.md")]
        for info in meta["artifacts"]:
            path=project_path(ROOT,Path("experiments")/info["path"])
            if not path.is_relative_to(d) or sha256(path)!=info["sha256"] or path.stat().st_size!=info["size_bytes"]:
                raise ValueError("Registered artifact differs")
            paths.append(path)
        for path in paths:
            files[path.relative_to(ROOT).as_posix()]={"path":path.relative_to(ROOT).as_posix(),"bytes":path.stat().st_size,"sha256":sha256(path)}
    manifest={"task_id":"T13","new_run_ids":[state["parent_run_id"],*state["child_run_ids"].values()],
              "historic_T09_dependency_ids":deps,"history_note":"Two unchanged T09 run trees are dependencies, not new T13 runs. Never restore their old CSV over the current ledger.",
              "selected_final_model_run_id":state["child_run_ids"]["random_forest"],"selected_by":"development_validation_MAE",
              "files":[files[n] for n in sorted(files)]}
    archive_path=out/"t13_runs.zip"
    pending=archive_path.with_suffix(".zip.partial")
    with zipfile.ZipFile(pending,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted(files):archive.write(ROOT/name,name)
        archive.writestr("T13_manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
    pending.replace(archive_path)
    result=verify_or_restore(archive_path)
    result["zip_bytes"]=archive_path.stat().st_size
    write_json(out/"artifact_delivery_manifest.json",{**manifest,"bundle":result})
    (out/"t13_runs.zip.sha256").write_text(result["sha256"]+"  t13_runs.zip\n",encoding="ascii",newline="\n")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--restore",type=Path)
    p.add_argument("--verify",type=Path)
    args=p.parse_args()
    if args.restore and args.verify:p.error("Choose restore or verify")
    print(json.dumps(verify_or_restore(args.restore,restore=True) if args.restore else verify_or_restore(args.verify) if args.verify else build()))


if __name__=="__main__":main()
