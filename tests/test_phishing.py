"""Tests for scripts/lib/phishing.py"""

import os
import sys
import unittest

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts.lib import phishing as ph  # noqa: E402


class TestSenderParser(unittest.TestCase):
    def test_display_and_email(self):
        d, e = ph.parse_sender('"PayPal" <support@scam.ru>')
        self.assertEqual(d, "PayPal")
        self.assertEqual(e, "support@scam.ru")

    def test_no_quotes(self):
        d, e = ph.parse_sender("PayPal <support@paypal.com>")
        self.assertEqual(d, "PayPal")
        self.assertEqual(e, "support@paypal.com")

    def test_bare_email(self):
        d, e = ph.parse_sender("noreply@github.com")
        self.assertEqual(d, "")
        self.assertEqual(e, "noreply@github.com")

    def test_empty(self):
        d, e = ph.parse_sender("")
        self.assertEqual((d, e), ("", ""))


class TestBrandSpoof(unittest.TestCase):
    def test_spoofed_paypal(self):
        s = ph.check_brand_spoof("PayPal", "support@paypal-secure.tk")
        self.assertIsNotNone(s)
        self.assertEqual(s.name, "brand_spoof")

    def test_legit_paypal(self):
        s = ph.check_brand_spoof("PayPal", "service@paypal.com")
        self.assertIsNone(s)

    def test_bank_of_america_compact(self):
        # Space-separated brand matched against compacted domain.
        s = ph.check_brand_spoof("Bank of America", "alerts@bankofamerica.com")
        self.assertIsNone(s)

    def test_no_brand_in_display(self):
        s = ph.check_brand_spoof("Jane Doe", "jane@example.com")
        self.assertIsNone(s)


class TestTLD(unittest.TestCase):
    def test_ru_suspicious(self):
        self.assertIsNotNone(ph.check_suspicious_tld("foo@bar.ru"))

    def test_com_clean(self):
        self.assertIsNone(ph.check_suspicious_tld("foo@bar.com"))

    def test_no_domain(self):
        self.assertIsNone(ph.check_suspicious_tld(""))


class TestShorteners(unittest.TestCase):
    def test_bitly_found(self):
        s = ph.check_url_shorteners("Click https://bit.ly/abc now")
        self.assertIsNotNone(s)

    def test_multiple_hits_higher_score(self):
        one = ph.check_url_shorteners("visit bit.ly/a")
        two = ph.check_url_shorteners("visit bit.ly/a and tinyurl.com/b and goo.gl/c")
        self.assertIsNotNone(one)
        self.assertIsNotNone(two)
        self.assertGreater(two.score, one.score)

    def test_clean_body(self):
        self.assertIsNone(ph.check_url_shorteners("Visit github.com/DimmMak"))


class TestUrgencyMoney(unittest.TestCase):
    def test_urgency_alone_no(self):
        s = ph.check_urgency_plus_money("Urgent: meeting", "please come asap")
        self.assertIsNone(s)

    def test_money_alone_no(self):
        s = ph.check_urgency_plus_money("Your refund pending", "see attached")
        self.assertIsNone(s)

    def test_both_yes(self):
        s = ph.check_urgency_plus_money(
            "URGENT: account will be suspended",
            "Please send a wire transfer immediately to recover",
        )
        self.assertIsNotNone(s)


class TestNameMismatch(unittest.TestCase):
    def test_kade_mismatch(self):
        s = ph.check_name_mismatch(
            "KADE, we've missed you",
            "",
            expected_first_names=["dan", "danny"],
        )
        self.assertIsNotNone(s)

    def test_danny_ok(self):
        s = ph.check_name_mismatch(
            "Hi Danny, your offer",
            "",
            expected_first_names=["dan", "danny"],
        )
        self.assertIsNone(s)


class TestOpaqueSubdomain(unittest.TestCase):
    def test_em_prefix(self):
        s = ph.check_opaque_subdomain("noreply@em-hrhcac.com")
        self.assertIsNotNone(s)

    def test_clean_domain(self):
        s = ph.check_opaque_subdomain("support@github.com")
        self.assertIsNone(s)


class TestAnalyzeIntegration(unittest.TestCase):
    def test_obvious_phish_scores_high(self):
        report = ph.analyze(
            sender='"PayPal" <support@paypal-secure.tk>',
            subject="URGENT: Your account will be suspended",
            body="Please send a wire transfer immediately. Click https://bit.ly/xyz to verify.",
            expected_first_names=("dan", "danny"),
        )
        self.assertTrue(report.is_suspicious, report.to_dict())
        names = {s.name for s in report.signals}
        # Expect at least these three to fire:
        self.assertIn("brand_spoof", names)
        self.assertIn("suspicious_tld", names)
        self.assertIn("url_shorteners", names)

    def test_clean_email_scores_zero(self):
        report = ph.analyze(
            sender="Jane Doe <jane@example.com>",
            subject="Coffee next week?",
            body="Hey Danny, want to grab coffee?",
            expected_first_names=("dan", "danny"),
        )
        self.assertEqual(report.signals, [])
        self.assertFalse(report.is_suspicious)

    def test_total_score_clamped(self):
        # Hit many signals to confirm clamping to 1.0.
        report = ph.analyze(
            sender='"Amazon" <fraud@amazon-secure.ru>',
            subject="URGENT KADE: account suspended",
            body="send wire transfer NOW, click http://bit.ly/x and http://tinyurl.com/y",
            expected_first_names=("dan", "danny"),
        )
        self.assertLessEqual(report.total_score, 1.0)
        self.assertGreaterEqual(report.total_score, 0.5)


if __name__ == "__main__":
    unittest.main()
