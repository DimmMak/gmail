# Changelog — .gmail

All notable changes to this skill are documented here. Format loosely follows Keep-a-Changelog. Dates are ISO 8601.

---

## [0.1.2] — 2026-04-19

### Added
- `scripts/lib/phishing.py` — programmatic phishing signal detection.
  Pure functions, stdlib only. Six checks: brand_spoof, suspicious_tld,
  url_shorteners, urgency_plus_money, name_mismatch, opaque_subdomain.
  Returns a PhishingReport with per-signal scores (0.0-1.0 each) and a
  clamped total_score. Caller decides policy — this module only senses.
- `tests/test_phishing.py` — 24 tests covering parser, each check, and
  integration. Real-inbox cases from Harbor Freight (KADE name mismatch),
  Hard Rock AC (opaque ESP subdomain), and synthetic PayPal spoof all
  classified correctly.

### Fixed
- Brand-spoof check was bypassed by hyphenated look-alike domains like
  'paypal-secure.tk' — the old logic checked substring after stripping
  hyphens. New logic compares against the REGISTRABLE SLD (handles
  'service.paypal.com' as legit, 'paypal-secure.tk' as spoof). Added
  best-effort two-part ccTLD handling (.co.uk, .com.au, etc.).
- Opaque-subdomain regex over-triggered on generic prefixes — 'travel.*'
  and 'mail' alone wrongly fired. Tightened to require a known ESP
  prefix (em-, e\\d+, mail-, track-, trk-, click-, t\\d+) with explicit
  separator.
- `quote_verify` min-length lowered 6→4 chars (v0.1.2 carries forward).

### Test counts
- Total unittest cases: 47 (was 23 at v0.1).

---

## [0.1.1] — 2026-04-19

### Added
- `scripts/lib/dedupe.py` — two-pass dedupe for supersedable alerts. When
  a later system-alert arrives for the same resource (sender + normalized
  subject stem) within `dedupe_window_minutes`, earlier alerts are marked
  `status: superseded` with a reference to the winning `thread_id`. Fixes
  the stale-GitHub-failure-email class of bugs found in v0.1 stress test.
- `scripts/lib/quote_verify.py` — verbatim-quote enforcement. Before a
  draft is logged as `pending_review`, the drafter's `quoted_line` is
  checked as a normalized substring of the email body. Failures cap
  confidence to 1 and prefix the draft with a hallucination warning.
- Two new `rules.json` categories: `system-alert` (flag + dedupe) and
  `spam-suspicious` (flag, never draft).
- Status verb stripping in `dedupe.resource_key()` so that a later
  "Run succeeded:" alert supersedes earlier "Run failed:" alerts on the
  same workflow.

### Changed
- `schema.py` — `_ALLOWED_STATUS` now includes `superseded`.
- `triage.py` — two-pass pipeline: classify all, dedupe, then flush to
  log. Keeps log append-only while producing a deduped report.
- `draft` log entries now carry `quote_verified: bool` and
  `quote_verification_reason: str`.

### Fixed
- GAP 3 from v0.1 stress test: stale system alerts no longer pollute the
  flagged-for-human queue after a later success supersedes them.
- GAP "hallucination hardening" from v0.1 stress test: drafts claiming
  to quote the inbound email are now structurally verified, not merely
  instructed.

---

## [0.1] — 2026-04-19

### Added
- Initial skill scaffold at `~/Desktop/CLAUDE CODE/gmail/`.
- Tree structure: `config/`, `prompts/`, `scripts/`, `logs/`, `tests/`.
- `SKILL.md` front door with schema v0.3 frontmatter and subcommand table.
- `ARCHITECTURE.md` documenting 7 invariants (I1–I7), failure-mode table, half-life math.
- `SCHEMA.md` defining contracts for `rules.json`, `drafts.jsonl`, `sent.jsonl`, `audits.jsonl`.
- Six starting rule categories in `config/rules.json`: recruiter, linkedin-accept, newsletter, receipt, personal, consulting-inbound.
- Prompts: `triage.md`, `draft.md`, `audit.md`.
- Stdlib-only Python library: `gmail_client.py`, `log.py`, `schema.py`.
- Subcommand entry points: `triage.py`, `review.py`, `audit.py`, `migrate.py`.
- Placeholder test suite: `test_contract.py`, `test_schema.py`, `test_idempotency.py`.
- `install.sh` for symlink install into `~/.claude/skills/gmail/`.

### Invariants established
- I1 churn isolation, I2 append-only logs, I3 single source of truth, I4 schema versioning, I5 structural no-send, I6 idempotency, I7 graceful degradation.

### Notes
- MCP surface deliberately lacks a `send` tool. This is structural — not policy.
- Cowork fallback in `gmail_client.py` documented but raises `NotImplementedError`. Wired in a later version.
