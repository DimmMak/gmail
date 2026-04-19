"""Programmatic phishing detection for .gmail triage.

Problem this solves:
    The `spam-suspicious` rule in rules.json describes phishing signals
    in prose. Prose is for the LLM. This module adds deterministic
    signal checks the LLM can't fake — domain mismatches, suspicious
    TLDs, URL shorteners, name mismatches. Every signal is a PURE
    FUNCTION on inputs that Gmail MCP already returns.

Scope:
    - Stdlib only.
    - Pure functions. No I/O. No MCP calls. Caller passes the fields in.
    - Returns a Signal record, not a boolean. Aggregation is the caller's job.
    - Deterministic — same input, same output, no randomness, no model calls.

Design philosophy:
    We do NOT classify "phishing / not phishing" alone. We SCORE
    individual signals, and the triage harness combines signals with
    rules.json to make the final decision. This keeps the phishing
    layer a sensor, not a judge — matching the Intern / Senior /
    Architect separation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


# -----------------------------------------------------------------------------
# Tunable lists (move to config/phishing.json when they grow)
# -----------------------------------------------------------------------------

# TLDs with high phishing prevalence. Not "bad" — just elevated scrutiny.
SUSPICIOUS_TLDS = frozenset({
    "ru", "cn", "tk", "ml", "ga", "cf", "gq", "top", "xyz", "club",
    "work", "click", "loan", "download", "men", "pro",
})

# URL shorteners — phishing hides destination behind these.
URL_SHORTENERS = frozenset({
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd",
    "buff.ly", "rebrand.ly", "cutt.ly", "short.link", "tiny.cc",
    "rb.gy", "shorturl.at", "t.ly",
})

# Legitimate brand names commonly impersonated. If display_name claims
# this brand but sender_domain is unrelated → spoof signal.
IMPERSONATION_TARGETS = frozenset({
    "paypal", "amazon", "apple", "microsoft", "google", "netflix",
    "chase", "wells fargo", "bank of america", "irs", "usps", "fedex",
    "ups", "dhl", "linkedin", "facebook", "instagram", "coinbase",
    "binance", "dropbox", "docusign", "adobe",
})

# Urgency phrases that correlate with scams when combined with money language.
URGENCY_PHRASES = (
    "act now", "immediate action", "immediately", "within 24 hours",
    "final notice", "last warning", "your account will be",
    "suspended", "will be closed", "verify now", "click here now",
    "limited time", "urgent", "asap",
)

# Money-ask / value-transfer phrases.
MONEY_PHRASES = (
    "wire transfer", "bank transfer", "send money", "gift card",
    "bitcoin", "crypto", "invoice attached", "payment required",
    "refund pending", "claim your reward", "prize", "lottery",
    "inheritance", "compensation",
)


# -----------------------------------------------------------------------------
# Signal record
# -----------------------------------------------------------------------------

@dataclass
class Signal:
    """A single phishing signal with an intensity score 0.0-1.0.

    score is a heuristic weight, NOT a probability. Caller aggregates.
    """
    name: str
    score: float
    detail: str


@dataclass
class PhishingReport:
    """Aggregated phishing analysis of one email."""
    signals: list[Signal] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        """Sum of signal scores, clamped 0.0–1.0."""
        return min(1.0, sum(s.score for s in self.signals))

    @property
    def is_suspicious(self) -> bool:
        """Convenience: total score >= 0.5."""
        return self.total_score >= 0.5

    def to_dict(self) -> dict:
        return {
            "total_score": round(self.total_score, 3),
            "is_suspicious": self.is_suspicious,
            "signals": [
                {"name": s.name, "score": s.score, "detail": s.detail}
                for s in self.signals
            ],
        }


# -----------------------------------------------------------------------------
# Parsers
# -----------------------------------------------------------------------------

_SENDER_RE = re.compile(r"^\s*(?:\"?(.*?)\"?\s*)?<([^>]+)>\s*$|^([^<]+)$")


def parse_sender(sender: str) -> tuple[str, str]:
    """Parse 'Display Name <user@domain>' into (display_name, email).

    Handles:
        "PayPal" <support@paypal-secure.tk>
        PayPal <support@paypal-secure.tk>
        support@paypal-secure.tk
    """
    if not sender:
        return "", ""
    m = _SENDER_RE.match(sender.strip())
    if not m:
        return "", sender.strip()
    if m.group(2):  # display + angle-bracket form
        return (m.group(1) or "").strip(), m.group(2).strip().lower()
    # bare email form
    raw = (m.group(3) or "").strip()
    if "@" in raw:
        return "", raw.lower()
    return raw, ""


def domain_of(email: str) -> str:
    """Return the domain portion of an email, lowercased, or ''."""
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower()


def tld_of(domain: str) -> str:
    """Return the TLD of a domain, lowercased."""
    if "." not in domain:
        return ""
    return domain.rsplit(".", 1)[1].strip().lower()


# -----------------------------------------------------------------------------
# Individual signal checks (each returns Signal | None)
# -----------------------------------------------------------------------------

def _registrable_sld(domain: str) -> str:
    """Return the second-level-domain label (no TLD, no subdomains).

    'service.paypal.com'     → 'paypal'
    'paypal-secure.tk'       → 'paypal-secure'
    'bankofamerica.com'      → 'bankofamerica'
    'account.chase.co.uk'    → 'chase'   (best-effort for common ccTLDs)
    """
    parts = [p for p in domain.split(".") if p]
    if len(parts) < 2:
        return ""
    # Strip common two-part ccTLDs so '.co.uk' / '.com.au' don't confuse.
    two_part_ccs = {("co", "uk"), ("co", "jp"), ("com", "au"),
                    ("co", "nz"), ("com", "br"), ("co", "in")}
    if len(parts) >= 3 and (parts[-2], parts[-1]) in two_part_ccs:
        return parts[-3].lower()
    return parts[-2].lower()


def check_brand_spoof(display_name: str, sender_email: str) -> Signal | None:
    """Display name claims a brand; the sender's registrable SLD is not that brand.

    Legitimacy rule: the brand must equal the SECOND-LEVEL DOMAIN of the
    sender exactly. 'paypal.com' / 'service.paypal.com' are legit; any
    lookalike with the brand as a hyphenated prefix ('paypal-secure.tk')
    is flagged.
    """
    if not display_name or not sender_email:
        return None
    dn_lower = display_name.lower()
    domain = domain_of(sender_email)
    sld = _registrable_sld(domain)
    for brand in IMPERSONATION_TARGETS:
        if brand in dn_lower:
            brand_compact = brand.replace(" ", "")
            if sld == brand_compact:
                return None  # legit — SLD exactly matches brand
            return Signal(
                name="brand_spoof",
                score=0.7,
                detail=(
                    f"display '{display_name}' claims '{brand}' but sender SLD "
                    f"is '{sld}' (domain: {domain})"
                ),
            )
    return None


def check_suspicious_tld(sender_email: str) -> Signal | None:
    domain = domain_of(sender_email)
    tld = tld_of(domain)
    if tld in SUSPICIOUS_TLDS:
        return Signal(
            name="suspicious_tld",
            score=0.3,
            detail=f"sender TLD '.{tld}' has elevated phishing prevalence",
        )
    return None


def check_url_shorteners(body: str) -> Signal | None:
    if not body:
        return None
    body_lower = body.lower()
    hits = [s for s in URL_SHORTENERS if s in body_lower]
    if hits:
        return Signal(
            name="url_shorteners",
            score=0.25 + 0.1 * min(3, len(hits) - 1),
            detail=f"found URL shortener(s): {', '.join(hits[:3])}",
        )
    return None


def check_urgency_plus_money(subject: str, body: str) -> Signal | None:
    """Urgency alone is marketing. Urgency + money ask = scam."""
    text = f"{subject or ''} {body or ''}".lower()
    urg = [p for p in URGENCY_PHRASES if p in text]
    money = [p for p in MONEY_PHRASES if p in text]
    if urg and money:
        return Signal(
            name="urgency_plus_money",
            score=0.5,
            detail=f"urgency ({urg[0]}) + money-ask ({money[0]}) co-occur",
        )
    return None


def check_name_mismatch(
    subject: str,
    body: str,
    expected_first_names: Iterable[str],
) -> Signal | None:
    """Email greets you by a name that isn't yours.

    Low severity — often data-broker pollution, not phishing —
    but worth flagging.
    """
    text = f"{subject or ''} {body or ''}"
    # Find "Hi <Name>," or "Dear <Name>," or "<NAME>, ..." patterns.
    # Keep it simple — look at the first line's first capitalized word
    # after Hi/Hello/Dear/Hey, and uppercase subject-prefix names.
    greetings = re.findall(
        r"\b(?:hi|hello|dear|hey)\s+([A-Z][a-z]{2,})\b",
        text,
    )
    # Subject prefix form: "KADE, we've missed you"
    subj_prefix = re.findall(r"^([A-Z]{2,})(?=,)", (subject or "").strip())
    candidates = {n.lower() for n in greetings + subj_prefix}
    expected = {n.lower() for n in expected_first_names if n}
    if not candidates or not expected:
        return None
    foreign = candidates - expected
    if foreign:
        return Signal(
            name="name_mismatch",
            score=0.2,
            detail=f"greeted as {sorted(foreign)[0]!r}; expected one of {sorted(expected)}",
        )
    return None


def check_opaque_subdomain(sender_email: str) -> Signal | None:
    """First label is a known ESP-style opaque prefix (em-*, e1-*, etc.).

    Not necessarily phishing — many legit ESPs do this — but a signal.
    We only fire on KNOWN prefixes with an explicit separator (hyphen or
    digit). 'travel.foo.com' and 'account.foo.com' do NOT fire.
    """
    domain = domain_of(sender_email)
    first_label = domain.split(".", 1)[0] if "." in domain else domain
    # Must start with a known ESP prefix AND have either a digit or hyphen.
    # Examples that should fire:
    #   em-hrhcac, e3, mail-x1, track-abc, trk-001, em1
    # Examples that should NOT fire:
    #   travel, mail, account, support, news, em (too generic alone)
    if re.match(
        r"^(?:em\d+|em-[a-z0-9]{2,}|e\d+|e-[a-z0-9]{2,}"
        r"|mail-[a-z0-9]{2,}|track-[a-z0-9]{2,}|trk-?[a-z0-9]{2,}"
        r"|click-[a-z0-9]{2,}|t\d+)$",
        first_label,
    ):
        return Signal(
            name="opaque_subdomain",
            score=0.1,
            detail=f"sender uses opaque ESP-style prefix '{first_label}' (domain: {domain})",
        )
    return None


# -----------------------------------------------------------------------------
# Top-level API
# -----------------------------------------------------------------------------

def analyze(
    sender: str,
    subject: str,
    body: str,
    expected_first_names: Iterable[str] = ("dan", "danny", "dim"),
) -> PhishingReport:
    """Run all signal checks and return a PhishingReport.

    Inputs are what Gmail MCP already returns:
        sender — raw "Display <email>" string
        subject — email subject
        body — body text (or snippet, if full body unavailable)
        expected_first_names — names the recipient legitimately answers to

    Caller decides what to DO with the report. This module only senses.
    """
    display, email = parse_sender(sender)
    report = PhishingReport()

    for check in (
        lambda: check_brand_spoof(display, email),
        lambda: check_suspicious_tld(email),
        lambda: check_url_shorteners(body),
        lambda: check_urgency_plus_money(subject, body),
        lambda: check_name_mismatch(subject, body, expected_first_names),
        lambda: check_opaque_subdomain(email),
    ):
        signal = check()
        if signal is not None:
            report.signals.append(signal)

    return report
