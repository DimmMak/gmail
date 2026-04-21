# NON_GOALS — .gmail

**Explicit out-of-scope list.** This skill refuses these and redirects elsewhere.

---

## Hard refusals (never attempt)

| 🟣 # | 🟣 Refused | 🟣 Reason | 🟣 Redirect |
|---|---|---|---|
| 1 | **Sending email** | Structural invariant I5 — MCP surface has no `send` tool | Human uses Gmail UI manually (the final mile is always human) |
| 2 | **Deleting email** | Structural — MCP has no delete tool | Gmail UI |
| 3 | **Modifying received emails** | Destroys audit trail | Not possible, by design |
| 4 | **Reaching non-Gmail inboxes** | Scope boundary; this is a Gmail-specific skill | Use a different inbox-specific skill when built |

---

## Soft refusals (decline + redirect)

| 🟣 Pattern | 🟣 Reason | 🟣 Redirect |
|---|---|---|
| **LinkedIn outreach / DMs** | LinkedIn is not Gmail; different platform entirely | Use a future `linkedin-outreach` skill (or handle manually) |
| **Prediction grading / accuracy tracking** | Email triage ≠ prediction scoring | `accuracy-tracker` |
| **Stock analysis / investment verdicts** | Email is a communication channel, not an analysis tool | `royal-rumble` or `.chief` |
| **Howard Marks-style memo writing** | Long-form prose is a different discipline | `.journalist` |
| **Cold outreach / marketing campaigns** | This skill triages RECEIVED email, not outbound broadcast | Use a dedicated outreach tool |
| **Spam filtering tuning** | Gmail's built-in spam filter handles this | Gmail's native settings |
| **Auto-retraining prompts** | Human-in-loop required (Architect role) | Monthly audit + manual prompt tweaks |

---

## Structural boundaries (permanent — never override)

1. **MCP-enforced:** MCP surface exposes only read + draft + label tools. Absence of `send` is structural, not policy.
2. **Human-approval gate:** Every draft must be reviewed by a human (Senior role) before it leaves Gmail drafts folder.
3. **Append-only logs:** All JSONL logs (drafts, sent, audits) are append-only. Never mutate past entries.
4. **No external orchestration:** Skill does not call other skills. Leaf in the fleet tree.

---

## Invariants enforced (I1-I7 — see ARCHITECTURE.md)

- **I1 — Churn isolation**
- **I2 — Append-only logs**
- **I3 — Single source of truth** (rules.json)
- **I4 — Schema versioning**
- **I5 — Structural no-send** (most critical)
- **I6 — Idempotency on triage**
- **I7 — Graceful degradation**

Any change that violates an invariant requires CHANGELOG + ARCHITECTURE.md amendment.

---

## 🧬 One sentence

> **.gmail is scoped to triage + draft + label of Gmail inbox threads only — it refuses sending (structural via MCP), non-Gmail platforms (LinkedIn etc.), non-email tasks (stock analysis, accuracy tracking, memo writing), and any violation of the 7 invariants in ARCHITECTURE.md — all refusals redirect to the correct fleet skill or explicitly mark the request as out-of-fleet-scope.**
