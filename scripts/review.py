"""`.gmail review` — Senior mode.

Walks `logs/drafts.jsonl` entries with status == 'pending_review', one at a time.
For each: show the email snippet + draft + confidence, ask for
approve / edit / reject via input(), write result to `logs/sent.jsonl`.

The skill does NOT send. Danny hits send in Gmail after approving. This log
captures what the Senior decided — so the Architect audit can grade accuracy.

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import os
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts.lib import log as loglib  # noqa: E402
from scripts.lib import schema as schemalib  # noqa: E402


DRAFTS_LOG = os.path.join(ROOT, "logs", "drafts.jsonl")
SENT_LOG = os.path.join(ROOT, "logs", "sent.jsonl")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def edit_distance_ratio(a: str, b: str) -> float:
    """Return difflib.SequenceMatcher.ratio() — 1.0 = identical, 0.0 = totally different."""
    return difflib.SequenceMatcher(a=a or "", b=b or "").ratio()


def already_reviewed_ids(log_path: str = SENT_LOG) -> set[str]:
    return {e["thread_id"] for e in loglib.read_all(log_path)}


def pending_drafts() -> list[dict]:
    seen = already_reviewed_ids()
    return [
        e for e in loglib.read_all(DRAFTS_LOG)
        if e.get("status") == "pending_review" and e["thread_id"] not in seen
    ]


def _prompt_decision(draft_preview: str) -> tuple[str, str]:
    """Return (decision, final_text).

    decision in {approved, edited, rejected}.
    """
    print("\n--- draft preview ---")
    print(draft_preview)
    print("--- end preview ---\n")
    choice = input("decision [a]pprove / [e]dit / [r]eject / [s]kip: ").strip().lower()
    if choice.startswith("a"):
        return "approved", draft_preview
    if choice.startswith("r"):
        return "rejected", draft_preview
    if choice.startswith("e"):
        print("Paste final body. End with a single '.' on its own line:")
        lines: list[str] = []
        while True:
            line = input()
            if line.strip() == ".":
                break
            lines.append(line)
        return "edited", "\n".join(lines)
    return "skip", draft_preview


def review_one(draft_entry: dict, reviewer: str = "danny") -> dict | None:
    """Interactively review one draft. Return the sent.jsonl entry, or None if skipped."""
    print("\n=====================================")
    fp = draft_entry["thread_fingerprint"]
    print(f"thread_id:  {draft_entry['thread_id']}")
    print(f"from:       {fp['from']}")
    print(f"subject:    {fp['subject']}")
    print(f"category:   {draft_entry['category_id']}  (confidence {draft_entry['confidence']})")
    decision, final_text = _prompt_decision(draft_entry.get("draft_preview", ""))
    if decision == "skip":
        return None

    original = draft_entry.get("draft_preview", "")
    entry = {
        "schema_version": schemalib.CURRENT_SCHEMA_VERSION,
        "timestamp_iso": _now_iso(),
        "thread_id": draft_entry["thread_id"],
        "original_draft_hash": _sha256(original),
        "final_text": final_text,
        "edit_distance": round(edit_distance_ratio(original, final_text), 4),
        "decision": decision,
        "reviewer": reviewer,
    }
    return entry


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=".gmail review", description="Review pending drafts.")
    parser.add_argument("--reviewer", default="danny")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N reviews (0 = no limit).")
    args = parser.parse_args(argv)

    pending = pending_drafts()
    if not pending:
        print("No pending drafts. Queue empty.")
        return 0

    print(f"{len(pending)} pending drafts.")
    done = 0
    for d in pending:
        if args.limit and done >= args.limit:
            break
        entry = review_one(d, reviewer=args.reviewer)
        if entry is None:
            continue
        loglib.append(SENT_LOG, entry, entry_type="sent")
        done += 1

    print(f"\nReviewed {done}. Remaining pending: {len(pending) - done}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
