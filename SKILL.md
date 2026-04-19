---
name: gmail
domain: general
version: 0.1
description: Email triage with Intern/Senior/Architect review pattern
capabilities:
  reads:
    - gmail-mcp (search_threads, get_thread, list_drafts, list_labels)
    - config/rules.json
    - logs/*.jsonl
  writes:
    - gmail-mcp (create_draft, create_label)
    - logs/*.jsonl (append only)
  calls: []
  cannot:
    - send email (MCP has no send tool — structural guarantee)
    - delete email
    - modify received emails
    - reach non-Gmail inboxes
    - auto-retrain prompts (human-in-loop only)
unix_contract:
  data_format: "JSONL"
  schema_version: "0.1"
  stdin_support: true
  stdout_format: "JSONL matching SCHEMA.md"
  composable_with:
    - linkedin-outreach
    - accuracy-tracker
    - royal-rumble
---

# .gmail — Email Triage Skill

**Pattern:** Intern / Senior / Architect.

- **Intern (Claude):** classifies incoming, drafts replies. Never sends.
- **Senior (Danny):** reviews drafts, edits, hits send in Gmail UI. The final mile is always human.
- **Architect (monthly):** samples 10% of drafts, grades accuracy, proposes prompt tweaks.

The MCP surface has no `send` tool. That is a **structural guarantee** (invariant I5), not a policy. Even a buggy agent cannot exfiltrate email.

---

## Subcommands

| 🟣 Command | 🟣 Role | 🟣 What it does | 🟣 Writes |
|---|---|---|---|
| `.gmail triage` | Intern | Pulls unread, classifies against `rules.json`, drafts replies | `logs/drafts.jsonl` + Gmail drafts |
| `.gmail review` | Senior | Walks pending drafts one-by-one: approve / edit / reject | `logs/sent.jsonl` |
| `.gmail audit` | Architect | Stratified 10% sample of last 30 days, computes edit_distance | `logs/audits.jsonl` |
| `.gmail search <query>` | Lookup | Raw MCP search passthrough | — |
| `.gmail status` | Health | Counts pending, last triage/review/audit timestamps | — |

---

## Daily loop

| 🟣 Slot | 🟣 Action | 🟣 Duration |
|---|---|---|
| Morning | `.gmail triage` → drafts land in Gmail | ~2 min |
| Afternoon | `.gmail review` → approve/edit/reject in terminal, send in Gmail | ~10 min |
| Monthly | `.gmail audit` → accuracy report, prompt diffs proposed | ~15 min |

---

## Non-Goals

The skill **refuses** to:

- Send email. Ever. (MCP has no send tool.)
- Delete email.
- Modify received emails.
- Reach non-Gmail inboxes (Outlook, Yahoo, etc.).
- Auto-retrain prompts — all prompt changes are human-in-loop.
- Run without `rules.json` — fail loud.
- Mutate logs in place — logs are append-only.
- Silently drop threads — every decision is logged.

---

## Invariants

See `ARCHITECTURE.md` for full treatment. Summary:

- **I1** churn isolation — configs vs code vs data in separate dirs
- **I2** append-only logs
- **I3** single source of truth — `rules.json` is the only classification source
- **I4** schema versioning — every JSONL entry carries `schema_version`
- **I5** structural no-send — MCP lacks the tool
- **I6** idempotency — re-running triage on same thread_id is a no-op
- **I7** graceful degradation — MCP down → stub writes a `skipped` log entry

---

## References

- `principle_tree_structure_always` — why the dirs are shaped this way
- `principle_future_proof_by_default` — the 12-month survival test applied to every decision here
- `principle_safe_implies` — the 7-checklist fires on any change to this skill
