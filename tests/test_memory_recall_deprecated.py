"""T8 — Layer 4 hook deprecated_by score decay tests.

Load hooks/memory-recall.py via importlib.util.spec_from_file_location
since the hyphen in the filename prevents normal import.
"""
from __future__ import annotations
import importlib.util
import pytest
from pathlib import Path


@pytest.fixture
def memory_recall_mod():
    """Load hooks/memory-recall.py as 'memory_recall_mod'."""
    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "hooks" / "memory-recall.py"
    spec = importlib.util.spec_from_file_location("memory_recall_mod", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_is_deprecated_detects_frontmatter(tmp_path, memory_recall_mod):
    dep = tmp_path / "a.md"
    dep.write_text(
        "---\nname: a\ndeprecated_by: [b]\ntype: feedback\n---\n\nbody\n",
        encoding="utf-8",
    )
    fresh = tmp_path / "b.md"
    fresh.write_text("---\nname: b\ntype: feedback\n---\n\nbody\n", encoding="utf-8")

    assert memory_recall_mod._is_deprecated(dep) is True
    assert memory_recall_mod._is_deprecated(fresh) is False


def test_is_deprecated_handles_missing_file(memory_recall_mod, tmp_path):
    """Non-existent file → False (no crash)."""
    missing = tmp_path / "does-not-exist.md"
    assert memory_recall_mod._is_deprecated(missing) is False


def test_is_deprecated_handles_no_frontmatter(tmp_path, memory_recall_mod):
    """File without frontmatter → False."""
    plain = tmp_path / "plain.md"
    plain.write_text("just markdown, no frontmatter", encoding="utf-8")
    assert memory_recall_mod._is_deprecated(plain) is False


def test_apply_deprecation_decay_multiplies_score(tmp_path, memory_recall_mod):
    dep = tmp_path / "a.md"
    dep.write_text(
        "---\nname: a\ndeprecated_by: [b]\n---\n\nbody\n",
        encoding="utf-8",
    )
    result = memory_recall_mod._apply_deprecation_decay(dep, original_score=0.85)
    expected = 0.85 * memory_recall_mod.DEPRECATED_DECAY
    assert abs(result - expected) < 1e-6


def test_apply_deprecation_decay_passthrough_non_deprecated(tmp_path, memory_recall_mod):
    fresh = tmp_path / "b.md"
    fresh.write_text("---\nname: b\n---\n\nbody\n", encoding="utf-8")
    assert memory_recall_mod._apply_deprecation_decay(fresh, 0.85) == 0.85


def test_apply_deprecation_decay_handles_zero_score(tmp_path, memory_recall_mod):
    dep = tmp_path / "a.md"
    dep.write_text("---\nname: a\ndeprecated_by: [b]\n---\n", encoding="utf-8")
    # 0 * 0.3 = 0
    assert memory_recall_mod._apply_deprecation_decay(dep, 0.0) == 0.0


def test_deprecated_decay_constant_is_03(memory_recall_mod):
    """DEPRECATED_DECAY = 0.3 (T8 spec)."""
    assert memory_recall_mod.DEPRECATED_DECAY == 0.3
