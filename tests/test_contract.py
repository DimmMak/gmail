"""Contract tests — enforce invariants I1-I7.

v0.1: these are mostly existence/import checks. Later versions expand
into behavioral assertions. Each test is tagged with the invariant it
defends.

Stdlib unittest only — pytest not required.
"""

from __future__ import annotations

import json
import os
import unittest

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))


class TestInvariantI1ChurnIsolation(unittest.TestCase):
    """I1 — configs, code, data, and logs live in separate dirs."""

    def test_dirs_exist(self):
        for d in ("config", "scripts", "logs", "prompts", "tests"):
            self.assertTrue(
                os.path.isdir(os.path.join(ROOT, d)),
                f"I1 violated: missing dir {d}/",
            )


class TestInvariantI2AppendOnly(unittest.TestCase):
    """I2 — log module exposes append + read, no update/delete."""

    def test_log_module_surface(self):
        from scripts.lib import log as loglib
        self.assertTrue(hasattr(loglib, "append"))
        self.assertTrue(hasattr(loglib, "read_all"))
        self.assertFalse(hasattr(loglib, "update"), "I2 violated: log.update exists")
        self.assertFalse(hasattr(loglib, "delete"), "I2 violated: log.delete exists")


class TestInvariantI3SingleSourceOfTruth(unittest.TestCase):
    """I3 — rules.json is the only category source; exists and parses."""

    def test_rules_json_present_and_valid(self):
        from scripts.lib import schema as schemalib
        with open(os.path.join(ROOT, "config", "rules.json"), encoding="utf-8") as f:
            doc = json.load(f)
        schemalib.validate_rules_file(doc)


class TestInvariantI4SchemaVersioning(unittest.TestCase):
    """I4 — schema module exposes CURRENT_SCHEMA_VERSION + validate."""

    def test_schema_surface(self):
        from scripts.lib import schema as schemalib
        self.assertTrue(hasattr(schemalib, "CURRENT_SCHEMA_VERSION"))
        self.assertTrue(hasattr(schemalib, "validate"))
        self.assertTrue(hasattr(schemalib, "SchemaError"))


class TestInvariantI5StructuralNoSend(unittest.TestCase):
    """I5 — GmailClient MUST NOT expose a send method."""

    def test_no_send_method(self):
        from scripts.lib.gmail_client import GmailClient
        self.assertFalse(
            hasattr(GmailClient, "send"),
            "I5 violated: GmailClient.send exists — send must not be implementable here.",
        )
        self.assertFalse(hasattr(GmailClient, "send_message"))
        self.assertFalse(hasattr(GmailClient, "deliver"))


class TestInvariantI6Idempotency(unittest.TestCase):
    """I6 — triage skips thread_ids already present in drafts.jsonl."""

    def test_triage_exposes_idempotency_helper(self):
        from scripts import triage
        self.assertTrue(hasattr(triage, "already_drafted_ids"))


class TestInvariantI7GracefulDegradation(unittest.TestCase):
    """I7 — backend failure must not raise out of triage.run (exit 0 path)."""

    def test_triage_has_run_entrypoint(self):
        from scripts import triage
        self.assertTrue(callable(getattr(triage, "run", None)))


class TestSubcommandEntryPoints(unittest.TestCase):
    """All three subcommands expose `run`."""

    def test_entry_points(self):
        from scripts import triage, review, audit, migrate
        self.assertTrue(callable(getattr(triage, "run", None)))
        self.assertTrue(callable(getattr(review, "run", None)))
        self.assertTrue(callable(getattr(audit, "run", None)))
        self.assertTrue(callable(getattr(migrate, "migrate", None)))


if __name__ == "__main__":
    unittest.main()
