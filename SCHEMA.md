# .gmail — Data Contracts

Every file the skill reads or writes has a schema. Every entry carries `schema_version`. Migrations live in `scripts/migrate.py`.

---

## `config/rules.json`

```json
{
  "schema_version": "0.1",
  "categories": [
    {
      "id": "string (kebab-case, unique)",
      "match": "string (human-readable classification hint for prompt)",
      "action": "draft | label | flag",
      "min_confidence": 1-5,
      "draft_template_hint": "string (optional)",
      "label": "string (Gmail label name, optional)"
    }
  ]
}
```

**Invariants:**
- `schema_version` required at root
- `id` must be unique within `categories`
- `action` in `{draft, label, flag}`
- `min_confidence` integer 1-5

---

## `logs/drafts.jsonl`

One JSON object per line. Append-only. No updates.

| 🟣 Field | 🟣 Type | 🟣 Required | 🟣 Notes |
|---|---|---|---|
| `schema_version` | string | yes | e.g. `"0.1"` |
| `timestamp_iso` | string | yes | ISO 8601 UTC |
| `thread_id` | string | yes | Gmail thread ID |
| `thread_fingerprint` | object | yes | `{from, subject, date_iso}` |
| `category_id` | string | yes | FK to `rules.json` |
| `rules_version` | string | yes | Value of `rules.json.schema_version` at triage time |
| `draft_preview` | string | yes | First 200 chars of draft body |
| `confidence` | int | yes | 1-5 |
| `status` | string | yes | `pending_review` \| `flagged_for_human` \| `skipped` |

---

## `logs/sent.jsonl`

Written by `.gmail review` after Danny acts on a draft.

| 🟣 Field | 🟣 Type | 🟣 Required | 🟣 Notes |
|---|---|---|---|
| `schema_version` | string | yes | |
| `timestamp_iso` | string | yes | |
| `thread_id` | string | yes | |
| `original_draft_hash` | string | yes | sha256 of draft body at time of creation |
| `final_text` | string | yes | Full body as sent (or last-edited before reject) |
| `edit_distance` | float | yes | 0.0-1.0 via `difflib.SequenceMatcher.ratio()` inverted (1.0 = identical, lower = more edits) |
| `decision` | string | yes | `approved` \| `edited` \| `rejected` |
| `reviewer` | string | yes | `"danny"` default |

Note: the name `sent.jsonl` reflects intent — the skill itself never sends. This log captures what the Senior decided about each draft.

---

## `logs/audits.jsonl`

Written monthly by `.gmail audit`.

| 🟣 Field | 🟣 Type | 🟣 Required | 🟣 Notes |
|---|---|---|---|
| `schema_version` | string | yes | |
| `timestamp_iso` | string | yes | |
| `period` | string | yes | e.g. `"2026-03"` |
| `sample_size` | int | yes | Count of drafts sampled |
| `findings` | object | yes | `{by_category: {id: {n, avg_edit_distance, reject_rate}}}` |
| `suggested_prompt_changes` | array | yes | List of `{category_id, proposal, rationale}` |

---

## Schema evolution

- `schema_version` is monotonic string — `"0.1"` → `"0.2"` → `"1.0"`.
- On bump, `scripts/migrate.py` gains a function `v0_1_to_v0_2(entry)` etc.
- Readers MUST tolerate older versions via the migration chain.
- CHANGELOG.md gets a row per bump with migration notes.
