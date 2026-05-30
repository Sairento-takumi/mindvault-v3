#!/usr/bin/env python3
"""기존 메모리에 source_type/source_ref 소급 부여. 억측 금지: staged_from_session
있으면 session, 없으면 unknown. atomic write (tmp + os.replace)."""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_indexer import parse_frontmatter  # noqa: E402


def _has(fm: dict, key: str) -> bool:
    return key in fm and fm[key] not in (None, "")


def backfill_file(path: Path, dry_run: bool) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    fm, body = parse_frontmatter(text)
    if not fm or _has(fm, "source_type"):
        return False
    if _has(fm, "staged_from_session"):
        st, ref = "session", str(fm["staged_from_session"])
    else:
        st, ref = "unknown", ""
    lines = text.split("\n")
    close = lines.index("---", 1)  # frontmatter 닫는 '---'
    inject = [f"source_type: {st}"]
    if ref:
        inject.append(f"source_ref: {ref}")
    new = lines[:close] + inject + lines[close:]
    out = "\n".join(new)
    if dry_run:
        return True
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(out, encoding="utf-8")
        os.replace(tmp, path)
        return True
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def backfill_dir(d: Path, dry_run: bool) -> int:
    n = 0
    for p in sorted(d.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        if backfill_file(p, dry_run):
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("memory_dir")
    ap.add_argument("--apply", action="store_true", help="실제 쓰기 (기본 dry-run)")
    a = ap.parse_args()
    n = backfill_dir(Path(a.memory_dir), dry_run=not a.apply)
    print(f"{'적용' if a.apply else 'dry-run'}: {n}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
