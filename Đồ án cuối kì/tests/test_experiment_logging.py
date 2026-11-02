"""TEST ONLY: synthetic logs/artifacts under tmp_path; no project data is read."""

from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from beijing_air.experiment_logging import CSV_FIELDS, ExperimentLogger
from beijing_air.experiment_logging import _git_state


@pytest.fixture
def logger(tmp_path):
    return ExperimentLogger(tmp_path / "TEST_ONLY_experiments", project_root=tmp_path)


def rows(logger):
    with logger.csv_path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def start(logger, **kwargs):
    return logger.start_run(task_id="TEST_ONLY_T04", is_test=True, **kwargs)


def test_tracked_index_without_run_files_never_loses_history_on_new_run(logger):
    with start(logger) as original:
        pass
    before = logger.csv_path.read_bytes()
    metrics = original.directory / "metrics.json"
    saved = metrics.read_bytes()
    metrics.unlink()  # TEST_ONLY: simulate a clone with missing run artifacts.
    with pytest.raises(FileNotFoundError, match="restore the run bundle"):
        start(logger)
    assert logger.csv_path.read_bytes() == before
    assert len(list(logger.artifact_dir.iterdir())) == 1
    metrics.write_bytes(saved)
    with start(logger):
        pass
    assert len(rows(logger)) == 2


def test_lifecycle_unicode_null_and_csv_links(logger):
    objective = 'KIỂM THỬ: dự báo, tiếng Việt\n"không phải thực nghiệm"'
    with start(logger, objective=objective, mode="smoke", kind="baseline",
               seed=42, model="TEST_ONLY", parameters={"unknown": None},
               feature_set=["PM2.5"], data={"manifest": "TEST_ONLY.json"},
               split={"basis": "target_timestamp"}) as run:
        record = rows(logger)[0]
        assert record["status"] == "running" and record["ended_at"] == ""
        assert read(run.directory / "metrics.json") == {}
        run.log_metrics({"mae": 0.25, "r2": None}, split="validation")
        run.log_metrics({"rmse": 0.5}, split="validation")
    record, = rows(logger)
    assert record["status"] == "completed" and record["objective"] == objective
    assert record["reference_run_id"] == "" and record["notes"] == ""
    assert json.loads(record["is_test"]) is True
    assert float(record["duration_seconds"]) >= 0
    assert record["timezone"] == "UTC" and record["started_at"].endswith("+00:00")
    config = read(logger.experiment_dir / record["config_path"])
    assert config["objective"] == objective and config["preprocessing"] is None
    assert config["parameters"]["unknown"] is None
    metrics = read(logger.experiment_dir / record["metrics_path"])
    assert metrics == {"validation": {"mae": 0.25, "rmse": 0.5, "r2": None}}
    assert json.loads(record["metrics"]) == metrics
    metadata = read(logger.experiment_dir / record["metadata_path"])
    assert metadata["run_id"] == run.run_id and metadata["error"] is None
    assert set(metadata["git"]) == {"commit", "branch", "dirty", "available"}
    if metadata["git"]["available"]:
        assert metadata["git"]["commit"] and isinstance(metadata["git"]["dirty"], bool)
    assert metadata["environment"]["python"] and metadata["environment"]["packages"]
    assert (logger.experiment_dir / record["notes_path"]).is_file()


def test_failure_keeps_config_metrics_artifact_and_traceback(logger, tmp_path):
    source = tmp_path / "TEST_ONLY.txt"
    source.write_text("Dữ liệu kiểm thử", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Lỗi kiểm thử"):
        with start(logger, objective="TEST ONLY: failure") as run:
            run.log_metrics({"partial": None})
            saved = run.log_artifact(source)
            raise RuntimeError("Lỗi kiểm thử")
    metadata = read(run.directory / "metadata.json")
    assert metadata["status"] == "failed" and metadata["ended_at"]
    assert metadata["error"]["type"] == "RuntimeError"
    assert "raise RuntimeError" in metadata["error"]["traceback"]
    assert metadata["error"]["message"] == "Lỗi kiểm thử"
    assert read(run.directory / "config.json")["is_test"] is True
    assert read(run.directory / "metrics.json") == {"partial": None}
    assert saved.read_text(encoding="utf-8") == "Dữ liệu kiểm thử"
    assert rows(logger)[0]["status"] == "failed"


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_interruption_propagates(logger, exception):
    with pytest.raises(exception):
        with start(logger) as run:
            raise exception("TEST ONLY: interrupted")
    assert rows(logger)[0]["status"] == "interrupted"
    assert read(run.directory / "metadata.json")["error"]["type"] == exception.__name__


def test_repeated_updates_and_finish_use_one_row(logger):
    run = start(logger)
    for value in range(3):
        run.log_metrics({"TEST_ONLY_metric": value})
    run.finish_run(notes="Kiểm thử thành công", decision="TEST ONLY: không kết luận")
    before = read(run.directory / "metadata.json")
    # Use a fresh instance to verify updates load persisted state.
    another = ExperimentLogger(logger.experiment_dir, project_root=logger.project_root)
    another.finish_run(run.run_id, notes="Cập nhật nhận xét kiểm thử")
    record, = rows(logger)
    assert record["notes"] == "Cập nhật nhận xét kiểm thử"
    assert record["ended_at"] == before["ended_at"]
    assert record["decision"] == before["decision"]
    assert json.loads(record["metrics"]) == {"TEST_ONLY_metric": 2}
    assert (run.directory / "notes.md").read_text(encoding="utf-8") == record["notes"]
    with pytest.raises(ValueError, match="final status"):
        another.finish_run(run.run_id, status="failed")
    with pytest.raises(ValueError, match="while running"):
        run.log_metrics({"TEST_ONLY_metric": 5})


def test_artifacts_isolated_no_overwrite_checksum_and_parent_link(logger, tmp_path):
    source = tmp_path / "TEST_ONLY.txt"
    source.write_bytes(b"TEST ONLY: first")
    with start(logger, kind="tuning") as parent:
        first = parent.log_artifact(source, name="predictions/TEST_ONLY.txt")
        with pytest.raises(FileExistsError):
            parent.log_artifact(source, name="predictions/TEST_ONLY.txt")
        source.write_bytes(b"TEST ONLY: second")
        with start(logger, parent_run_id=parent.run_id, reference_run_id=parent.run_id,
                   fold_id=0, parameters={"TEST_ONLY_parameter": 1}) as child:
            second = child.log_artifact(source, name="predictions/TEST_ONLY.txt")
    assert parent.run_id != child.run_id and first != second
    assert first.read_bytes() == b"TEST ONLY: first"
    assert second.read_bytes() == b"TEST ONLY: second"
    artifact, = read(parent.directory / "metadata.json")["artifacts"]
    assert (logger.experiment_dir / artifact["path"]).resolve() == first
    assert artifact["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert artifact["size_bytes"] == len(first.read_bytes())
    assert read(child.directory / "config.json")["parent_run_id"] == parent.run_id


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "C:\\outside.txt", "file:stream"])
def test_artifact_paths_cannot_escape(logger, tmp_path, name):
    source = tmp_path / "TEST_ONLY.txt"
    source.write_text("TEST ONLY", encoding="utf-8")
    with start(logger) as run:
        with pytest.raises(ValueError):
            run.log_artifact(source, name=name)


def test_parallel_threads_merge_same_run_without_lost_metrics(logger):
    with start(logger) as run:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda n: run.log_metrics({f"TEST_ONLY_{n}": n}), range(12)))
    record, = rows(logger)
    assert json.loads(record["metrics"]) == {f"TEST_ONLY_{n}": n for n in range(12)}


def test_parallel_processes_share_csv_and_same_run(logger, tmp_path):
    run = start(logger)
    script = tmp_path / "TEST_ONLY_worker.py"
    # Explicit path supports the project's portable interpreter as well as venvs.
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / 'src')!r})\n"
        "from beijing_air.experiment_logging import ExperimentLogger\n"
        "logger = ExperimentLogger(sys.argv[1], project_root=sys.argv[2])\n"
        "logger.log_metrics(sys.argv[3], {sys.argv[4]: 1})\n"
        "with logger.start_run(task_id='TEST_ONLY_worker', is_test=True):\n"
        "    pass\n", encoding="utf-8")
    processes = [subprocess.Popen(
        [sys.executable, str(script), str(logger.experiment_dir), str(tmp_path), run.run_id,
         f"TEST_ONLY_worker_{n}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) for n in range(3)]
    for process in processes:
        _, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
    run.finish_run()
    records = rows(logger)
    assert len(records) == len({row["run_id"] for row in records}) == 4
    assert all(row["status"] == "completed" for row in records)
    assert read(run.directory / "metrics.json") == {f"TEST_ONLY_worker_{n}": 1 for n in range(3)}


def test_index_replace_failure_preserves_csv_and_can_recover(logger, monkeypatch):
    with start(logger) as run:
        previous_csv = logger.csv_path.read_bytes()
        replace = os.replace

        def fail_csv(source, destination):
            if Path(destination) == logger.csv_path:
                raise PermissionError("TEST ONLY: simulate CSV open in Excel")
            return replace(source, destination)

        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", fail_csv)
            with pytest.raises(PermissionError):
                run.log_metrics({"TEST_ONLY_saved": 1})
        assert logger.csv_path.read_bytes() == previous_csv
        assert read(run.directory / "metrics.json") == {"TEST_ONLY_saved": 1}
        logger.rebuild_index()
        assert json.loads(rows(logger)[0]["metrics"]) == {"TEST_ONLY_saved": 1}
        assert not list(logger.experiment_dir.glob(".logger-*.tmp"))


def test_lock_timeout_leaves_existing_csv_intact(logger):
    with start(logger):
        previous = logger.csv_path.read_bytes()
        contender = ExperimentLogger(logger.experiment_dir, lock_timeout=0.05)
        with logger._locked():
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(contender.rebuild_index)
                with pytest.raises(TimeoutError):
                    future.result(timeout=5)
        assert logger.csv_path.read_bytes() == previous


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), object()])
def test_invalid_json_does_not_corrupt_existing_metrics(logger, invalid):
    with start(logger) as run:
        with pytest.raises((ValueError, TypeError)):
            run.log_metrics({"TEST_ONLY_invalid": invalid})
        assert read(run.directory / "metrics.json") == {}


def test_original_exception_survives_logger_io_error(logger, monkeypatch):
    with pytest.raises(RuntimeError, match="TEST ONLY: original"):
        with start(logger):
            def fail_finish(*args, **kwargs):
                raise OSError("TEST ONLY: disk error")
            monkeypatch.setattr(logger, "finish_run", fail_finish)
            raise RuntimeError("TEST ONLY: original")
    assert rows(logger)[0]["status"] == "running"  # Honest state on I/O failure.


def test_empty_index_has_no_invented_runs(logger):
    logger.rebuild_index()
    with logger.csv_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == list(CSV_FIELDS)
        assert list(reader) == []


def test_git_unavailable_is_null_without_fabricated_state(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("TEST ONLY: Git unavailable")
    monkeypatch.setattr(subprocess, "run", unavailable)
    assert _git_state(tmp_path) == {
        "commit": None, "branch": None, "dirty": None, "available": False,
    }
