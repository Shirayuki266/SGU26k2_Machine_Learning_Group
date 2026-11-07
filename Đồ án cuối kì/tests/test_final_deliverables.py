import json
from pathlib import Path

from beijing_air.final_deliverables import (
    ROOT,
    collect_evidence,
    protected_snapshot,
    verify_final_deliverables,
)


def test_final_evidence_is_source_linked_and_uses_locked_t13_model():
    evidence = collect_evidence(ROOT)
    assert evidence["dataset"]["dataset_id"] == 501
    assert evidence["models"]["random_forest"]["run_id"] == "24cd6d765f214d52aa26e5988380e2cd"
    assert evidence["models"]["random_forest"]["mae_reduction_pct"] > 0
    assert evidence["models"]["ridge"]["mae_reduction_pct"] < 0
    assert evidence["t17b"]["oof_ridge_stack"]["validation_MAE"] < evidence["t17b"]["fusion_3"]["validation_MAE"]
    assert evidence["summary_rows"] == 27
    assert evidence["t13_execution"]["test_samples_accessed"] is True
    assert evidence["t17b_requested_failed_run_found"] is False
    assert evidence["t17b_parent_run_id"] == "2512bc9c844a4b39a150c52f6bded9db"
    assert len(evidence["summary_run_ids"]) == 27
    assert round(evidence["grouped_metrics"]["station|Dingling|random_forest"]["MAE"], 4) == 8.5951
    assert round(evidence["grouped_metrics"]["season|JJA|random_forest"]["MAE"], 4) == 7.6437
    assert evidence["evidence_conflicts"][0]["requested_value"] == 8.6287
    assert evidence["evidence_conflicts"][1]["requested_value"] == 6.6666


def test_final_verifier_checks_generated_artifacts_and_preserves_history(tmp_path):
    expected = protected_snapshot(ROOT)
    build_dir = ROOT / "reports/final"
    result = verify_final_deliverables(ROOT, build_dir)
    assert result["status"] == "PASS_WITH_DRAFT_PLACEHOLDERS_AND_SOURCE_CONFLICTS"
    assert result["presentation_slides"] == 18
    assert result["poster_png_dimensions"] == [2400, 3200]
    assert result["test_raw_samples_accessed"] is False
    assert result["model_fit_performed"] is False
    assert protected_snapshot(ROOT) == expected


def test_traceability_contains_only_relative_source_paths():
    trace_path = ROOT / "reports/final/traceability.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["ledger_written"] is False
    assert trace["t17b_parent_run_id"] == "2512bc9c844a4b39a150c52f6bded9db"
    for path in trace["source_hashes"]:
        assert not Path(path).is_absolute()
        assert "\\" not in path
