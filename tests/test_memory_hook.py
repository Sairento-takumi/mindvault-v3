"""Sprint 4 Task 5 — UserPromptSubmit hook 계약 검증."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "memory-recall.py"


class TestHookIO(unittest.TestCase):
    """hook의 stdin/stdout 계약: 모든 실패 silent, exit 0."""

    def _run(self, payload: dict, timeout: float = 5.0) -> tuple[int, str, str]:
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=timeout,
        )
        return r.returncode, r.stdout.decode(), r.stderr.decode()

    def test_short_prompt_empty_output(self):
        rc, out, _ = self._run({"prompt": "ㅇ"})
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_malformed_stdin_silent(self):
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=b"not json at all",
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), b"")

    def test_no_prompt_field_silent(self):
        rc, out, _ = self._run({"session_id": "abc"})
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_empty_stdin_silent(self):
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=b"",
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), b"")


@unittest.skipIf(
    os.environ.get("MV2_SKIP_INTEGRATION") == "1",
    "MV2_SKIP_INTEGRATION=1",
)
class TestHookNormalFlow(unittest.TestCase):
    """실 BGE-M3 + ~/.claude/mindvault-v2/index.db 의존."""

    def test_real_query_format(self):
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"prompt": "메일 보내는 도구"}).encode(),
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(r.returncode, 0)
        # threshold 통과한 결과가 있으면 system-reminder 포맷
        if r.stdout.strip():
            out = r.stdout.decode()
            self.assertIn("<system-reminder>", out)
            self.assertIn("메모리 회수 (Layer 4 hybrid)", out)
            self.assertIn("</system-reminder>", out)


if __name__ == "__main__":
    unittest.main()
