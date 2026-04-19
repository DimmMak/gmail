"""Smoke tests for scripts/stats.py and scripts/status.py.

These are integration-style: they run the CLI entry points with
the real log files (which should be empty or tiny in a fresh
checkout) and verify the processes complete without error.
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts import stats, status  # noqa: E402


class TestStatsSmoke(unittest.TestCase):
    def test_runs_clean(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = stats.run(["--days", "7"])
        self.assertEqual(rc, 0)
        self.assertIn("🟣 Volume", buf.getvalue())

    def test_json_mode(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = stats.run(["--days", "7", "--json"])
        self.assertEqual(rc, 0)
        import json
        doc = json.loads(buf.getvalue())
        self.assertIn("drafts", doc)
        self.assertIn("sent", doc)
        self.assertIn("health", doc)


class TestStatusSmoke(unittest.TestCase):
    def test_all_checks_pass_on_fresh_skill(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = status.run([])
        self.assertEqual(rc, 0, buf.getvalue())
        out = buf.getvalue()
        self.assertIn("🟢 HEALTHY", out)

    def test_no_send_invariant_detected(self):
        ok, detail = status.check_no_send()
        self.assertTrue(ok)
        self.assertIn("no send", detail.lower())


if __name__ == "__main__":
    unittest.main()
