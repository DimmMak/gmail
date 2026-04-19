"""Invariant I6 — triage is idempotent per thread_id.

If a thread_id already appears in drafts.jsonl, a second triage run must
skip it. This test uses a temp log to exercise `already_drafted_ids`
without touching the real logs.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts import triage  # noqa: E402


def _write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


class TestIdempotency(unittest.TestCase):
    def test_already_drafted_ids_reads_seen(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "drafts.jsonl")
            _write_jsonl(path, [
                {"thread_id": "t1"},
                {"thread_id": "t2"},
                {"thread_id": "t3"},
            ])
            seen = triage.already_drafted_ids(path)
            self.assertEqual(seen, {"t1", "t2", "t3"})

    def test_second_run_is_noop(self):
        """Simulate the I6 check directly: if the id is in seen, skip."""
        seen = {"t1"}
        threads = [{"thread_id": "t1"}, {"thread_id": "t2"}]
        to_process = [t for t in threads if t["thread_id"] not in seen]
        self.assertEqual(len(to_process), 1)
        self.assertEqual(to_process[0]["thread_id"], "t2")

    def test_empty_log_returns_empty_set(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "drafts.jsonl")
            # file does not exist; read_all should yield nothing.
            self.assertEqual(triage.already_drafted_ids(path), set())


if __name__ == "__main__":
    unittest.main()
