"""Verbatim-quote verifier for Intern drafts.

Problem this solves (hallucination hardening, FIX #2 from v0.1 stress test):
    The draft prompt tells the LLM to include a `quoted_line` copied
    verbatim from the inbound email. But "tells" is not "enforces."
    This module checks programmatically: does the quoted_line actually
    appear in the source email body? If not, the draft is rejected
    BEFORE it's logged as pending_review.

Scope: pure functions, stdlib only. Deterministic.

Mechanism:
    1. Normalize both the quoted_line and the email body
       (collapse whitespace, lowercase, strip smart-quote/curly-apostrophe
       variants).
    2. If normalized quoted_line is a substring of normalized body → OK.
    3. Otherwise → fail, with a reason.

    `<none>` is an allowed sentinel (when the drafter decided no line was
    worth quoting and lowered confidence to 1 per the prompt spec).
"""

from __future__ import annotations

import re
import unicodedata


_WS = re.compile(r"\s+")

# Smart-quote → dumb-quote normalization.
_QUOTE_MAP = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201A": "'", "\u201B": "'",
    "\u201C": '"', "\u201D": '"', "\u201E": '"', "\u201F": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00A0": " ",  # nbsp
})


def _normalize(text: str) -> str:
    """Lowercase, dumb-quote, unicode-normalize, collapse whitespace."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.translate(_QUOTE_MAP)
    t = t.lower()
    t = _WS.sub(" ", t).strip()
    return t


def verify(quoted_line: str, email_body: str) -> tuple[bool, str]:
    """Return (ok, reason).

    ok=True means quoted_line is a verbatim (after normalization) substring
    of email_body, OR quoted_line is the sentinel '<none>'.

    ok=False reasons are human-readable for logging.
    """
    if quoted_line is None:
        return False, "quoted_line is None"

    stripped = quoted_line.strip()
    if stripped == "<none>":
        return True, "sentinel <none> accepted (drafter declined to quote)"

    if len(stripped) < 6:
        # Too short to be meaningful — likely hallucinated filler.
        return False, f"quoted_line too short ({len(stripped)} chars); minimum 6"

    needle = _normalize(stripped)
    haystack = _normalize(email_body or "")

    if not haystack:
        return False, "email_body is empty; cannot verify quote"

    if needle in haystack:
        return True, "verbatim match"

    # Try a looser match: drop leading/trailing punctuation.
    loose = needle.strip(".,;:!?()[]\"'- ")
    if loose and loose in haystack:
        return True, "match after stripping edge punctuation"

    return False, "quoted_line not found in email_body (hallucination suspected)"


def enforce_or_downgrade(draft: dict, email_body: str) -> dict:
    """Return a possibly-modified copy of `draft` with enforcement applied.

    If the quoted_line fails verification:
      - confidence is capped to 1
      - a 'quote_verification' field is added with {'ok': False, 'reason': ...}
      - the draft_body is PREFIXED with a warning comment so human reviewer
        sees it during `.gmail review`

    If verification passes:
      - 'quote_verification': {'ok': True, 'reason': ...}

    The draft dict is not stored directly in the log — the log stores
    draft_preview + quote_verification. Callers should read
    `out['quote_verification']['ok']` to decide whether to proceed.
    """
    out = dict(draft)  # shallow copy — we only mutate top-level keys
    quoted = out.get("quoted_line", "")
    ok, reason = verify(quoted, email_body)

    out["quote_verification"] = {"ok": ok, "reason": reason}

    if not ok:
        out["confidence"] = 1
        body = out.get("draft_body", "")
        warning = (
            "[⚠️ QUOTE UNVERIFIED — possible hallucination. Reason: "
            f"{reason}. Human review required.]\n\n"
        )
        out["draft_body"] = warning + body

    return out
