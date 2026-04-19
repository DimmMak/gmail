"""Schema validator tests — valid + invalid entries for each log type."""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts.lib import schema as schemalib  # noqa: E402


def _valid_draft():
    return {
        "schema_version": "0.1",
        "timestamp_iso": "2026-04-19T12:00:00+00:00",
        "thread_id": "t1",
        "thread_fingerprint": {"from": "a@b.com", "subject": "hi", "date_iso": "2026-04-19"},
        "category_id": "newsletter",
        "rules_version": "0.1",
        "draft_preview": "",
        "confidence": 4,
        "status": "pending_review",
    }


def _valid_sent():
    return {
        "schema_version": "0.1",
        "timestamp_iso": "2026-04-19T12:00:00+00:00",
        "thread_id": "t1",
        "original_draft_hash": "deadbeef",
        "final_text": "ok",
        "edit_distance": 0.9,
        "decision": "approved",
        "reviewer": "danny",
    }


def _valid_audit():
    return {
        "schema_version": "0.1",
        "timestamp_iso": "2026-04-19T12:00:00+00:00",
        "period": "2026-04",
        "sample_size": 0,
        "findings": {"by_category": {}},
        "suggested_prompt_changes": [],
    }


def _valid_rule():
    return {
        "id": "newsletter",
        "match": "anything",
        "action": "label",
        "min_confidence": 3,
    }


class TestValidEntries(unittest.TestCase):
    def test_draft_ok(self):
        schemalib.validate(_valid_draft(), "draft")

    def test_sent_ok(self):
        schemalib.validate(_valid_sent(), "sent")

    def test_audit_ok(self):
        schemalib.validate(_valid_audit(), "audit")

    def test_rule_ok(self):
        schemalib.validate(_valid_rule(), "rule")


class TestInvalidEntries(unittest.TestCase):
    def test_missing_schema_version(self):
        e = _valid_draft()
        del e["schema_version"]
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate(e, "draft")

    def test_bad_status(self):
        e = _valid_draft()
        e["status"] = "sent"  # not allowed; send is structurally impossible
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate(e, "draft")

    def test_bad_confidence(self):
        e = _valid_draft()
        e["confidence"] = 9
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate(e, "draft")

    def test_bad_decision(self):
        e = _valid_sent()
        e["decision"] = "maybe"
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate(e, "sent")

    def test_edit_distance_range(self):
        e = _valid_sent()
        e["edit_distance"] = 1.5
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate(e, "sent")

    def test_rule_action(self):
        e = _valid_rule()
        e["action"] = "send"
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate(e, "rule")

    def test_unknown_entry_type(self):
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate(_valid_draft(), "banana")


class TestRulesFile(unittest.TestCase):
    def test_duplicate_id(self):
        doc = {
            "schema_version": "0.1",
            "categories": [_valid_rule(), _valid_rule()],
        }
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate_rules_file(doc)


if __name__ == "__main__":
    unittest.main()
