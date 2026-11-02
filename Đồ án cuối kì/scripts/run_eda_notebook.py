"""Execute the T06 notebook from a fresh kernel using this Python interpreter."""

import argparse
import json
import os
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient
from jupyter_client import AsyncKernelManager
from jupyter_client.kernelspec import KernelSpecManager


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--split-manifest", default="reports/splits_full/split_manifest.json")
    parser.add_argument("--output-tag", help="New artifact suffix; existing outputs are never replaced")
    args = parser.parse_args()
    cache = root / "artifacts/t06_runtime"
    for env, name in (("MPLCONFIGDIR", "matplotlib"), ("IPYTHONDIR", "ipython"),
                      ("JUPYTER_CONFIG_DIR", "config"), ("JUPYTER_RUNTIME_DIR", "runtime")):
        path = cache / name
        path.mkdir(parents=True, exist_ok=True)
        os.environ[env] = str(path)
    kernel_dir = cache / "kernels/t06-local"
    kernel_dir.mkdir(parents=True, exist_ok=True)
    (kernel_dir / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "T06 current Python", "language": "python"}), encoding="utf-8")
    notebook_path = root / "notebooks/01_train_eda.ipynb"
    notebook = nbformat.read(notebook_path, as_version=4)
    nbformat.validate(notebook)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
        if "parameters" in cell.metadata.get("tags", []):
            cell.source = f"MODE = {args.mode!r}\nSPLIT_MANIFEST = {args.split_manifest!r}\nOUTPUT_TAG = {args.output_tag!r}"
    manager = AsyncKernelManager(kernel_name="t06-local", kernel_spec_manager=KernelSpecManager(
        kernel_dirs=[str(kernel_dir.parent)], ensure_native_kernel=False))
    # Fresh process and cleared outputs; portable Python needs no global kernelspec.
    client = NotebookClient(notebook, km=manager, timeout=600,
                            resources={"metadata": {"path": str(root)}})
    client.execute(cleanup_kc=True)
    executed = [c for c in notebook.cells if c.cell_type == "code"]
    if any(c.execution_count is None or any(o.output_type == "error" for o in c.outputs) for c in executed):
        raise RuntimeError("Notebook did not execute cleanly")
    output = notebook_path if args.mode == "full" and args.output_tag is None else cache / f"executed_{args.mode}_{args.output_tag or 'check'}.ipynb"
    # Keep the checked-in notebook's parameters ready for explicit future runs.
    nbformat.write(notebook, output)
    print(f"PASS: {len(executed)} cells executed from a fresh kernel; mode={args.mode}")
    print(f"Notebook: {output.relative_to(root)}")


if __name__ == "__main__":
    main()
