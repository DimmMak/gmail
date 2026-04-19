# Changelog — .gmail

All notable changes to this skill are documented here. Format loosely follows Keep-a-Changelog. Dates are ISO 8601.

---

## [0.1.10] — 2026-04-19

### Added — closing pro-grade stress-test gap
- `phishing.check_homograph(display, email)` — detects brand spoofs
  using Cyrillic/Greek/fullwidth/Latin-1 confusables (e.g. `Аmazon` with
  Cyrillic А vs legit `Amazon`). Runs BEFORE brand_spoof in the pipeline
  so homograph attempts flagged even when SLD looks legit-ish.
- `_fold_confusables(text)` — explicit mapping-based fold. Audit-friendly
  alternative to full Unicode TR#36/39 dep. Covers most-abused homograph
  set in phishing corpora (Cyrillic А/В/Е/К/О/Р/Т/Х, Greek А/Р, etc.).
- 6 new unit tests for homograph detection (79 total, was 73).

### Why it matters
Professional-grade threat surface. `Аmazon` with Cyrillic А was a
documented blind spot in the v0.1.9 stress test report. Now flagged
as a 0.6-score signal — lower than brand_spoof (0.7) because domain
evidence is weaker, but combined with other signals (TLD, shortener)
still trips the 0.5 suspicious threshold.

---

## [0.1.9] — 2026-04-19

### Fixed
- **Major live-test finding:** Gmail MCP `get_thread` does NOT expose
  the RFC 2369 `List-Unsubscribe` header. The entire unsub.py pipeline
  was broken against real MCP data (found by running it against a real
  30-day inbox window). All 63 unit tests passed because they fed
  synthetic headers into the parser, not real MCP output.

### Added
- `extract_unsub_urls_from_body()` — fallback that scans plaintextBody
  for URLs containing unsub/opt-out/preferences/email-settings. Covers
  ~70% of newsletters without the header access. Trailing punctuation
  stripped, duplicates deduped.
- `resolve_unsub(thread)` — unified resolver. Priority order: header
  (if harness supplies it), body-scrape URL, Gmail UI fallback.
- New `source: "header" | "body_scrape" | "none"` field on every
  unsub log entry so the user knows which are authoritative (RFC
  2369) vs best-effort (scraped).
- New schema action: `manual_gmail_ui` — instructs user to click
  Gmail's native Unsubscribe button (Gmail has the header even when
  MCP doesn't).
- Report renderer splits https output by source (authoritative vs
  scraped) and adds a dedicated Gmail-UI-button section.
- 10 new tests in test_unsub_and_versioning.py.

### Live-test result
- Ran against 10 real senders from today's inbox. 9 got scraped URLs;
  1 fell back to Gmail UI. 73 tests pass.

---

## [0.1.7] — 2026-04-19

### Added
- `scripts/lib/prompt_version.py` — parser for `<!-- prompt_version: ... -->`
  comment headers in `prompts/*.md`. Stdlib only, pure functions.
- `prompt_versions` field on every draft log entry, populated from the
  current triage + draft prompt headers. Attributes drafts to specific
  prompt revisions so the monthly architect audit can say "edit rate
  rose starting at draft.md v0.3" instead of just "edit rate rose."
- Version headers added to `prompts/triage.md`, `prompts/draft.md`,
  `prompts/audit.md` — all at `0.1.0`, last_changed `2026-04-19`.
- `tests/test_unsub_and_versioning.py` — covers both new modules,
  including a CI-level test that fails if any future prompt is added
  without a version header.

---

## [0.1.6] — 2026-04-19

### Added
- `scripts/unsub.py` — batch unsubscribe helper. Parses RFC 2369
  `List-Unsubscribe` headers, then either (a) queues mailto-based
  unsubscribe drafts via `create_draft` (still human-reviewed before
  send), or (b) prints https: one-click URLs for batch-opening.
- `unsub` entry type added to `scripts/lib/schema.py` with 5 allowed
  actions (none / draft_queued / manual_click / manual_mailto / dry_run).
- `logs/unsubs.jsonl` — new append-only log for unsubscribe candidates.

### Safety
- Zero new capabilities. Uses only existing MCP surface (search_threads,
  get_thread, create_draft). Invariant I5 (no send) still structural.

---

## [0.1.5] — 2026-04-19

### Added
- `.gmail status` subcommand (`scripts/status.py`) — 7 health checks:
  symlink, rules.json validity, log integrity, module imports, I5
  no-send invariant, schema version parity, last triage age. Exits
  non-zero on any failure for CI integration.

### Fulfilled
- SKILL.md advertised `status` subcommand is now real.

---

## [0.1.4] — 2026-04-19

### Added
- `scripts/stats.py` — observability layer. Reads all JSONL logs,
  produces markdown report: triage volume, category breakdown, review
  decisions, phishing signal hit rates, log health (with rotation
  warnings at 5k/10k lines). `--json` mode for machine-readable output.
- `tests/test_stats_status.py` — smoke tests for stats + status CLIs.

---

## [0.1.3] — 2026-04-19

### Added
- `phishing.analyze()` wired into `triage.triage_one()`. Every thread
  now carries a `phishing_report` field in its draft log entry.
- Hard safety gate: `total_score >= 0.5` forces `status=flagged_for_human`
  regardless of classifier intent, with `flag_reason: "phishing_signals"`.

### Changed
- `schema.py` now accepts optional `phishing_report` in draft entries
  (backward-compat: older entries without the field still validate).

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
