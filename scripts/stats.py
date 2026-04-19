"""`.gmail stats` — Observability layer.

Reads logs/*.jsonl and reports trends. Read-only, stdlib only,
deterministic.

Output: markdown tier-list-style tables printed to stdout.

Subject area coverage:
    - Triage volume (drafts/day, per-category counts)
    - Review outcomes (approve/edit/reject rates, edit distance distribution)
    - Phishing signals (which checks fire most often, total_score distribution)
    - Log health (file sizes, line counts, oldest/newest entry)

Pipelines:
    `python3 -m scripts.stats --days 30`
    `python3 -m scripts.stats --days 7 --json`  → machine-readable
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts.lib import log as loglib  # noqa: E402


LOGS_DIR = os.path.join(ROOT, "logs")
DRAFTS_LOG = os.path.join(LOGS_DIR, "drafts.jsonl")
SENT_LOG = os.path.join(LOGS_DIR, "sent.jsonl")
AUDITS_LOG = os.path.join(LOGS_DIR, "audits.jsonl")


def _parse_iso(ts: str) -> dt.datetime | None:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return dt.datetime.fromisoformat(ts).astimezone(dt.timezone.utc)
    except (AttributeError, ValueError):
        return None


def _within(ts: str, since: dt.datetime) -> bool:
    d = _parse_iso(ts)
    return d is not None and d >= since


def collect_draft_stats(entries: list[dict], since: dt.datetime) -> dict:
    recent = [e for e in entries if _within(e.get("timestamp_iso", ""), since)]
    categories = Counter(e.get("category_id", "none") for e in recent)
    statuses = Counter(e.get("status", "unknown") for e in recent)
    # Drafts per day bucket
    per_day: dict[str, int] = defaultdict(int)
    for e in recent:
        d = _parse_iso(e.get("timestamp_iso", ""))
        if d:
            per_day[d.strftime("%Y-%m-%d")] += 1
    # Phishing
    ph_signals: Counter = Counter()
    ph_scores: list[float] = []
    suspicious = 0
    for e in recent:
        pr = e.get("phishing_report") or {}
        ph_scores.append(float(pr.get("total_score", 0.0)))
        if pr.get("is_suspicious"):
            suspicious += 1
        for s in pr.get("signals", []) or []:
            ph_signals[s.get("name", "?")] += 1
    avg_score = sum(ph_scores) / len(ph_scores) if ph_scores else 0.0
    # Quote-verify miss rate
    unverified = sum(1 for e in recent if e.get("quote_verified") is False)
    drafted = sum(1 for e in recent if e.get("status") == "pending_review")
    return {
        "total": len(recent),
        "categories": dict(categories),
        "statuses": dict(statuses),
        "per_day": dict(per_day),
        "phishing_signals": dict(ph_signals),
        "phishing_avg_score": round(avg_score, 3),
        "phishing_suspicious": suspicious,
        "quote_unverified": unverified,
        "drafts_created": drafted,
    }


def collect_sent_stats(entries: list[dict], since: dt.datetime) -> dict:
    recent = [e for e in entries if _within(e.get("timestamp_iso", ""), since)]
    decisions = Counter(e.get("decision", "unknown") for e in recent)
    eds = [float(e.get("edit_distance", 0.0)) for e in recent]
    avg_ed = sum(eds) / len(eds) if eds else 0.0
    return {
        "total": len(recent),
        "decisions": dict(decisions),
        "avg_edit_distance": round(avg_ed, 3),
    }


def log_health() -> dict:
    def _health(path: str) -> dict:
        if not os.path.exists(path):
            return {"exists": False}
        size = os.path.getsize(path)
        lines = sum(1 for _ in loglib.read_all(path))
        return {"exists": True, "bytes": size, "lines": lines}
    return {
        "drafts": _health(DRAFTS_LOG),
        "sent": _health(SENT_LOG),
        "audits": _health(AUDITS_LOG),
    }


def render_markdown(drafts: dict, sent: dict, health: dict, days: int) -> str:
    out = []
    out.append(f"# 📊 `.gmail` stats — last {days} days\n")
    out.append("> 🟢 good sign · 🔴 bad sign · 🟡 middling\n")

    # Volume table
    out.append("## 🟣 Volume\n")
    out.append("| 🟣 Metric | 🟣 Count |")
    out.append("| --------- | -------- |")
    out.append(f"| Threads triaged       | {drafts['total']} |")
    out.append(f"| Drafts created        | {drafts['drafts_created']} |")
    out.append(f"| Sent / reviewed       | {sent['total']} |")
    out.append(f"| Avg edit distance     | {sent['avg_edit_distance']} |")
    out.append(f"| Quote-verify misses   | {drafts['quote_unverified']} |")
    out.append(f"| Phishing-flagged      | {drafts['phishing_suspicious']} |")
    out.append("")

    # Categories
    out.append("## 🟣 Category breakdown\n")
    if drafts["categories"]:
        out.append("| 🟣 Category | 🟣 Count |")
        out.append("| ----------- | -------- |")
        for cat, n in sorted(drafts["categories"].items(), key=lambda kv: -kv[1]):
            out.append(f"| {cat:<20s} | {n} |")
    else:
        out.append("_(no triage data in window)_")
    out.append("")

    # Decisions
    out.append("## 🟣 Review decisions\n")
    if sent["decisions"]:
        out.append("| 🟣 Decision | 🟣 Count |")
        out.append("| ----------- | -------- |")
        for dec, n in sorted(sent["decisions"].items(), key=lambda kv: -kv[1]):
            out.append(f"| {dec:<20s} | {n} |")
    else:
        out.append("_(no reviews in window)_")
    out.append("")

    # Phishing signals
    out.append("## 🟣 Phishing signals fired\n")
    if drafts["phishing_signals"]:
        out.append(f"Avg score: **{drafts['phishing_avg_score']}** · Suspicious: **{drafts['phishing_suspicious']}**\n")
        out.append("| 🟣 Signal | 🟣 Count |")
        out.append("| --------- | -------- |")
        for sig, n in sorted(drafts["phishing_signals"].items(), key=lambda kv: -kv[1]):
            out.append(f"| {sig:<20s} | {n} |")
    else:
        out.append("_(no phishing signals recorded — probably pre-v0.1.3 logs or no triage yet)_")
    out.append("")

    # Log health
    out.append("## 🟣 Log health\n")
    out.append("| 🟣 Log | 🟣 Lines | 🟣 Bytes | 🟣 Rotation? |")
    out.append("| ------ | -------- | -------- | ------------ |")
    for name, h in health.items():
        if not h.get("exists"):
            out.append(f"| {name:<6s} | _(missing)_ | _(missing)_ | n/a |")
            continue
        lines = h["lines"]
        rotate = "🔴 rotate now" if lines >= 10000 else ("🟡 nearing" if lines >= 5000 else "🟢 fine")
        out.append(f"| {name:<6s} | {lines} | {h['bytes']} | {rotate} |")
    out.append("")

    return "\n".join(out)


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=".gmail stats", description="Observability over .gmail logs.")
    p.add_argument("--days", type=int, default=30, help="Window in days (default 30).")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of markdown.")
    args = p.parse_args(argv)

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)

    drafts = collect_draft_stats(list(loglib.read_all(DRAFTS_LOG)), since)
    sent = collect_sent_stats(list(loglib.read_all(SENT_LOG)), since)
    health = log_health()

    if args.json:
        print(json.dumps({"drafts": drafts, "sent": sent, "health": health, "days": args.days}, indent=2))
    else:
        print(render_markdown(drafts, sent, health, args.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
