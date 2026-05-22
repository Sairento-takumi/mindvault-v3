#!/usr/bin/env python3
"""MindVault v2 Sprint 4 — memory/*.md → BLOB-기반 vec + FTS5 이중 인덱서.

설계 결정:
- vec 저장은 sqlite-vec 대신 일반 BLOB 컬럼 + numpy float32 (macOS 시스템
  Python sqlite3의 enable_load_extension 미지원 회피). 메모리 ~100개 규모라
  성능 차이 무시 가능.
- 이중 임베딩: body 전체 + frontmatter description 각각. description은 정수만
  박혀있어 매칭 정밀도가 높아 검색 시 1.5x 가중.
- 변경 감지: mtime_ns 비교. 같으면 skip, 다르면 재임베딩 + DB upsert.
- 동시성: flock(LOCK_NB)로 동시 indexer 실행 차단.
- path traversal: symlink resolve 후 allowed_roots 하위 확인.
"""
from __future__ import annotations

import fcntl
import json
import re
import sqlite3
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import yaml

DATA_DIR = Path("/Users/yonghaekim/.claude/mindvault-v2")
DB_PATH = DATA_DIR / "index.db"
DEBUG_LOG = DATA_DIR / "debug.log"
LOCK_PATH = DATA_DIR / "memory-indexer.lock"
BGE_M3_URL = "http://localhost:8081/embed"
BGE_M3_TIMEOUT = 5  # seconds — 인덱싱 시점은 hook과 별개라 여유
EMBED_DIM = 1024
DEFAULT_MEMORY_DIRS = [
    Path("/Users/yonghaekim/.claude/projects/-Users-yonghaekim/memory"),
    Path("/Users/yonghaekim/.claude/projects/-Users-yonghaekim-my-folder/memory"),
]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

# 같은 디렉토리의 indexer.py(Sprint 1~3)에서 secret 마스킹 + open_db 재사용
sys.path.insert(0, str(Path(__file__).parent))
from indexer import redact, open_db  # noqa: E402


def _debug(msg: str) -> None:
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG.open("a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] mem-indexer: {msg}\n")
    except Exception:
        pass


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """마크다운에서 YAML frontmatter dict + 본문 분리. 실패 시 ({}, text)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            return {}, text
    except yaml.YAMLError:
        return {}, text
    return fm, text[m.end():]


def embed_text(text: str) -> list[float] | None:
    """BGE-M3 서버 호출 → 1024차원 dense 벡터. 실패 시 None."""
    text = (text or "").strip()
    if not text:
        return None
    body = json.dumps({"input": text}).encode("utf-8")
    req = urllib.request.Request(
        BGE_M3_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=BGE_M3_TIMEOUT) as resp:
            data = json.loads(resp.read())
        vec = data.get("vector")
        if not isinstance(vec, list) or len(vec) != EMBED_DIM:
            _debug(
                f"embed bad shape: type={type(vec).__name__} "
                f"len={len(vec) if isinstance(vec, list) else '?'}"
            )
            return None
        return vec
    except (TimeoutError, urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        _debug(f"embed fail: {type(e).__name__}: {e}")
        return None


def _safe_memory_path(path: Path, allowed_roots: list[Path]) -> bool:
    """path가 allowed_roots 중 하나의 하위인지 (symlink resolve 포함)."""
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        return False
    for root in allowed_roots:
        try:
            resolved.relative_to(root.resolve(strict=False))
            return True
        except ValueError:
            continue
    return False


def _collect_md_files(dirs: list[Path]) -> list[Path]:
    """memory/ 디렉토리에서 .md 수집. _staged/는 제외, symlink outside는 거부."""
    out: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            if any(part == "_staged" for part in p.parts):
                continue
            if not _safe_memory_path(p, dirs):
                _debug(f"unsafe path skip: {p}")
                continue
            out.append(p)
    return out


def _vec_to_blob(vec: list[float]) -> bytes:
    """list[float] → float32 little-endian bytes (numpy)."""
    return np.asarray(vec, dtype=np.float32).tobytes()


def _parse_memory_file(path: Path) -> tuple[dict, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        _debug(f"read fail {path}: {e}")
        return None
    fm, body = parse_frontmatter(text)
    return fm, redact(body)


def _acquire_lock():
    """flock(LOCK_NB) — 동시 실행 차단. lock 못 잡으면 None."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fh = LOCK_PATH.open("w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except BlockingIOError:
        fh.close()
        return None


def _release_lock(fh) -> None:
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def incremental_index(
    memory_dirs: list[Path] | None = None,
    db_path: Path | None = None,
) -> dict[str, int]:
    """변경된 .md만 재임베딩. 반환: {"updated", "skipped", "removed"}.

    lock 못 잡으면 즉시 0으로 반환 (다른 indexer가 작업 중).
    """
    if memory_dirs is None:
        memory_dirs = DEFAULT_MEMORY_DIRS
    if db_path is None:
        db_path = DB_PATH

    counts = {"updated": 0, "skipped": 0, "removed": 0}
    lock = _acquire_lock()
    if lock is None:
        _debug("lock busy — skip")
        return counts

    try:
        conn = open_db(db_path)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            existing = {
                r["path"]: r["mtime_ns"]
                for r in conn.execute("SELECT path, mtime_ns FROM memories")
            }
            present_files = _collect_md_files(memory_dirs)
            present_paths = {str(p) for p in present_files}

            # 1) 삭제된 파일 정리
            for stale_path in existing.keys() - present_paths:
                conn.execute("DELETE FROM memories WHERE path=?", (stale_path,))
                conn.execute(
                    "DELETE FROM memories_fts WHERE path=?", (stale_path,)
                )
                conn.execute(
                    "DELETE FROM memories_vec WHERE path=?", (stale_path,)
                )
                counts["removed"] += 1

            # 2) 신규/변경 파일 처리
            for p in present_files:
                try:
                    st = p.stat()
                except OSError:
                    continue
                sp = str(p)
                if existing.get(sp) == st.st_mtime_ns:
                    counts["skipped"] += 1
                    continue

                parsed = _parse_memory_file(p)
                if parsed is None:
                    continue
                fm, body = parsed
                name = (fm.get("name") or p.stem)
                description = (fm.get("description") or "")

                vec_body = embed_text(body) if body.strip() else None
                vec_desc = embed_text(description) if description.strip() else None

                conn.execute(
                    "DELETE FROM memories_fts WHERE path=?", (sp,)
                )
                conn.execute(
                    "DELETE FROM memories_vec WHERE path=?", (sp,)
                )
                conn.execute(
                    """
                    INSERT INTO memories(path, name, description, mtime_ns, indexed_at)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(path) DO UPDATE SET
                        name=excluded.name,
                        description=excluded.description,
                        mtime_ns=excluded.mtime_ns,
                        indexed_at=excluded.indexed_at
                    """,
                    (sp, name, description, st.st_mtime_ns, now),
                )
                conn.execute(
                    "INSERT INTO memories_fts(path, body) VALUES(?,?)",
                    (sp, body),
                )
                if vec_body is not None:
                    conn.execute(
                        "INSERT INTO memories_vec(path, kind, embedding) "
                        "VALUES(?,?,?)",
                        (sp, "body", _vec_to_blob(vec_body)),
                    )
                if vec_desc is not None:
                    conn.execute(
                        "INSERT INTO memories_vec(path, kind, embedding) "
                        "VALUES(?,?,?)",
                        (sp, "description", _vec_to_blob(vec_desc)),
                    )
                counts["updated"] += 1

            conn.commit()
        finally:
            conn.close()
    finally:
        _release_lock(lock)

    _debug(f"incremental: {counts}")
    return counts


def full_rebuild(
    memory_dirs: list[Path] | None = None,
    db_path: Path | None = None,
) -> int:
    """memories_* 데이터 비우고 재인덱싱 (sessions_* 보존)."""
    if db_path is None:
        db_path = DB_PATH
    conn = open_db(db_path)
    try:
        conn.execute("DELETE FROM memories")
        conn.execute("DELETE FROM memories_fts")
        conn.execute("DELETE FROM memories_vec")
        conn.commit()
    finally:
        conn.close()
    return incremental_index(memory_dirs, db_path)["updated"]


def main() -> int:
    t0 = time.time()
    try:
        c = incremental_index()
        _debug(f"main: {c} in {time.time()-t0:.2f}s")
    except Exception as e:
        _debug(f"FATAL: {e}\n{traceback.format_exc()}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
