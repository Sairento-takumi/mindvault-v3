#!/usr/bin/env python3
"""Arctic-ko snowflake-arctic-embed-l-v2.0-ko 의 MLX 4bit 양자화 변환.

install.sh Sprint 4.5 + tests/test_install_v320.py 가 공통으로 호출하는 단일 진입점.
mlx-community 에 4bit 양자화본이 없어서 사용자 환경에서 직접 변환 필요.

환경변수:
  MV3_CONVERT_DRY_RUN=1   실제 변환 안 하고 model.safetensors marker 만 생성 (테스트용)
  MV3_CONVERT_FAIL=1      dry-run 안에서 의도적 실패 (cleanup 테스트용)
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SOURCE_MODEL = "dragonkue/snowflake-arctic-embed-l-v2.0-ko"


def _cleanup_partial(target: Path) -> None:
    """변환 실패 시 partial 잔재 제거. 디렉토리 자체는 보존 (다음 실행에서 재사용)."""
    if not target.exists():
        return
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass


def convert(target: Path) -> int:
    target.mkdir(parents=True, exist_ok=True)
    marker = target / "model.safetensors"

    if marker.exists():
        print(f"  ✓ Arctic-ko model already present at {target}")
        return 0

    dry_run = os.environ.get("MV3_CONVERT_DRY_RUN") == "1"
    fail = os.environ.get("MV3_CONVERT_FAIL") == "1"

    if dry_run:
        if fail:
            _cleanup_partial(target)
            print("  ✗ convert FAILED (dry-run forced fail)", file=sys.stderr)
            return 1
        marker.write_bytes(b"dry-run-marker")
        print(f"  ✓ Arctic-ko model converted (dry-run) to {target}")
        return 0

    # 실제 변환 경로.
    try:
        from mlx_embeddings.utils import convert as mlx_convert
    except ImportError as e:
        print(f"  ✗ mlx_embeddings import 실패: {e}", file=sys.stderr)
        print(f"     pip install --user mlx_embeddings 후 재실행", file=sys.stderr)
        return 1

    try:
        mlx_convert(SOURCE_MODEL, mlx_path=str(target), quantize=True, q_bits=4)
    except Exception as e:
        _cleanup_partial(target)
        print(f"  ✗ Arctic-ko convert FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if not marker.exists():
        _cleanup_partial(target)
        print(f"  ✗ Arctic-ko convert finished but {marker} missing", file=sys.stderr)
        return 1

    print(f"  ✓ Arctic-ko model converted to {target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.home() / ".cache" / "mlx-arctic-ko",
        help="변환 결과 저장 경로 (default: ~/.cache/mlx-arctic-ko)",
    )
    args = parser.parse_args()
    return convert(args.target)


if __name__ == "__main__":
    sys.exit(main())
