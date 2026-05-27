from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path


class ContradictionKind(str, enum.Enum):
    METRIC_UPDATE = "metric_update"
    DECISION_REVERSAL = "decision_reversal"
    FACT_CORRECTION = "fact_correction"
    NO_CONFLICT = "no_conflict"


@dataclass
class Contradiction:
    target_path: Path
    target_name: str
    kind: ContradictionKind
    reason: str
    confidence: float
    new_body_excerpt: str = ""
    old_body_excerpt: str = ""


def detect_contradictions(candidate: dict, mem_dir: Path) -> list[Contradiction]:
    """Hybrid recall + Gemma 분류로 candidate 와 mem_dir 안 충돌 후보 검출.

    Args:
        candidate: {"slug", "title", "body", "type" (optional)}
        mem_dir: memory/*.md 위치

    Returns:
        confidence ≥ CONFIDENCE_THRESHOLD 이고 kind != NO_CONFLICT 만.
    """
    return []  # 후속 tasks (T2~T4) 에서 채움


def _hybrid_search(query: str, mem_dir: Path, top_k: int = 5) -> list[tuple[Path, float]]:
    """memory_search.recall_memory 호출 후 (path, score) tuple 로 정규화.

    mem_dir filter: 결과 path 중 mem_dir subtree 안의 것만 (cross-project 잡음 제거).
    """
    from src import memory_search
    try:
        results = memory_search.recall_memory(query, top_k=top_k)
    except Exception:
        return []

    mem_root = mem_dir.resolve()
    out: list[tuple[Path, float]] = []
    for r in results:
        p_raw = r.get("path")
        if not p_raw:
            continue
        try:
            p = Path(p_raw).resolve()
        except (OSError, ValueError):
            continue
        try:
            p.relative_to(mem_root)  # raises ValueError if not under mem_root
        except ValueError:
            continue
        out.append((p, float(r.get("score", 0.0))))
    return out


def _recall_candidates(
    candidate: dict, mem_dir: Path, top_k: int = 5,
) -> list[tuple[Path, float]]:
    """candidate.body+title 로 query 만들어 _hybrid_search 호출, self-slug 제외."""
    title = candidate.get("title", "")
    body_excerpt = candidate.get("body", "")[:300]
    query = " ".join(p for p in (title, body_excerpt) if p).strip()
    if not query:
        return []

    results = _hybrid_search(query, mem_dir, top_k=top_k)

    own_slug = candidate.get("slug", "")
    own_stem = own_slug.replace("-", "_")
    return [(p, s) for p, s in results if p.stem != own_stem]
