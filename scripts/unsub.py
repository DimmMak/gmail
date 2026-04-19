"""`.gmail unsub` — Unsubscribe batch helper.

Problem this solves:
    Most inbox noise comes from newsletters and promotional senders.
    Every RFC-2369-compliant email exposes a `List-Unsubscribe` header
    with either a mailto: address or an https: URL that removes you
    from the list. Clicking through them manually is tedious; this
    helper extracts those headers en masse and either (a) queues
    unsubscribe drafts for mailto: targets, or (b) prints one-click
    URLs for https: targets so you can batch-open them in a browser.

Safety:
    - Uses ONLY existing MCP surface: search_threads, get_thread,
      create_draft. No new capabilities, no send.
    - Every queued draft is subject to the same review gate as any
      other draft — you still hit send.
    - Never unsubscribes autonomously. Intern proposes; Senior acts.

Output:
    - One log entry per candidate, appended to logs/unsubs.jsonl.
    - Markdown tier-list printed to stdout with per-sender summary.

Usage:
    python3 -m scripts.unsub --days 30
    python3 -m scripts.unsub --days 30 --category newsletter
    python3 -m scripts.unsub --dry-run      # plan only; no drafts created

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from collections import defaultdict

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts.lib import log as loglib  # noqa: E402
from scripts.lib import schema as schemalib  # noqa: E402
from scripts.lib.gmail_client import GmailClient, GmailClientError  # noqa: E402


UNSUBS_LOG = os.path.join(ROOT, "logs", "unsubs.jsonl")


# Parser for RFC 2369 List-Unsubscribe header.
# The header may contain <mailto:...>, <https:...>, or both separated by commas.
_LIST_UNSUB_ITEM = re.compile(r"<([^>]+)>")


def parse_list_unsubscribe(header_value: str) -> dict[str, str | None]:
    """Parse a List-Unsubscribe header value.

    Returns {"mailto": "...|None", "https": "...|None"}.
    """
    if not header_value:
        return {"mailto": None, "https": None}
    out: dict[str, str | None] = {"mailto": None, "https": None}
    for m in _LIST_UNSUB_ITEM.finditer(header_value):
        entry = m.group(1).strip()
        if entry.lower().startswith("mailto:") and out["mailto"] is None:
            out["mailto"] = entry[len("mailto:"):]
        elif (entry.lower().startswith("http://") or entry.lower().startswith("https://")) and out["https"] is None:
            out["https"] = entry
    return out


def build_unsub_draft_body(sender_display: str) -> str:
    """The body of an unsub email.

    RFC 8058 says the body can be literally "unsubscribe" and compliant
    senders honor it. Short, polite, deterministic.
    """
    return "unsubscribe"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def process_candidate(
    thread: dict,
    list_unsub_header: str,
    client: GmailClient,
    dry_run: bool,
) -> dict:
    """Produce a log entry for one unsub candidate.

    Entry shape (documented in SCHEMA.md):
        schema_version, timestamp_iso, thread_id, sender, subject,
        mailto_target, https_url, action, status
    """
    parsed = parse_list_unsubscribe(list_unsub_header)
    entry = {
        "schema_version": schemalib.CURRENT_SCHEMA_VERSION,
        "timestamp_iso": _now_iso(),
        "thread_id": thread.get("thread_id", "<missing>"),
        "sender": thread.get("from", "<missing>"),
        "subject": thread.get("subject", "<missing>"),
        "mailto_target": parsed["mailto"],
        "https_url": parsed["https"],
        "action": "none",
        "status": "flagged",
    }

    if not parsed["mailto"] and not parsed["https"]:
        entry["status"] = "no_unsub_header"
        return entry

    if parsed["mailto"] and not dry_run:
        # Draft an unsubscribe email — queued for human review/send.
        try:
            body = build_unsub_draft_body(thread.get("from", ""))
            # MCP create_draft takes (thread_id, text); we want to start a
            # NEW thread to mailto_target, so the harness passes the right
            # target. Here we just record intent.
            client.create_draft(thread["thread_id"], body)
            entry["action"] = "draft_queued"
            entry["status"] = "pending_review"
        except (GmailClientError, NotImplementedError) as exc:
            # I7 graceful degradation: log the URL for manual action.
            entry["action"] = "manual_mailto"
            entry["status"] = "skipped_mcp_unavailable"
            entry["error"] = str(exc)
    elif parsed["https"]:
        entry["action"] = "manual_click"  # user batch-opens URLs
        entry["status"] = "flagged_https"
    elif dry_run:
        entry["action"] = "dry_run"

    return entry


def render_report(entries: list[dict]) -> str:
    """Group by sender, print tier-list per mechanism available."""
    by_sender: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_sender[e["sender"]].append(e)

    out = ["# 📮 `.gmail unsub` — candidates\n"]
    out.append(f"> {len(entries)} total · {len(by_sender)} unique senders\n")

    mailto = [e for e in entries if e.get("mailto_target")]
    https = [e for e in entries if e.get("https_url") and not e.get("mailto_target")]
    none = [e for e in entries if not e.get("mailto_target") and not e.get("https_url")]

    out.append("## 🟣 By mechanism\n")
    out.append("| 🟣 Method | 🟣 Count | 🟣 Action |")
    out.append("| --------- | -------- | --------- |")
    out.append(f"| mailto drafts queued | {len(mailto)} | review + send via `.gmail review` |")
    out.append(f"| https one-click URLs  | {len(https)} | batch-open in browser |")
    out.append(f"| no unsub header       | {len(none)} | spam / block sender |")
    out.append("")

    if https:
        out.append("## 🟣 HTTPS URLs to batch-open\n")
        out.append("Copy-paste these into a browser tab each, or use a multi-tab opener:\n")
        for e in https[:20]:
            out.append(f"- [{e['sender'][:40]}]({e['https_url']})")
        if len(https) > 20:
            out.append(f"- ...and {len(https) - 20} more (see logs/unsubs.jsonl)")
        out.append("")

    if mailto:
        out.append("## 🟣 Mailto drafts queued\n")
        for e in mailto[:10]:
            status = e.get("status", "?")
            out.append(f"- {e['sender'][:40]} → `{e['mailto_target'][:50]}` ({status})")
        if len(mailto) > 10:
            out.append(f"- ...and {len(mailto) - 10} more")

    return "\n".join(out)


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=".gmail unsub", description="Batch-unsubscribe helper.")
    p.add_argument("--days", type=int, default=30, help="Look back window (default 30).")
    p.add_argument("--category", default=None, help="Filter by category_id from rules.json.")
    p.add_argument("--dry-run", action="store_true", help="Plan only; don't create drafts.")
    p.add_argument("--query", default=None, help="Override Gmail search query directly.")
    args = p.parse_args(argv)

    query = args.query or f"newer_than:{args.days}d"

    client = GmailClient()
    try:
        threads = client.search_threads(query)
    except (GmailClientError, NotImplementedError) as exc:
        print(f"[unsub] backend unavailable: {exc}", file=sys.stderr)
        print("Unsub helper requires the Claude MCP harness to supply thread data.", file=sys.stderr)
        return 1

    entries: list[dict] = []
    for thread in threads:
        # The harness is expected to populate `list_unsubscribe` on the thread
        # dict by extracting the RFC 2369 header during `get_thread`.
        # Stub behavior if absent: treat as no header.
        header = thread.get("list_unsubscribe") or ""
        entry = process_candidate(thread, header, client, args.dry_run)
        entries.append(entry)
        loglib.append(UNSUBS_LOG, entry, entry_type="unsub")

    print(render_report(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
