"""Sprint 4 Task 6 — recall_cli --source 확장 검증."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

CLI = Path(__file__).parent.parent / "src" / "recall_cli.py"


class TestRecallCLI(unittest.TestCase):
    def test_memory_source_only(self):
        """--source memory: out에 memory 키만, sessions 없음."""
        r = subprocess.run(
            [sys.executable, str(CLI), "메일", "--source", "memory"],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout.decode())
        self.assertIn("memory", data)
        self.assertNotIn("sessions", data)
        self.assertEqual(data["query"], "메일")
        # memory 결과는 list
        self.assertIsInstance(data["memory"], list)

    def test_default_source_is_both(self):
        """인자 없으면 both: memory + sessions 둘 다."""
        r = subprocess.run(
            [sys.executable, str(CLI), "테스트짧은쿼리"],
            capture_output=True,
            timeout=120,  # Gemma 재순위/요약 포함하면 시간 걸림
        )
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout.decode())
        self.assertIn("query", data)
        self.assertIn("memory", data)
        self.assertIn("sessions", data)

    def test_invalid_source_rejected(self):
        """잘못된 --source는 argparse가 거부 (rc != 0)."""
        r = subprocess.run(
            [sys.executable, str(CLI), "x", "--source", "garbage"],
            capture_output=True,
            timeout=5,
        )
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
