import datetime
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _load(monkeypatch, tmp_path):
    monkeypatch.setenv("MV3_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MV3_MEMORY_DIR", str(tmp_path / "memory"))
    spec = importlib.util.spec_from_file_location(
        "sme", Path(__file__).parent.parent / "src" / "session_memory_end.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_write_staged_records_source(monkeypatch, tmp_path):
    sme = _load(monkeypatch, tmp_path)
    item = {"type": "project", "title": "t", "reason": "r",
            "evidence": "e", "body": "b"}
    path = sme.write_staged(item, session_id="abcd1234-5678-90ab-cdef-111122223333")
    assert path is not None
    text = path.read_text()
    assert "source_type: session" in text
    assert "source_ref: abcd1234-5678-90ab-cdef-111122223333" in text


def test_write_staged_records_explicit_source_override(monkeypatch, tmp_path):
    sme = _load(monkeypatch, tmp_path)
    item = {"type": "project", "title": "t", "reason": "r",
            "evidence": "e", "body": "b"}
    path = sme.write_staged(item, session_id="abcd1234-5678-90ab-cdef-111122223333",
                            source_type="url", source_ref="https://youtu.be/abc123")
    assert path is not None
    text = path.read_text()
    assert "source_type: url" in text
    assert "source_ref: https://youtu.be/abc123" in text


def _fake_embed(_text):
    """1024차원, 모두 0.5인 unit vector."""
    return [0.5] * 1024


def test_recall_attaches_provenance(tmp_path):
    """recall_memory 반환 결과에 provenance 키가 부착되는지 검증."""
    from memory_indexer import incremental_index
    from memory_search import recall_memory

    # 격리된 fixture 생성
    memdir = tmp_path / "memory"
    memdir.mkdir()
    mem_file = memdir / "prov_test.md"
    mem_file.write_text(
        "---\n"
        "name: prov-test\n"
        "description: 출처 추적 테스트 메모리\n"
        "type: project\n"
        "staged_at: 2026-05-30T10:00:00\n"
        "staged_from_session: abcd1234\n"
        "source_type: session\n"
        "source_ref: abcd1234-5678-90ab-cdef-111122223333\n"
        "---\n\n"
        "메일 발송 노하우 본문 텍스트\n",
        encoding="utf-8",
    )

    tmp_db = tmp_path / "test.db"

    with patch("memory_indexer.embed_text", side_effect=_fake_embed):
        incremental_index([memdir], db_path=tmp_db)

    # FTS-only 모드로 recall (vec off → embed_text returns None)
    with patch("memory_search.embed_text", return_value=None):
        results = recall_memory(
            "메일",
            top_k=3,
            score_threshold=0.0,
            db_path=tmp_db,
        )

    assert results, "후보 없음 — fixture 확인"
    assert "provenance" in results[0]
    assert results[0]["provenance"]["source_type"] == "session"
    assert results[0]["provenance"]["source_ref"] == "abcd1234-5678-90ab-cdef-111122223333"
    assert results[0]["provenance"]["captured_at"] == datetime.datetime(2026, 5, 30, 10, 0)


# ─── Task 3: _format_output 출처 라벨 ────────────────────────────────────────

HOOK_PATH = Path(__file__).parent.parent / "hooks" / "memory-recall.py"


def _load_hook():
    """hooks/memory-recall.py 를 importlib 로 로드 (test_memory_hook.py 패턴 동일)."""
    spec = importlib.util.spec_from_file_location("hk_prov", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_format_output_shows_source_label():
    hook = _load_hook()
    results = [{
        "name": "x", "description": "d", "snippet": "", "score": 0.9,
        "source": ["vec"],
        "provenance": {"source_type": "session", "source_ref": "abcd1234-5678-90ab",
                       "captured_at": "2026-05-30T10:00:00"},
    }]
    out = hook._format_output(results)
    assert "출처:" in out
    assert "session" in out


def test_format_output_nonstring_source_type_does_not_crash():
    hook = _load_hook()
    results = [{
        "name": "x", "description": "d", "snippet": "", "score": 0.9,
        "source": ["vec"],
        "provenance": {"source_type": True, "source_ref": None, "captured_at": None},
    }]
    out = hook._format_output(results)  # must not raise
    assert "출처:" in out
    assert "True" in out


def test_format_output_unknown_source_suppressed():
    hook = _load_hook()
    results = [{
        "name": "x", "description": "d", "snippet": "", "score": 0.9,
        "source": ["vec"],
        "provenance": {"source_type": "unknown", "source_ref": None, "captured_at": None},
    }]
    out = hook._format_output(results)
    assert "출처:" not in out  # unknown → no label (noise suppression)


def test_format_output_datetime_captured_at():
    import datetime
    hook = _load_hook()
    results = [{
        "name": "x", "description": "d", "snippet": "", "score": 0.9,
        "source": ["vec"],
        "provenance": {"source_type": "session", "source_ref": "abcd1234ef",
                       "captured_at": datetime.datetime(2026, 5, 30, 10, 0)},
    }]
    out = hook._format_output(results)
    assert "출처: session" in out
    assert "2026-05-30" in out      # datetime str()[:10]
    assert "abcd1234" in out and "abcd1234e" not in out  # ref truncated to 8 chars


# ─── Task 4: 기존 메모리 backfill CLI ───────────────────────────────────────


def test_backfill_adds_source_from_staged_session(tmp_path):
    from src import provenance_backfill_cli as bf
    mem = tmp_path / "memory"; mem.mkdir()
    p = mem / "feedback_x.md"
    p.write_text("---\nname: x\ntype: feedback\nstaged_from_session: abcd1234\n---\n\nbody\n")
    n = bf.backfill_dir(mem, dry_run=False)
    assert n == 1
    text = p.read_text()
    assert "source_type: session" in text
    assert "source_ref: abcd1234" in text


def test_backfill_unknown_when_no_session(tmp_path):
    from src import provenance_backfill_cli as bf
    mem = tmp_path / "memory"; mem.mkdir()
    p = mem / "reference_y.md"
    p.write_text("---\nname: y\ntype: reference\n---\n\nbody\n")
    bf.backfill_dir(mem, dry_run=False)
    assert "source_type: unknown" in p.read_text()
    assert "source_ref" not in p.read_text()


def test_backfill_dry_run_no_write(tmp_path):
    from src import provenance_backfill_cli as bf
    mem = tmp_path / "memory"; mem.mkdir()
    p = mem / "feedback_z.md"
    original = "---\nname: z\ntype: feedback\nstaged_from_session: eeee9999\n---\n\nbody\n"
    p.write_text(original)
    n = bf.backfill_dir(mem, dry_run=True)
    assert n == 1  # 대상 건수는 반환
    assert p.read_text() == original  # 파일 내용 불변


def test_backfill_skips_unreadable_file(tmp_path):
    from src import provenance_backfill_cli as bf
    mem = tmp_path / "memory"; mem.mkdir()
    bad = mem / "bad.md"
    bad.write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    # must not raise; bad file simply not counted
    n = bf.backfill_dir(mem, dry_run=False)
    assert n == 0


# ─── Task 5: end-to-end 통합 (write→index→recall→format 출처 라벨) ─────────────


def test_e2e_staged_to_recall_label(tmp_path):
    """write_staged → index → recall_memory(provenance 부착) → _format_output(출처 라벨)
    전 구간이 연결되는지 검증하는 end-to-end 통합 테스트."""
    from memory_indexer import incremental_index
    from memory_search import recall_memory

    # 1. 격리된 tmp memory dir + source frontmatter 포함 파일 생성
    memdir = tmp_path / "memory"
    memdir.mkdir()
    mem_file = memdir / "e2e_prov_test.md"
    mem_file.write_text(
        "---\n"
        "name: e2e-prov-test\n"
        "description: end-to-end 출처 추적 테스트 메모리\n"
        "type: project\n"
        "staged_at: 2026-05-30T12:00:00\n"
        "staged_from_session: e2e11111\n"
        "source_type: session\n"
        "source_ref: e2e11111-2222-3333-4444-555566667777\n"
        "---\n\n"
        "한국어 검색 통합 테스트 본문 텍스트\n",
        encoding="utf-8",
    )

    tmp_db = tmp_path / "e2e_test.db"

    # 2. 인덱싱 (_fake_embed로 임베딩 대체)
    with patch("memory_indexer.embed_text", side_effect=_fake_embed):
        incremental_index([memdir], db_path=tmp_db)

    # 3. recall_memory 호출 (FTS-only 모드 — embed_text returns None)
    with patch("memory_search.embed_text", return_value=None):
        results = recall_memory(
            "한국어 검색",
            top_k=3,
            score_threshold=0.0,
            db_path=tmp_db,
        )

    assert results, "recall 후보 없음 — fixture 또는 FTS 쿼리 확인"
    assert "provenance" in results[0], "recall_memory가 provenance를 부착하지 않음"

    # 4. _format_output으로 출처 라벨 렌더링
    hook = _load_hook()
    out = hook._format_output(results)

    # 5. 체인 전체 검증: 출처 라벨 + source_type + source_ref 8자 prefix
    assert "출처:" in out, f"'출처:' 라벨이 출력에 없음:\n{out}"
    assert "session" in out, f"'session' source_type이 출력에 없음:\n{out}"
    assert "e2e11111" in out, f"source_ref 8자 prefix 'e2e11111'이 출력에 없음:\n{out}"
