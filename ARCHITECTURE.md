# .gmail — Architecture

A long-form design doc for the email-triage skill. Read this before changing any file in the tree.

---

## Tree structure — one question per directory

```
gmail/
├── SKILL.md          ← "what is this?"           (front door)
├── ARCHITECTURE.md   ← "how is it shaped?"       (this file)
├── SCHEMA.md         ← "what are the contracts?"
├── CHANGELOG.md      ← "what changed when?"
├── config/           ← "what rules does it follow?"  (slow-churn)
├── prompts/          ← "how does Claude think about this?" (medium-churn)
├── scripts/          ← "what code executes it?"           (medium-churn)
├── logs/             ← "what happened?"                   (fast-churn, append-only)
├── tests/            ← "what must remain true?"
└── install.sh        ← "how do I wire it up?"
```

Each directory answers exactly one question. Churn rates are isolated — rewriting a prompt must not ripple into logs or configs.

---

## The 7 Invariants

| 🟣 ID | 🟣 Invariant | 🟣 Guarantee | 🟣 Enforced by |
|---|---|---|---|
| I1 | Churn isolation | Configs/code/data/logs live in separate dirs; high-churn never touches low-churn | Tree shape |
| I2 | Append-only logs | No log entry is ever mutated or deleted in place | `log.append()` has no update path |
| I3 | Single source of truth | `rules.json` is the only place categories live | `schema.py` validation; no hardcoded category lists |
| I4 | Schema versioning | Every JSONL entry has a `schema_version` field | `schema.validate()` rejects entries without it |
| I5 | Structural no-send | Skill cannot send email; MCP exposes no send tool | Absence of the tool in capability surface |
| I6 | Idempotency on triage | Running `.gmail triage` twice on the same thread is a no-op | `triage.py` checks `drafts.jsonl` before draft create |
| I7 | Graceful degradation | MCP down → write `status: skipped` log entry, exit 0 | try/except in `gmail_client.py` + log.append |

---

## Data lifecycle

```
┌──────────────┐
│ Email arrives│
└──────┬───────┘
       │
       ▼
┌──────────────┐   .gmail triage        ┌────────────────────┐
│ Gmail inbox  │ ───────────────────►   │ logs/drafts.jsonl  │
│ (unread)     │   (create_draft)       │ status: pending    │
└──────────────┘                        └─────────┬──────────┘
                                                  │
                                                  │ .gmail review
                                                  ▼
                                        ┌────────────────────┐
                                        │ logs/sent.jsonl    │
                                        │ decision: approved │
                                        │         │ edited   │
                                        │         │ rejected │
                                        └─────────┬──────────┘
                                                  │
                                                  │ .gmail audit (monthly)
                                                  ▼
                                        ┌────────────────────┐
                                        │ logs/audits.jsonl  │
                                        │ findings +         │
                                        │ prompt diffs       │
                                        └─────────┬──────────┘
                                                  │
                                                  │ quarterly
                                                  ▼
                                        ┌────────────────────┐
                                        │ logs/archive/*.jsonl.gz │
                                        └────────────────────┘
```

---

## Failure modes

| 🟣 # | 🟣 Failure | 🟣 Blast radius | 🟣 Detection | 🟣 Recovery | 🟣 Severity |
|---|---|---|---|---|---|
| 1 | MCP server down | Triage skips run | `gmail_client` raises; log `skipped` | Retry on next cron tick | Low |
| 2 | `rules.json` malformed | Triage refuses to start | `schema.validate` on load | Fix JSON; re-run | Low |
| 3 | Hallucinated draft (fabricated quote) | Wrong reply in Gmail drafts (not sent) | Review step catches via quote-match | Reject draft; tighten prompt | Medium |
| 4 | Duplicate draft for same thread | Two drafts in Gmail | I6 check on `drafts.jsonl` | Idempotency prevents | Low |
| 5 | Log file corruption | Partial history loss | `log.read_all` skips malformed lines, warns | Restore from archive | High |
| 6 | Schema drift post-upgrade | Mixed v0.1 + v0.2 entries | `schema_version` field | Run `migrate.py` | Medium |
| 7 | Reviewer approves wrong draft | Bad email goes out from Gmail UI | Audit catches pattern | Tune prompts; retrain reviewer | Medium |
| 8 | Audit never runs | Accuracy drift goes unnoticed | `.gmail status` flags age of last audit | Run audit; set calendar reminder | Medium |

---

## Half-life calculation

Three orthogonal axes contribute to skill longevity:

- Tree structure (directory shape answers one question each): **99%** retained/year
- Plugin surface (SKILL.md frontmatter, MCP capability boundary): **98%** retained/year
- Unix contract (JSONL in, JSONL out, stdin/stdout composable): **97%** retained/year

Combined retention = 0.99 × 0.98 × 0.97 = **0.941** → expected 12-month survival probability **~94%**.

Any change that drops the combined score below 0.90 requires an explicit `ARCHITECTURE.md` amendment and a CHANGELOG entry, per `principle_future_proof_by_default` check #6.

---

## Why these boundaries

- **Configs vs code:** rules change monthly; code changes quarterly. Separating them means tuning categories doesn't risk code regressions.
- **Prompts vs code:** prompts are text; Python is code. Swapping the prompt file is a one-line diff — swapping classification logic is a PR.
- **Logs vs state:** logs are the state. No separate DB. JSONL is grep-able, human-readable, survives 50 years (per `principle_50_year_preservation`).
- **install.sh at root:** one visible on-ramp. Symlink pattern keeps source editable in `~/Desktop/CLAUDE CODE/gmail/` while `~/.claude/skills/gmail/` stays in sync automatically.
