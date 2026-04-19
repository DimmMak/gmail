"""Dedupe logic for system-alert and similar superseding-alert flows.

Problem this solves (GAP 3 from v0.1 stress test):
    GitHub/CI sends failure emails, then success emails for later runs.
    Without dedupe, the human sees stale failures after the fix already
    landed. Dedupe collapses a cluster of alerts for the same resource
    into "most recent wins" within a time window.

Scope: pure functions, stdlib only. Deterministic. Testable.

Design:
    Two alerts dedupe together when all of:
      - Same category_id (e.g., 'system-alert')
      - Same resource_key (derived from sender + subject-stem)
      - Within dedupe_window_minutes of each other

    Within a cluster, the MOST RECENT alert wins — even if it's a
    success that supersedes an earlier failure.

    We do NOT mutate log entries. We produce a filtered VIEW over the
    incoming triage batch, annotating superseded entries so they appear
    in the log as status='superseded' (new allowed status) rather than
    polluting the flagged_for_human queue.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable


_SUBJECT_STEM_STRIP = re.compile(
    r"^(re:|fwd:|\[.*?\]|⚠️|✅|❌|🚨)\s*",
    re.IGNORECASE,
)

# Status verbs at the head of system-alert subjects. Stripped so that a
# "Run failed: X" and a later "Run succeeded: X" collapse together — that's
# the whole point: the newer success should SUPERSEDE the older failure.
# Ordered by specificity (multi-word first).
_STATUS_VERBS = re.compile(
    r"^(run\s+(?:failed|succeeded|passed|cancelled|canceled|timed\s+out)"
    r"|build\s+(?:failed|succeeded|passed|broken|fixed)"
    r"|deployment\s+(?:failed|succeeded|completed|rolled\s+back)"
    r"|workflow\s+(?:failed|succeeded|completed)"
    r"|status:\s*(?:failed|success|passed|error|ok)"
    r")\s*:?\s*",
    re.IGNORECASE,
)


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating trailing Z."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts).astimezone(timezone.utc)


def resource_key(thread_fingerprint: dict) -> str:
    """Derive a stable key for what this alert is ABOUT.

    Example:
        "notifications@github.com" + "[DimmMak/DimmMak.github.io] Run failed: Build and Deploy - main (abc123)"
        → "notifications@github.com::dimmmak/dimmmak.github.io run failed: build and deploy - main"

    The commit hash / run ID at the end is stripped so failures + successes
    on the same workflow collapse together.
    """
    sender = (thread_fingerprint.get("from") or "").lower()
    subject = thread_fingerprint.get("subject") or ""
    # Strip leading tags/emoji prefixes.
    stem = _SUBJECT_STEM_STRIP.sub("", subject).strip()
    # Strip leading status verbs so failure/success on the same resource merge.
    stem = _STATUS_VERBS.sub("", stem).strip()
    # Strip trailing parenthesized run IDs / hashes.
    stem = re.sub(r"\s*\([0-9a-f]{6,}\)\s*$", "", stem, flags=re.IGNORECASE)
    # Strip trailing run numbers like " #1234".
    stem = re.sub(r"\s*#\d+\s*$", "", stem)
    # Collapse whitespace, lowercase.
    stem = " ".join(stem.lower().split())
    return f"{sender}::{stem}"


def dedupe_alerts(
    entries: list[dict],
    window_minutes: int = 60,
) -> list[dict]:
    """Return entries with superseded ones marked status='superseded'.

    Input: list of draft-log-shaped entries (must have timestamp_iso,
           thread_fingerprint, category_id).
    Output: SAME list, same order, with superseded entries' status
            field mutated to 'superseded' and 'superseded_by' field
            added pointing to the winning thread_id.

    Only entries where category_id is 'system-alert' (or any category
    with dedupe_window_minutes set — resolved by caller) are eligible.
    Non-eligible entries pass through untouched.
    """
    window = timedelta(minutes=window_minutes)

    # Group eligible entries by resource_key.
    groups: dict[str, list[tuple[int, dict, datetime]]] = {}
    for idx, e in enumerate(entries):
        if e.get("category_id") != "system-alert":
            continue
        try:
            ts = _parse_iso(e["timestamp_iso"])
        except (KeyError, ValueError):
            continue
        key = resource_key(e.get("thread_fingerprint") or {})
        groups.setdefault(key, []).append((idx, e, ts))

    # Within each group, find the winner (most recent) and mark the rest.
    for key, items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda t: t[2])  # ascending by ts
        winner_idx, winner_entry, winner_ts = items[-1]
        for idx, entry, ts in items[:-1]:
            if winner_ts - ts <= window:
                entry["status"] = "superseded"
                entry["superseded_by"] = winner_entry.get("thread_id", "<unknown>")
                entry["superseded_reason"] = (
                    f"later alert on same resource key ({key}) arrived "
                    f"within {window_minutes}min window"
                )

    return entries


def filter_active(entries: Iterable[dict]) -> list[dict]:
    """Return only entries whose status is NOT 'superseded'.

    Convenience for the triage reporter.
    """
    return [e for e in entries if e.get("status") != "superseded"]
