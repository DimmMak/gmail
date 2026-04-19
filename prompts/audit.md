<!--
prompt_version: "0.1.0"
last_changed: "2026-04-19"
-->

# Audit Prompt — Architect Mode

Monthly review. Not about individual emails — about **the prompts themselves**. Does the Intern classify correctly? Do the drafts survive Senior review with minimal edits?

## Inputs

- `logs/drafts.jsonl` — last 30 days.
- `logs/sent.jsonl` — last 30 days.
- `logs/audits.jsonl` — prior audit for trend comparison.

## Method

1. **Stratify** drafts by `category_id`.
2. **Sample 10%** per category (minimum 3, cap at 20).
3. For each sampled draft, join to its `sent.jsonl` entry via `thread_id`.
4. **Compute metrics** per category:
   - `n` — sample count
   - `avg_edit_distance` — mean of `edit_distance` field (1.0 = untouched, lower = more edits)
   - `reject_rate` — proportion of `decision == "rejected"`
   - `approve_rate` — proportion of `decision == "approved"` (no edits)
5. **Flag categories** where `avg_edit_distance < 0.5` — draft required substantial rewrite.
6. **Propose prompt changes** for each flagged category. Each proposal:
   - Cites 2-3 specific sampled threads as evidence.
   - Suggests a concrete edit to `prompts/draft.md` or the category's `draft_template_hint`.
   - Explains the mechanism — why the change should reduce edit distance.

## Output — JSON matching `logs/audits.jsonl` schema

```json
{
  "schema_version": "0.1",
  "timestamp_iso": "<now>",
  "period": "YYYY-MM",
  "sample_size": 0,
  "findings": {
    "by_category": {
      "recruiter": {"n": 0, "avg_edit_distance": 1.0, "reject_rate": 0.0}
    }
  },
  "suggested_prompt_changes": [
    {
      "category_id": "recruiter",
      "proposal": "<concrete diff>",
      "rationale": "<mechanism — why this reduces edits>"
    }
  ]
}
```

## Hard rule — human-in-loop

The audit **proposes**. It does not apply. Danny reads the audit, picks which proposals to accept, and hand-edits `prompts/draft.md` or `config/rules.json`. Auto-prompt-rewrite is explicitly listed in `SKILL.md` under `cannot`.
