"""Tests for scripts.unsub + scripts.lib.prompt_version."""

import os
import sys
import tempfile
import unittest

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts import unsub  # noqa: E402
from scripts.lib import prompt_version as pv  # noqa: E402
from scripts.lib import schema as schemalib  # noqa: E402


class TestListUnsubscribeParser(unittest.TestCase):
    def test_mailto_only(self):
        r = unsub.parse_list_unsubscribe("<mailto:unsubscribe@example.com>")
        self.assertEqual(r["mailto"], "unsubscribe@example.com")
        self.assertIsNone(r["https"])

    def test_https_only(self):
        r = unsub.parse_list_unsubscribe("<https://example.com/unsub?id=abc>")
        self.assertEqual(r["https"], "https://example.com/unsub?id=abc")
        self.assertIsNone(r["mailto"])

    def test_both(self):
        r = unsub.parse_list_unsubscribe(
            "<mailto:unsub@x.com>, <https://x.com/unsub>"
        )
        self.assertEqual(r["mailto"], "unsub@x.com")
        self.assertEqual(r["https"], "https://x.com/unsub")

    def test_empty(self):
        r = unsub.parse_list_unsubscribe("")
        self.assertEqual(r, {"mailto": None, "https": None})

    def test_malformed(self):
        # No angle brackets — ignored.
        r = unsub.parse_list_unsubscribe("mailto:naked@x.com")
        self.assertEqual(r, {"mailto": None, "https": None})


class TestBodyScraperFallback(unittest.TestCase):
    def test_basic_unsubscribe_url_extracted(self):
        body = "Thanks for subscribing. To stop, visit https://example.com/unsubscribe?id=abc"
        urls = unsub.extract_unsub_urls_from_body(body)
        self.assertEqual(urls, ["https://example.com/unsubscribe?id=abc"])

    def test_multiple_urls_deduped(self):
        body = """Click https://x.com/unsub?a=1 to unsub. Or
        https://x.com/unsub?a=1 again. Or https://y.com/opt-out."""
        urls = unsub.extract_unsub_urls_from_body(body)
        self.assertEqual(len(urls), 2)
        self.assertIn("https://x.com/unsub?a=1", urls)
        self.assertIn("https://y.com/opt-out", urls)

    def test_opt_out_variant(self):
        body = "visit http://x.com/OptOut to stop"
        urls = unsub.extract_unsub_urls_from_body(body)
        self.assertEqual(urls, ["http://x.com/OptOut"])

    def test_preferences_url(self):
        body = "manage at https://news.com/email-preferences now"
        urls = unsub.extract_unsub_urls_from_body(body)
        self.assertIn("https://news.com/email-preferences", urls)

    def test_no_match(self):
        body = "Hey, just checking in. Love, Mom"
        self.assertEqual(unsub.extract_unsub_urls_from_body(body), [])

    def test_trailing_punctuation_stripped(self):
        body = "see https://x.com/unsubscribe."
        self.assertEqual(unsub.extract_unsub_urls_from_body(body),
                         ["https://x.com/unsubscribe"])


class TestResolveUnsub(unittest.TestCase):
    def test_header_wins_over_body(self):
        thread = {
            "list_unsubscribe": "<mailto:h@hdr.com>",
            "body": "click https://body.com/unsubscribe",
        }
        r = unsub.resolve_unsub(thread)
        self.assertEqual(r["mailto"], "h@hdr.com")
        self.assertEqual(r["source"], "header")

    def test_body_fallback_when_no_header(self):
        thread = {
            "list_unsubscribe": "",
            "body": "click https://body.com/unsubscribe",
        }
        r = unsub.resolve_unsub(thread)
        self.assertEqual(r["https"], "https://body.com/unsubscribe")
        self.assertEqual(r["source"], "body_scrape")

    def test_none_source_when_nothing(self):
        thread = {"list_unsubscribe": "", "body": "hi mom"}
        r = unsub.resolve_unsub(thread)
        self.assertIsNone(r["mailto"])
        self.assertIsNone(r["https"])
        self.assertEqual(r["source"], "none")

    def test_plaintext_body_field_used(self):
        thread = {"plaintextBody": "click https://x.com/unsubscribe now"}
        r = unsub.resolve_unsub(thread)
        self.assertEqual(r["https"], "https://x.com/unsubscribe")


class TestUnsubSchema(unittest.TestCase):
    def test_valid_unsub_entry(self):
        entry = {
            "schema_version": "0.1",
            "timestamp_iso": "2026-04-19T15:00:00Z",
            "thread_id": "abc123",
            "sender": "news@x.com",
            "subject": "weekly digest",
            "action": "draft_queued",
            "status": "pending_review",
        }
        # No raise.
        schemalib.validate(entry, "unsub")

    def test_invalid_action(self):
        entry = {
            "schema_version": "0.1",
            "timestamp_iso": "2026-04-19T15:00:00Z",
            "thread_id": "abc",
            "sender": "x@y",
            "subject": "z",
            "action": "obliterate",   # not allowed
            "status": "pending_review",
        }
        with self.assertRaises(schemalib.SchemaError):
            schemalib.validate(entry, "unsub")


class TestPromptVersionParser(unittest.TestCase):
    def _write(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        f.write(content)
        f.close()
        self.addCleanup(lambda: os.remove(f.name))
        return f.name

    def test_header_parsed(self):
        path = self._write(
            "<!--\nprompt_version: \"0.2.1\"\nlast_changed: \"2026-04-19\"\n-->\n\n# Title"
        )
        r = pv.read_version(path)
        self.assertEqual(r["prompt_version"], "0.2.1")
        self.assertEqual(r["last_changed"], "2026-04-19")

    def test_no_header(self):
        path = self._write("# Just a title, no header\n\nbody")
        r = pv.read_version(path)
        self.assertIsNone(r["prompt_version"])
        self.assertIsNone(r["last_changed"])

    def test_missing_last_changed(self):
        path = self._write(
            "<!--\nprompt_version: \"0.1.0\"\n-->\n\n# Title"
        )
        r = pv.read_version(path)
        self.assertEqual(r["prompt_version"], "0.1.0")
        self.assertIsNone(r["last_changed"])

    def test_missing_file(self):
        r = pv.read_version("/nonexistent/path.md")
        self.assertIsNone(r["prompt_version"])

    def test_real_prompts_versioned(self):
        """The committed prompts/*.md must all carry a version header.

        This test encodes the expectation: any new prompt added to
        prompts/ must be versioned. If someone adds one without, this
        fails in CI.
        """
        prompts_dir = os.path.join(ROOT, "prompts")
        result = pv.read_all(prompts_dir)
        self.assertGreaterEqual(len(result), 1)
        for name, info in result.items():
            self.assertIsNotNone(
                info["prompt_version"],
                f"prompt {name!r} is missing a version header",
            )


if __name__ == "__main__":
    unittest.main()
