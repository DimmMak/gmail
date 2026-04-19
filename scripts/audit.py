"""`.gmail audit` — Architect mode.

Monthly accuracy review.

Pipeline:
    1. Load last 30 days of sent.jsonl entries.
    2. Join with drafts.jsonl by thread_id to recover category.
    3. Stratified 10% sample per category (min 3, cap 20).
    4. Compute per-category metrics: n, avg_edit_distance, reject_rate, approve_rate.
    5. Flag categories with avg_edit_distance < 0.5 (substantial rewrite required).
    6. Write findings to logs/audits.jsonl.
    7. Print summary table.

Actual prompt-change proposals are produced by Claude at runtime using
prompts/audit.md. This orchestrator computes metrics; it does not propose.

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import sys
from collections import defaultdict

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts.lib import log as loglib  # noqa: E402
from scripts.lib import schema as schemalib  # noqa: E402


DRAFTS_LOG = os.path.join(ROOT, "logs", "drafts.jsonl")
SENT_LOG = os.path.join(ROOT, "logs", "sent.jsonl")
AUDITS_LOG = os.path.join(ROOT, "logs", "audits.jsonl")

FLAG_THRESHOLD = 0.5


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _parse_iso(s: str) -> dt.datetime:
    # tolerate "Z" suffix; otherwise expect fromisoformat-compatible
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return dt.datetime.fromisoformat(s)


def _period_tag(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def load_recent_sent(days: int = 30) -> list[dict]:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    out = []
    for e in loglib.read_all(SENT_LOG):
        try:
            if _parse_iso(e["timestamp_iso"]) >= cutoff:
                out.append(e)
        except Exception:
            continue
    return out


def category_index() -> dict[str, str]:
    """Map thread_id -> category_id from drafts.jsonl."""
    return {e["thread_id"]: e["category_id"] for e in loglib.read_all(DRAFTS_LOG)}


def stratified_sample(
    sent_entries: list[dict],
    cat_by_thread: dict[str, str],
    pct: float = 0.10,
    min_n: int = 3,
    cap: int = 20,
) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for e in sent_entries:
        cat = cat_by_thread.get(e["thread_id"], "unknown")
        buckets[cat].append(e)
    sampled: dict[str, list[dict]] = {}
    for cat, items in buckets.items():
        n = max(min_n, min(cap, math.ceil(len(items) * pct)))
        sampled[cat] = items[:n]  # deterministic: take the first N (newest if sorted)
    return sampled


def compute_findings(sampled: dict[str, list[dict]]) -> dict:
    by_cat = {}
    for cat, items in sampled.items():
        if not items:
            continue
        n = len(items)
        avg_ed = sum(float(e.get("edit_distance", 1.0)) for e in items) / n
        reject = sum(1 for e in items if e.get("decision") == "rejected") / n
        approve = sum(1 for e in items if e.get("decision") == "approved") / n
        by_cat[cat] = {
            "n": n,
            "avg_edit_distance": round(avg_ed, 4),
            "reject_rate": round(reject, 4),
            "approve_rate": round(approve, 4),
            "flagged": avg_ed < FLAG_THRESHOLD,
        }
    return {"by_category": by_cat}


def print_summary(findings: dict) -> None:
    print("\n=== .gmail audit summary ===")
    print(f"{'category':<24} {'n':>4} {'avg_ed':>8} {'approve':>8} {'reject':>7} {'flag':>5}")
    print("-" * 60)
    for cat, m in findings["by_category"].items():
        flag = "YES" if m["flagged"] else ""
        print(
            f"{cat:<24} {m['n']:>4} {m['avg_edit_distance']:>8.3f} "
            f"{m['approve_rate']:>8.2%} {m['reject_rate']:>7.2%} {flag:>5}"
        )
    print()


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=".gmail audit", description="Monthly accuracy audit.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--pct", type=float, default=0.10)
    parser.add_argument("--dry-run", action="store_true", help="Do not append to audits.jsonl.")
    args = parser.parse_args(argv)

    sent_entries = load_recent_sent(args.days)
    if not sent_entries:
        print("No sent-log entries in window. Nothing to audit.")
        return 0

    cat_by_thread = category_index()
    sampled = stratified_sample(sent_entries, cat_by_thread, pct=args.pct)
    findings = compute_findings(sampled)

    entry = {
        "schema_version": schemalib.CURRENT_SCHEMA_VERSION,
        "timestamp_iso": _now_iso(),
        "period": _period_tag(),
        "sample_size": sum(m["n"] for m in findings["by_category"].values()),
        "findings": findings,
        "suggested_prompt_changes": [],  # filled in by Claude per prompts/audit.md
    }

    print_summary(findings)

    if not args.dry_run:
        loglib.append(AUDITS_LOG, entry, entry_type="audit")
        print(f"Audit appended to {AUDITS_LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
