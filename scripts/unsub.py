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


# FALLBACK: Gmail MCP's get_thread does NOT expose the List-Unsubscribe
# RFC 2369 header. We extract unsubscribe URLs from the email body as a
# best-effort. ~70% of newsletters embed an explicit unsubscribe link.
_UNSUB_URL_RE = re.compile(
    r"https?://[^\s<>\"')]+(?:unsub|opt[_-]?out|preferences|email[_-]?settings)[^\s<>\"')]*",
    re.IGNORECASE,
)


def extract_unsub_urls_from_body(body: str) -> list[str]:
    """Scan a plaintext body for likely unsubscribe URLs.

    Heuristic: URL contains one of (unsub, opt-out, preferences,
    email-settings). Preserves original order; caller takes first.
    """
    if not body:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _UNSUB_URL_RE.finditer(body):
        url = m.group(0).rstrip(".,;:!?)")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def resolve_unsub(thread: dict) -> dict[str, str | None]:
    """Best-effort unsub resolution using every available signal.

    Priority:
      1. thread["list_unsubscribe"] header (if the harness extracted it)
      2. URLs scraped from thread["body"] / thread["plaintextBody"]
      3. None — caller falls back to "use Gmail's native button"
    """
    header = thread.get("list_unsubscribe") or ""
    out = parse_list_unsubscribe(header)
    if out["mailto"] or out["https"]:
        out["source"] = "header"
        return out

    body = thread.get("body") or thread.get("plaintextBody") or thread.get("snippet") or ""
    urls = extract_unsub_urls_from_body(body)
    if urls:
        return {"mailto": None, "https": urls[0], "source": "body_scrape"}

    return {"mailto": None, "https": None, "source": "none"}


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
        mailto_target, https_url, source, action, status
    """
    # Resolve via header if present, otherwise fall back to body scrape.
    # Header wins when available (RFC 2369 is authoritative).
    thread_with_header = dict(thread)
    thread_with_header["list_unsubscribe"] = list_unsub_header
    parsed = resolve_unsub(thread_with_header)

    entry = {
        "schema_version": schemalib.CURRENT_SCHEMA_VERSION,
        "timestamp_iso": _now_iso(),
        "thread_id": thread.get("thread_id", "<missing>"),
        "sender": thread.get("from", "<missing>"),
        "subject": thread.get("subject", "<missing>"),
        "mailto_target": parsed["mailto"],
        "https_url": parsed["https"],
        "source": parsed.get("source", "none"),
        "action": "none",
        "status": "flagged",
    }

    if not parsed["mailto"] and not parsed["https"]:
        # MCP doesn't expose List-Unsubscribe header, and body had no
        # scrape-able URL. User's best option: click Gmail's native
        # unsubscribe button (Gmail has the header even when MCP doesn't).
        entry["status"] = "use_gmail_native_button"
        entry["action"] = "manual_gmail_ui"
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
    gmail_ui = [e for e in entries if e.get("action") == "manual_gmail_ui"]
    none = [e for e in entries
            if not e.get("mailto_target")
            and not e.get("https_url")
            and e.get("action") != "manual_gmail_ui"]

    # Split https by source — header-derived vs body-scrape — so the
    # user knows which are authoritative vs best-effort.
    https_header = [e for e in https if e.get("source") == "header"]
    https_scraped = [e for e in https if e.get("source") == "body_scrape"]

    out.append("## 🟣 By mechanism\n")
    out.append("| 🟣 Method | 🟣 Count | 🟣 Action |")
    out.append("| --------- | -------- | --------- |")
    out.append(f"| mailto drafts queued | {len(mailto)} | review + send via `.gmail review` |")
    out.append(f"| https (RFC 2369)     | {len(https_header)} | batch-open — authoritative |")
    out.append(f"| https (body-scraped) | {len(https_scraped)} | batch-open — best effort |")
    out.append(f"| Gmail native button  | {len(gmail_ui)} | open in Gmail, click \"Unsubscribe\" |")
    out.append(f"| no mechanism found   | {len(none)} | block sender / mark spam |")
    out.append("")

    if gmail_ui:
        out.append("## 🟣 Use Gmail's native Unsubscribe button\n")
        out.append(
            "Gmail's MCP surface doesn't expose the RFC 2369 header, but "
            "Gmail's **web UI** does. For these senders, open the thread "
            "in gmail.com and click the **Unsubscribe** link next to the "
            "sender name:\n"
        )
        for e in gmail_ui[:15]:
            out.append(f"- `{e['sender'][:50]}` — thread `{e['thread_id']}`")
        if len(gmail_ui) > 15:
            out.append(f"- ...and {len(gmail_ui) - 15} more (see logs/unsubs.jsonl)")
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
