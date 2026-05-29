"""bug-audit 2026-05-29 회귀 테스트 — extractor/turns_cache 데이터 유실·파싱 강건성.

커버하는 수정:
- extractor-greedy-json-1: parse_gemma_json 이 산문/대괄호가 섞인 출력에서도
  유효 JSON 배열을 추출 (greedy 매칭으로 통째로 버리던 회귀 차단).
- extractor-negcache-1: Gemma 호출 실패(서버 다운)로 인한 빈 결과는 캐시하지 않음
  (서버 복구 후 영구 추출 스킵 방지). 정상 빈 응답("[]")은 캐시.
- turns-cache-readfail-wipe-1: append-only jsonl 의 일시적 read 실패([] 반환)가
  기존 캐시 turn 을 영구 소실시키지 않음.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestParseGemmaJsonRobust(unittest.TestCase):
    def test_prose_and_brackets_around_array(self):
        from memory_extractor import parse_gemma_json
        out = (
            '참고[1]: 아래가 결과입니다 '
            '[{"type":"feedback","title":"t","body":"b","reason":"r","evidence":"e"}] '
            '끝 (추가 [노트])'
        )
        r = parse_gemma_json(out)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["title"], "t")

    def test_code_fence(self):
        from memory_extractor import parse_gemma_json
        out = '```json\n[{"type":"project","title":"x","body":"y","reason":"r","evidence":"e"}]\n```'
        self.assertEqual(len(parse_gemma_json(out)), 1)

    def test_direct_array(self):
        from memory_extractor import parse_gemma_json
        out = '[{"type":"feedback","title":"a","body":"b","reason":"r","evidence":"e"}]'
        self.assertEqual(len(parse_gemma_json(out)), 1)

    def test_empty_and_none(self):
        from memory_extractor import parse_gemma_json
        self.assertEqual(parse_gemma_json("[]"), [])
        self.assertEqual(parse_gemma_json(None), [])
        self.assertEqual(parse_gemma_json("해설만 있고 JSON 없음"), [])

    def test_leading_non_json_array_then_real_array(self):
        """앞에 dict 없는 list([\"note\"])가 와도 dict 담은 배열을 선택."""
        from memory_extractor import parse_gemma_json
        out = (
            '["메모"] 다음이 진짜 결과: '
            '[{"type":"feedback","title":"진짜","body":"b","reason":"r","evidence":"e"}]'
        )
        r = parse_gemma_json(out)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["title"], "진짜")


class TestExtractorNegativeCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.jsonl = Path(self.tmp.name) / "sess.jsonl"
        self.jsonl.write_text(
            json.dumps({
                "type": "user",
                "message": {"content": "이건 영구 기억해줘: 커밋은 논리 단위로 분리해라"},
                "timestamp": "2026-01-01T00:00:00Z",
            }) + "\n" +
            json.dumps({
                "type": "assistant",
                "message": {"content": "알겠습니다. 커밋을 논리 단위로 분리하겠습니다."},
                "timestamp": "2026-01-01T00:00:01Z",
            }) + "\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, gemma_return):
        import memory_extractor as me
        import extractor_cache
        put = MagicMock()
        with patch.object(me, "_always_fire", return_value=True), \
             patch.object(me, "call_gemma", return_value=gemma_return), \
             patch.object(extractor_cache, "cache_get", return_value=None), \
             patch.object(extractor_cache, "cache_put", put):
            out = me.extract_from_jsonl(self.jsonl)
        return out, put

    def test_server_down_empty_not_cached(self):
        out, put = self._run(None)  # call_gemma None = 서버 다운
        self.assertEqual(out, [])
        put.assert_not_called()

    def test_legit_empty_is_cached(self):
        out, put = self._run("[]")  # 서버가 응답했으나 후보 0건
        self.assertEqual(out, [])
        put.assert_called_once()

    def test_success_is_cached(self):
        valid = ('[{"type":"feedback","title":"커밋 분리","body":"커밋은 논리 단위로 분리",'
                 '"reason":"사용자 지시","evidence":"커밋은 분리"}]')
        out, put = self._run(valid)
        self.assertEqual(len(out), 1)
        put.assert_called_once()


class TestTurnsCacheReadFailWipe(unittest.TestCase):
    def test_transient_empty_read_does_not_wipe(self):
        import os
        import turns_cache as tc
        good = [{"ts_unix": 1.0, "role": "user", "text": "hi", "tool_uses": []}]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "turns.db"
            jp = Path(tmp) / "sess.jsonl"
            jp.write_text("non-empty jsonl content line\n")
            with patch.object(tc, "iter_session_jsonl_paths", return_value=[jp]), \
                 patch.object(tc, "load_turns", return_value=good):
                tc.refresh_cache(db_path=db)
            self.assertEqual(tc.cache_stats(db)["indexed_turns"], 1)

            # mtime 변경 + load_turns 가 일시적으로 [] (read 실패 시뮬) → 보존돼야
            os.utime(jp, (2_000_000_000, 2_000_000_000))
            with patch.object(tc, "iter_session_jsonl_paths", return_value=[jp]), \
                 patch.object(tc, "load_turns", return_value=[]):
                tc.refresh_cache(db_path=db)
            self.assertEqual(
                tc.cache_stats(db)["indexed_turns"], 1,
                "일시적 빈-read 가 기존 turn 을 wipe 하면 안 됨",
            )

            # 복구 후 정상 반영
            os.utime(jp, (3_000_000_000, 3_000_000_000))
            good2 = good + [{"ts_unix": 2.0, "role": "assistant", "text": "yo", "tool_uses": []}]
            with patch.object(tc, "iter_session_jsonl_paths", return_value=[jp]), \
                 patch.object(tc, "load_turns", return_value=good2):
                tc.refresh_cache(db_path=db)
            self.assertEqual(tc.cache_stats(db)["indexed_turns"], 2)


if __name__ == "__main__":
    unittest.main()
