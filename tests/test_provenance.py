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
