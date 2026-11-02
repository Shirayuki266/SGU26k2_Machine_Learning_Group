"""Local experiment records; no data loading, fitting, or metric calculation.

Per-run JSON is authoritative. The CSV is a rebuildable index, published with
atomic replacement under an OS file lock shared by all cooperating writers.
"""

from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
from importlib import metadata as package_metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import time
import traceback
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FIELDS = (
    "task_id", "reference_run_id", "parent_run_id", "fold_id", "mode", "kind",
    "objective", "hypothesis", "change", "model", "parameters", "feature_set",
    "preprocessing", "data", "split", "time_ranges", "sample_counts", "seed",
    "budget", "is_test", "source",
)
CSV_FIELDS = (
    "run_id", "status", *CONFIG_FIELDS, "started_at", "ended_at", "timezone",
    "duration_seconds", "git", "environment", "metrics", "artifacts", "notes",
    "decision", "error", "config_path", "metrics_path", "metadata_path", "notes_path",
)
_RUN_ID = re.compile(r"^[0-9a-f]{32}$")


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_text(path, content):
    """Keep the old complete file if writing or replacement fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".logger-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _git_state(root):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=10,
        ).stdout.strip()

    try:
        return {"commit": git("rev-parse", "HEAD"),
                "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(git("status", "--porcelain", "--untracked-files=normal")),
                "available": True}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "branch": None, "dirty": None, "available": False}


def _environment():
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": dict(sorted(
                (dist.metadata["Name"], dist.version)
                for dist in package_metadata.distributions() if dist.metadata["Name"]
            ))}


class ExperimentLogger:
    """Use one experiment_dir/artifact_dir pair per local experiment ledger."""

    def __init__(self, experiment_dir=None, artifact_dir=None, *, project_root=None,
                 lock_timeout=10.0):
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        self.experiment_dir = Path(
            experiment_dir or self.project_root / "experiments"
        ).resolve()
        self.artifact_dir = Path(
            artifact_dir or self.experiment_dir.parent / "artifacts" / "experiments"
        ).resolve()
        self.csv_path = self.experiment_dir / "experiment_log.csv"
        self.lock_timeout = lock_timeout

    @contextmanager
    def _locked(self):
        # OS locks are released even if the writer process dies. Never unlink
        # this file: replacing its inode would let writers lock different files.
        self.experiment_dir.mkdir(parents=True, exist_ok=True)
        with (self.experiment_dir / ".experiment_log.lock").open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Experiment log is locked by another writer")
                    time.sleep(0.02)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _run_dir(self, run_id):
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid run_id")
        path = self.artifact_dir / run_id
        if path.resolve().parent != self.artifact_dir:
            raise ValueError("Run directory must remain inside artifact_dir")
        return path

    def _load_run(self, run_id):
        directory = self._run_dir(run_id)
        return directory, _read(directory / "metadata.json")

    def _relative(self, path):
        return Path(os.path.relpath(path, self.experiment_dir)).as_posix()

    def _index(self):
        rows = []
        for path in sorted(self.artifact_dir.glob("*/metadata.json")):
            record = _read(path)
            directory = self._run_dir(record["run_id"])
            config = _read(directory / "config.json")
            metrics = _read(directory / "metrics.json")
            row = {**config, **record, "metrics": metrics}
            for name in ("config", "metrics", "metadata"):
                row[f"{name}_path"] = self._relative(directory / f"{name}.json")
            row["notes_path"] = self._relative(directory / "notes.md")
            rows.append({key: "" if row.get(key) is None else
                         _json(row[key]) if isinstance(row[key], (dict, list, bool))
                         else row[key] for key in CSV_FIELDS})
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        _atomic_text(self.csv_path, output.getvalue())

    def rebuild_index(self):
        """Recover a stale/missing CSV from authoritative per-run JSON files."""
        with self._locked():
            self._index()

    def start_run(self, *, notes=None, **config):
        if notes is not None and not isinstance(notes, str):
            raise TypeError("notes must be a string or None")
        unknown = config.keys() - set(CONFIG_FIELDS)
        if unknown:
            raise TypeError(f"Unknown config fields: {sorted(unknown)}")
        config = {key: config.get(key) for key in CONFIG_FIELDS}
        if config["mode"] not in (None, "smoke", "full"):
            raise ValueError("mode must be smoke, full, or None")
        if config["kind"] not in (None, "baseline", "train", "tuning", "ablation", "feature_selection"):
            raise ValueError("Unsupported experiment kind")
        # Validate and detach input before creating anything; reject NaN/Inf,
        # non-JSON objects, and accidental mutable aliases.
        config = json.loads(_json(config))
        run_id = uuid4().hex
        record = {
            "schema_version": 1, "run_id": run_id, "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(), "ended_at": None,
            "timezone": "UTC", "duration_seconds": None,
            "git": _git_state(self.project_root), "environment": _environment(),
            "artifacts": [], "notes": notes, "decision": None, "error": None,
        }
        _json(record)
        with self._locked():
            directory = self._run_dir(run_id)
            directory.mkdir(parents=True, exist_ok=False)
            _atomic_text(directory / "config.json", _json(config))
            _atomic_text(directory / "metrics.json", _json({}))
            _atomic_text(directory / "notes.md", notes or "")
            _atomic_text(directory / "metadata.json", _json(record))
            self._index()
        return ExperimentRun(self, run_id)

    def log_metrics(self, run_id, metrics, *, split=None):
        """Merge metric keys; with split, merge into that namespace only."""
        if not isinstance(metrics, dict):
            raise TypeError("metrics must be a dict")
        metrics = json.loads(_json(metrics))
        with self._locked():
            directory, record = self._load_run(run_id)
            if record["status"] != "running":
                raise ValueError("Metrics can only be logged while running")
            current = _read(directory / "metrics.json")
            if split is None:
                current.update(metrics)
            else:
                if not isinstance(split, str) or not split:
                    raise ValueError("split must be a nonempty string")
                group = current.setdefault(split, {})
                if not isinstance(group, dict):
                    raise ValueError("Metric namespace already contains a scalar")
                group.update(metrics)
            _atomic_text(directory / "metrics.json", _json(current))
            self._index()

    def log_artifact(self, run_id, source, *, name=None):
        """Copy a file into this run, refuse overwrite, and record its checksum."""
        source = Path(source)
        if not source.is_file():
            raise ValueError("Artifact source must be a file")
        relative = Path(name or source.name)
        if (relative.is_absolute() or relative.drive or ".." in relative.parts
                or not relative.name or any(":" in part for part in relative.parts)):
            raise ValueError("Artifact name must be a relative path inside the run")
        with self._locked():
            directory, record = self._load_run(run_id)
            if record["status"] != "running":
                raise ValueError("Artifacts can only be logged while running")
            base = directory / "artifacts"
            destination = base / relative
            if not destination.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Artifact path escapes run directory")
            if destination.exists():
                raise FileExistsError(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".logger-", dir=destination.parent)
            try:
                digest = hashlib.sha256()
                size = 0
                with os.fdopen(fd, "wb") as output, source.open("rb") as input_stream:
                    while chunk := input_stream.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
            record["artifacts"].append({"path": self._relative(destination),
                                        "sha256": digest.hexdigest(), "size_bytes": size})
            _atomic_text(directory / "metadata.json", _json(record))
            self._index()
        return destination

    def finish_run(self, run_id, *, status="completed", error=None, notes=None, decision=None):
        if any(value is not None and not isinstance(value, str) for value in (notes, decision)):
            raise TypeError("notes and decision must be strings or None")
        if error is not None and not isinstance(error, BaseException):
            raise TypeError("error must be an exception or None")
        if status not in ("completed", "failed", "interrupted"):
            raise ValueError("Invalid final status")
        if status == "completed" and error is not None:
            raise ValueError("A completed run cannot contain an error")
        error_record = None
        if error is not None:
            error_record = {"type": type(error).__name__, "message": str(error),
                            "traceback": "".join(traceback.format_exception(
                                type(error), error, error.__traceback__))}
        with self._locked():
            directory, record = self._load_run(run_id)
            if record["status"] not in ("running", status):
                raise ValueError("Cannot change a run's final status")
            if record["status"] == "running":
                end = datetime.now(timezone.utc)
                record.update(status=status, ended_at=end.isoformat(),
                              duration_seconds=(end - datetime.fromisoformat(record["started_at"])).total_seconds())
            if error_record is not None:
                record["error"] = error_record
            if notes is not None:
                record["notes"] = notes
            if decision is not None:
                record["decision"] = decision
            content = _json(record)
            _atomic_text(directory / "notes.md", record["notes"] or "")
            _atomic_text(directory / "metadata.json", content)
            self._index()


class ExperimentRun:
    """Run handle and context manager; exceptions propagate to the caller."""

    def __init__(self, logger, run_id):
        self.logger = logger
        self.run_id = run_id

    @property
    def directory(self):
        return self.logger._run_dir(self.run_id)

    def log_metrics(self, metrics, *, split=None):
        self.logger.log_metrics(self.run_id, metrics, split=split)

    def log_artifact(self, source, *, name=None):
        return self.logger.log_artifact(self.run_id, source, name=name)

    def finish_run(self, **kwargs):
        self.logger.finish_run(self.run_id, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        status = "completed" if exc is None else "interrupted" if isinstance(
            exc, (KeyboardInterrupt, SystemExit)) else "failed"
        try:
            self.finish_run(status=status, error=exc)
        except Exception as logging_error:
            if exc is None:
                raise
            # Preserve the original experiment exception even on logger I/O failure.
            if hasattr(exc, "add_note"):
                exc.add_note(f"Experiment logger also failed: {logging_error}")
        return False
