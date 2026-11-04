"""Build/execute NB01 evidence notebook; no data preparation or model execution."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import nbformat

from beijing_air.project_journey import TASKS, TITLE, project_root


def build_notebook(root):
    md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell
    cells = [md("# Hành trình dự án PM2.5 — T01 đến T14\n\n"
                "**Dự báo nồng độ PM2.5 đúng một giờ tiếp theo tại các trạm Bắc Kinh.**\n\n"
                "NB01 / Issue #42 — tài liệu minh chứng có output sẵn. Mỗi mục trả lời: task dùng mã nào, "
                "file nào là cấu hình, file kết quả nằm đâu và kết quả ấy chứng minh điều gì. "
                "Không phải mọi task đều tạo một file kết quả mới: có bước xác minh terminal, đặc tả hoặc factories.\n\n"
                "Đọc tuần tự bản đồ → T01–T14/T04-LOG → RQ/tình huống bất lợi → kiểm chứng → phụ lục. "
                "Các đường dẫn tính từ thư mục đồ án chứa README/pyproject.toml. Audit/EDA ≠ log mô hình; smoke ≠ full.\n\n"
                "**Chỉ đọc minh chứng:** không training/tuning, không mở raw/processed samples hay weights. "
                "Test chỉ là artifact T13 đã lưu; mỗi cell liên quan có nhãn **T13 artifact, chỉ đọc**. "
                "Tài liệu cũ được trích theo snapshot, không sửa lịch sử hoặc dùng test chọn lại phương án."),
             code("RERUN_LIGHT = False\nRERUN_HEAVY = False\n\n"
                  "from beijing_air.project_journey import Journey, project_root\n"
                  "ROOT = project_root()\nJ = Journey(ROOT)\n"
                  "J.environment(RERUN_LIGHT, RERUN_HEAVY)"),
             md("## Bản đồ tổng thể\n\nT13 artifact, chỉ đọc: bảng chỉ mục có đường dẫn/run ID T13, không mở mẫu."),
             code("# T13 artifact, chỉ đọc — metadata/index only\nJ.overview()")]
    for task, spec in TASKS.items():
        label = "\n\n**T13 artifact, chỉ đọc** — chỉ đọc metadata/kết quả đã lưu." if task in {"T04-LOG", "T10", "T13", "T14"} else ""
        cells.append(md(f"## {task} — {spec[0]}"+label))
        source = ("# T13 artifact, chỉ đọc\n" if label else "")+f"J.task({task!r})"
        cells.append(code(source))
    cells.extend([
        md("## Tổng hợp và kết quả bất lợi\n\n**T13 artifact, chỉ đọc**."),
        code("# T13 artifact, chỉ đọc\nJ.synthesis()"),
        md("## Kiểm chứng chéo\n\n**T13 artifact, chỉ đọc**. Tính lại metric rẻ từ saved predictions/OOF, "
           "đối chiếu metrics.json và số báo cáo với dung sai 1e-6. Không sửa số cũ. "
           "Không tạo run; kiểm chứng luôn chạy vì là thao tác đọc nhẹ, không phải heavy experiment."),
        code("# T13 artifact, chỉ đọc\nJ.crosscheck()"),
        md("## Phụ lục và xuất bản đồ mã nguồn\n\n**T13 artifact, chỉ đọc**: kiểm kê nguồn đã đọc, không đọc thêm sample/weights. "
           "Chỉ ghi sản phẩm tài liệu NB01 mới."),
        code("# T13 artifact, chỉ đọc\nJ.appendix()\nverification = J.export()"),
    ])
    for index, cell in enumerate(cells):
        cell.id = f"nb01-{index:03d}"
        if "T13 artifact, chỉ đọc" in cell.source:
            cell.metadata["tags"] = ["T13-artifact-read-only"]
    nb = nbformat.v4.new_notebook(cells=cells)
    nb.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.metadata.language_info = {"name": "python", "version": sys.version.split()[0]}
    nb.metadata["nb01"] = {"task": "NB01", "issue": 42, "mode": "evidence_only",
                           "raw_samples_allowed": False, "model_loading_allowed": False}
    path = root/"notebooks"/(TITLE+".ipynb")
    nbformat.write(nb, path)
    return path


def protected_snapshot(root):
    """Only historical ledger/run metadata/config, not raw data or weights."""
    files = [root/"experiments/experiment_log.csv", root/"reports/ablation/frozen_model.json"]
    for pattern in ("artifacts/experiments/*/config.json", "artifacts/experiments/*/metadata.json",
                    "artifacts/experiments/*/metrics.json", "artifacts/experiments/*/notes.md", "configs/*.json"):
        files.extend(root.glob(pattern))
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(files)) if p.is_file()}


def execute(root, path):
    """A fresh kernel with filesystem audit hook blocks data/model access and run writes."""
    started = time.monotonic()
    before = protected_snapshot(root)
    work = root/"artifacts/nb01_work"
    kernel_dir = work/"jupyter/kernels/nb01-readonly"
    kernel_dir.mkdir(parents=True, exist_ok=True)
    # The audit hook is applied inside the kernel, before notebook imports.
    hook = work/"readonly_kernel.py"
    hook.write_text('''import os, sys
from pathlib import Path
root = Path(os.environ["NB01_PROJECT_ROOT"]).resolve()
def guard(event, args):
    if event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    path = Path(os.fsdecode(args[0])).resolve()
    if not path.is_relative_to(root):
        return
    rel = path.relative_to(root)
    if not rel.parts:
        return
    if rel.parts[0] == "data" or path.suffix.lower() in {".joblib", ".pkl", ".pickle", ".sqlite3"}:
        raise PermissionError("NB01 forbids raw/processed sample or model access")
    flags = args[2] if len(args) > 2 else 0
    writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
    if writing and (rel.parts[0] in {"experiments", "configs"} or rel.parts[:2] == ("artifacts", "experiments")):
        raise PermissionError("NB01 forbids experiment/config writes")
sys.addaudithook(guard)
from ipykernel.kernelapp import IPKernelApp
IPKernelApp.launch_instance()
''', encoding="utf-8")
    (kernel_dir/"kernel.json").write_text(json.dumps({"argv": [sys.executable, str(hook), "-f", "{connection_file}"],
            "display_name": "NB01 read-only evidence", "language": "python"}), encoding="utf-8")
    env = os.environ.copy()
    env["JUPYTER_PATH"] = str(work/"jupyter")+os.pathsep+env.get("JUPYTER_PATH", "")
    env["NB01_PROJECT_ROOT"] = str(root)
    # Keep Python imports/bytecode and matplotlib caches inside the workspace.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(work/"matplotlib")
    command = [sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace",
               "--ExecutePreprocessor.kernel_name=nb01-readonly", "--ExecutePreprocessor.timeout=240",
               str(path.relative_to(root))]
    result = subprocess.run(command, cwd=root, env=env, check=False)
    after = protected_snapshot(root)
    if before != after:
        raise RuntimeError("Historical experiment/config bytes changed during NB01")
    if result.returncode:
        raise RuntimeError("Notebook execution failed; inspect cell error without changing historical data")
    nb = nbformat.read(path, as_version=4)
    nb.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nbformat.write(nb, path)
    # Outputs are embedded; users can read the HTML without the local PNG files.
    from nbconvert import HTMLExporter
    exporter = HTMLExporter(template_name="lab")
    exporter.embed_images = True
    html, _ = exporter.from_notebook_node(nb)
    output = root/"reports/notebook"/(TITLE+".html")
    output.write_text(html, encoding="utf-8")
    for content in (path.read_text(encoding="utf-8"), html):
        if re.search(r"(?<!\w)[A-Za-z]:[\\/]|/(?:Users|home)/|gh[pousr]_[A-Za-z0-9]{30}|sk-[A-Za-z0-9]{30}", content):
            raise RuntimeError("Personal path or secret-like value found in generated notebook/HTML")
    errors = [o for c in nb.cells if c.cell_type == "code" for o in c.outputs if o.output_type == "error"]
    if errors:
        raise RuntimeError("Notebook retained error outputs")
    qa = {"task_id": "NB01", "executed_clean_kernel": True, "execution_tool": "jupyter nbconvert --execute",
          "elapsed_seconds": round(time.monotonic()-started, 3), "code_cells": sum(c.cell_type == "code" for c in nb.cells),
          "error_outputs": len(errors), "notebook_bytes": path.stat().st_size, "html_bytes": output.stat().st_size,
          "protected_files": len(before), "protected_bytes_unchanged": before == after,
          "raw_model_access_guard": "active in kernel, rejects sample data/model opens and experiment/config writes",
          "path_secret_scan": "PASS", "generated_at": datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")}
    (output.parent/"journey_execution.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Execute existing-evidence notebook in a fresh protected kernel")
    args = parser.parse_args()
    root = project_root()
    path = build_notebook(root)
    if args.execute:
        execute(root, path)
    else:
        print(path.relative_to(root).as_posix()+" generated; run with --execute to retain outputs")


if __name__ == "__main__":
    main()
