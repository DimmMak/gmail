# Changelog — .gmail

All notable changes to this skill are documented here. Format loosely follows Keep-a-Changelog. Dates are ISO 8601.

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
