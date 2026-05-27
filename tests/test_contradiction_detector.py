import pytest
from pathlib import Path
from src.contradiction_detector import (
    Contradiction, ContradictionKind, detect_contradictions,
)

def test_contradiction_kind_enum_values():
    assert ContradictionKind.METRIC_UPDATE.value == "metric_update"
    assert ContradictionKind.DECISION_REVERSAL.value == "decision_reversal"
    assert ContradictionKind.FACT_CORRECTION.value == "fact_correction"
    assert ContradictionKind.NO_CONFLICT.value == "no_conflict"

def test_contradiction_dataclass_minimal():
    c = Contradiction(
        target_path=Path("/x/a.md"),
        target_name="a",
        kind=ContradictionKind.METRIC_UPDATE,
        reason="hit rate 65 -> 66.3",
        confidence=0.85,
    )
    assert c.kind == ContradictionKind.METRIC_UPDATE
    assert 0 <= c.confidence <= 1
    assert c.new_body_excerpt == ""

def test_detect_returns_empty_when_mem_dir_empty(tmp_path):
    candidate = {"slug": "x", "title": "X", "body": "no related"}
    result = detect_contradictions(candidate, tmp_path)
    assert result == []


def test_recall_candidates_excludes_self_slug(tmp_path, write_memory, monkeypatch):
    from src.contradiction_detector import _recall_candidates

    own = write_memory(tmp_path, "new_metric.md",
                       "name: new-metric\ntype: feedback", "hit rate 66.3%")
    other = write_memory(tmp_path, "old_metric.md",
                         "name: old-metric\ntype: feedback", "hit rate 65%")

    def fake_hybrid(query, mem_dir, top_k):
        return [(own, 0.95), (other, 0.85)]
    monkeypatch.setattr("src.contradiction_detector._hybrid_search", fake_hybrid)

    candidate = {"slug": "new-metric", "title": "회수율", "body": "hit rate 66.3%"}
    found = _recall_candidates(candidate, tmp_path, top_k=5)

    paths = [p for p, _ in found]
    assert own not in paths
    assert other in paths
