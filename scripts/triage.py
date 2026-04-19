"""`.gmail triage` — Intern mode.

Pipeline:
    1. Load config/rules.json and validate it.
    2. Query Gmail for unread threads.
    3. For each thread NOT already in drafts.jsonl (invariant I6):
         a. Classify against rules (prompts/triage.md).
         b. If confidence >= category.min_confidence and action == 'draft',
            generate a draft (prompts/draft.md) and create via MCP.
         c. Append the decision to logs/drafts.jsonl.
    4. Gracefully degrade on MCP failure (invariant I7) — log 'skipped' and exit 0.

Stdlib only. Argparse CLI.

Note: this file is the ORCHESTRATION skeleton. The actual classify/draft calls
are made by Claude (the harness) invoking MCP tools and reading prompts/*.md.
This module's job is to enforce idempotency, validate, and log.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts.lib import log as loglib  # noqa: E402
from scripts.lib import schema as schemalib  # noqa: E402
from scripts.lib import dedupe as dedupelib  # noqa: E402
from scripts.lib import quote_verify as qvlib  # noqa: E402
from scripts.lib.gmail_client import GmailClient, GmailClientError  # noqa: E402


RULES_PATH = os.path.join(ROOT, "config", "rules.json")
DRAFTS_LOG = os.path.join(ROOT, "logs", "drafts.jsonl")


def load_rules(path: str = RULES_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    schemalib.validate_rules_file(doc)
    return doc


def already_drafted_ids(log_path: str = DRAFTS_LOG) -> set[str]:
    """Invariant I6 — enforce idempotency via prior log contents."""
    return {entry["thread_id"] for entry in loglib.read_all(log_path)}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def triage_one(
    thread: dict,
    rules: dict,
    rules_version: str,
    classify_fn,
    draft_fn,
    client: GmailClient,
) -> dict:
    """Run the full triage on one thread, return the log entry that will be appended.

    classify_fn and draft_fn are injected so the harness (Claude) can supply
    real LLM-backed implementations while tests pass in deterministic stubs.
    """
    classification = classify_fn(thread, rules)
    category_id = classification.get("category_id", "none")
    confidence = int(classification.get("confidence", 1))

    cat = next((c for c in rules["categories"] if c["id"] == category_id), None)

    entry: dict = {
        "schema_version": schemalib.CURRENT_SCHEMA_VERSION,
        "timestamp_iso": _now_iso(),
        "thread_id": thread["thread_id"],
        "thread_fingerprint": {
            "from": thread.get("from", "<missing>"),
            "subject": thread.get("subject", "<missing>"),
            "date_iso": thread.get("date_iso", "<missing>"),
        },
        "category_id": category_id,
        "rules_version": rules_version,
        "draft_preview": "",
        "confidence": max(1, min(5, confidence)),
        "status": "skipped",
    }

    if cat is None:
        return entry

    if confidence < cat["min_confidence"]:
        entry["status"] = "skipped"
        return entry

    if cat["action"] == "flag":
        entry["status"] = "flagged_for_human"
        return entry

    if cat["action"] == "label":
        # labeling is a side effect outside the draft pipeline;
        # the harness handles it. We log the intent only.
        entry["status"] = "skipped"
        return entry

    # action == 'draft'
    draft = draft_fn(thread, cat)

    # FIX #2 — verbatim quote enforcement (hallucination hardening).
    # If quoted_line does not appear in email body, draft is downgraded
    # (confidence capped to 1, warning prefixed, verification recorded).
    email_body = thread.get("body", "") or thread.get("snippet", "")
    draft = qvlib.enforce_or_downgrade(draft, email_body)
    qv = draft["quote_verification"]
    entry["quote_verified"] = qv["ok"]
    entry["quote_verification_reason"] = qv["reason"]

    body = draft.get("draft_body", "")
    entry["draft_preview"] = body[:200]
    try:
        client.create_draft(thread["thread_id"], body)
        entry["status"] = "pending_review"
    except (GmailClientError, NotImplementedError) as exc:
        # I7 graceful degradation: log skipped, keep going.
        print(f"[triage] create_draft failed for {thread['thread_id']}: {exc}", file=sys.stderr)
        entry["status"] = "skipped"

    return entry


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=".gmail triage", description="Triage unread Gmail.")
    parser.add_argument("--dry-run", action="store_true", help="Classify but do not create drafts.")
    parser.add_argument("--query", default="is:unread", help="Gmail search query (default: is:unread).")
    args = parser.parse_args(argv)

    rules = load_rules()
    rules_version = rules["schema_version"]
    seen = already_drafted_ids()
    client = GmailClient()

    try:
        threads = client.search_threads(args.query)
    except (GmailClientError, NotImplementedError) as exc:
        print(f"[triage] backend unavailable: {exc}", file=sys.stderr)
        return 0  # I7

    # classify_fn and draft_fn are expected to be injected by the harness.
    # In standalone CLI runs, we raise — this entry point is called via Claude.
    def _classify_stub(thread, rules):
        raise NotImplementedError(
            "triage_one requires classify_fn supplied by the harness. "
            "Run via `.gmail triage` (Claude Code), not standalone python."
        )

    def _draft_stub(thread, cat):
        raise NotImplementedError(
            "triage_one requires draft_fn supplied by the harness."
        )

    # FIX #1 — two-pass dedupe for supersedable alerts (system-alert).
    # Pass 1: build entries in memory without logging.
    # Pass 2: run dedupe, then flush to disk. Keeps log append-only while
    # still giving the human a clean triage report.
    pending: list[dict] = []
    for thread in threads:
        if thread["thread_id"] in seen:
            continue  # I6
        entry = triage_one(
            thread, rules, rules_version, _classify_stub, _draft_stub, client,
        )
        pending.append(entry)

    # Look up the dedupe window from the system-alert rule (default 60 min).
    sys_cat = next(
        (c for c in rules["categories"] if c["id"] == "system-alert"),
        None,
    )
    window = int((sys_cat or {}).get("dedupe_window_minutes", 60))
    dedupelib.dedupe_alerts(pending, window_minutes=window)

    for entry in pending:
        loglib.append(DRAFTS_LOG, entry, entry_type="draft")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
