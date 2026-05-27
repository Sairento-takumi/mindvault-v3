from __future__ import annotations

import enum
import os
import time
from dataclasses import dataclass
from pathlib import Path


def _debug(msg: str) -> None:
    """Emit to ~/.claude/mindvault-v3/debug.log (matches memory_search._debug pattern).

    MV3_RUNTIME_DIR 환경변수가 있으면 그 경로 우선, 없으면 default.
    """
    log_dir = os.environ.get("MV3_RUNTIME_DIR") or str(
        Path.home() / ".claude" / "mindvault-v3"
    )
    try:
        log_path = Path(log_dir) / "debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] contradiction: {msg}\n")
    except OSError:
        pass  # never raise from logging path


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
        candidate: {
            "slug": str,           # bare slug, no type prefix
            "title": str,
            "body": str,
            "type": str (optional),
            "path": Path | str (optional),  # explicit self-path for exclusion
        }
        mem_dir: memory/*.md 위치

    Returns:
        confidence ≥ CONFIDENCE_THRESHOLD 이고 kind != NO_CONFLICT 만.
    """
    return []  # 후속 tasks (T2~T4) 에서 채움


def _hybrid_search(query: str, mem_dir: Path, top_k: int = 5) -> list[tuple[Path, float]]:
    """memory_search.recall_memory 호출 후 (path, score) tuple 로 정규화.

    mem_dir filter: 결과 path 중 mem_dir subtree 안의 것만 (cross-project 잡음 제거).
    실패 시 빈 list + debug.log 에 사유 기록 (silent loss 방지).
    """
    from src import memory_search
    try:
        results = memory_search.recall_memory(query, top_k=top_k)
    except Exception as e:
        # Telemetry only — caller already handles []. memory_search.recall_memory
        # 자체가 FATAL+traceback 을 자기 로그에 남기므로 여기는 한 줄 요약으로 충분.
        _debug(f"recall_memory failed: {type(e).__name__}: {e}")
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
    """candidate.body+title 로 query 만들어 _hybrid_search 호출, self 제외.

    Self-exclusion 우선순위:
    1. candidate["path"] 있으면 path identity 비교 (가장 정확).
    2. 없으면 stem suffix match — production memory 파일이 "<type>_<slug>.md"
       (예: feedback_youtube_metadata_dump.md) 형태라서, slug="youtube-metadata-dump"
       만 가지고 stem 전체와 비교하면 절대 일치 안 함. suffix 매칭으로 보강.
    """
    title = candidate.get("title", "")
    body_excerpt = candidate.get("body", "")[:300]
    query = " ".join(p for p in (title, body_excerpt) if p).strip()
    if not query:
        return []

    results = _hybrid_search(query, mem_dir, top_k=top_k)

    # Self-exclusion. Prefer path identity (most reliable); fall back to stem
    # suffix match (handles "<type>_<slug>" prod naming convention).
    own_path = candidate.get("path")
    if own_path:
        try:
            own_resolved = Path(own_path).resolve()
        except (OSError, ValueError):
            own_resolved = None
    else:
        own_resolved = None

    own_slug = candidate.get("slug", "")
    own_stem_suffix = own_slug.replace("-", "_")  # underscore form

    def is_self(p: Path) -> bool:
        if own_resolved is not None and p == own_resolved:
            return True
        if not own_stem_suffix:
            return False
        # Match if stem == slug (bare) OR ends with "_<slug>" (handles type_ prefix).
        return p.stem == own_stem_suffix or p.stem.endswith("_" + own_stem_suffix)

    return [(p, s) for p, s in results if not is_self(p)]
