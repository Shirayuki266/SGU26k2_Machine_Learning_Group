"""TEST_ONLY NB01 fixtures; no actual samples, weights, or experiment runs."""

from pathlib import Path

import pytest

from beijing_air.project_journey import Evidence, code_excerpt, locate, related_tests, safe_text


def test_ast_qualified_positions_follow_source_edits(tmp_path):
    file = tmp_path/"fixture.py"
    file.write_text("class Schema:\n    def check(self):\n        return True\n", encoding="utf-8")
    found = locate("Schema.check", [tmp_path])
    assert [(r["start"], r["end"], r["symbol"]) for r in found] == [(2, 3, "Schema.check")]
    file.write_text("\n\n"+file.read_text(encoding="utf-8"), encoding="utf-8")
    assert locate("Schema.check", [file])[0]["start"] == 4
    assert locate("nonexistent", [tmp_path]) == []


def test_evidence_refuses_samples_weights_and_path_escape(tmp_path):
    reader = Evidence(tmp_path)
    for name in ("data/raw/fixture.csv", "data/processed/samples_full/test.csv", "model.joblib", "demo.sqlite3", "../secret.txt"):
        with pytest.raises(ValueError):
            reader.read(name)
    (tmp_path/"TEST_ONLY_metrics.json").write_text('{"nhận xét": "đã kiểm tra", "metric": null}', encoding="utf-8")
    assert reader.json("TEST_ONLY_metrics.json")["nhận xét"] == "đã kiểm tra"
    assert reader.json("TEST_ONLY_missing.json") == {}
    assert reader.missing == ["Không tìm thấy artifact: TEST_ONLY_missing.json"]


def test_excerpt_limits_long_function_and_preserves_real_range(tmp_path):
    file = tmp_path/"fixture.py"
    file.write_text('def long_function():\n    """TEST_ONLY documentation."""\n'+"    value = 1\n"*80, encoding="utf-8")
    excerpt = code_excerpt(file, 1, 82)
    assert "TEST_ONLY documentation" in excerpt
    assert "actual source lines 1-82" in excerpt
    assert len(excerpt.splitlines()) < 60
    assert "LOCAL_PATH_REDACTED" in safe_text("fixture " + "C:"+chr(92)+"Users"+chr(92)+"TEST_ONLY")
    assert safe_text("https://example.org/file") == "https://example.org/file"


def test_test_map_lists_only_ast_existing_tests(tmp_path):
    directory = tmp_path/"tests"
    directory.mkdir()
    (directory/"test_fixture.py").write_text("# TEST_ONLY feature module\ndef test_real():\n    feature()\n\ndef helper():\n    pass\n", encoding="utf-8")
    result = related_tests(tmp_path, "fixture", "feature")
    assert result == ["tests/test_fixture.py::test_real"]


def test_notebook_template_has_all_tasks_flags_and_t13_labels(tmp_path):
    import importlib.util
    from beijing_air.project_journey import TASKS
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("nb01_builder", root/"scripts/build_project_journey.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import nbformat
    (tmp_path/"notebooks").mkdir()
    nb = nbformat.read(module.build_notebook(tmp_path), as_version=4)
    sources = "\n".join(c.source for c in nb.cells)
    assert "RERUN_LIGHT = False" in sources and "RERUN_HEAVY = False" in sources
    for task in TASKS:
        matches = [c for c in nb.cells if c.cell_type == "code" and f"J.task({task!r})" in c.source]
        assert len(matches) == 1
        if task in {"T04-LOG", "T10", "T13", "T14"}:
            assert "T13 artifact, chỉ đọc" in matches[0].source
            assert "T13-artifact-read-only" in matches[0].metadata.tags
    assert not any(c.outputs for c in nb.cells if c.cell_type == "code")
