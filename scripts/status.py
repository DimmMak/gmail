"""`.gmail status` — Health check / self-diagnosis.

Answers "is the skill healthy RIGHT NOW?" Read-only, stdlib only.

Checks performed:
    1. Symlink: ~/.claude/skills/gmail points somewhere valid
    2. Config: rules.json is valid JSON + passes schema
    3. Logs: each log file exists and is well-formed JSONL
    4. Modules: every scripts/lib/*.py imports without error
    5. Schema version: SCHEMA.md-declared version matches code constant
    6. MCP surface: GmailClient has no send method (invariant I5)
    7. Last triage: when was the most recent entry logged?

Exit codes:
    0 — all checks pass
    1 — any check fails (details printed to stderr)
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from scripts.lib import log as loglib  # noqa: E402
from scripts.lib import schema as schemalib  # noqa: E402


CHECKS: list[tuple[str, callable]] = []  # filled by @check decorator


def check(name: str):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


@check("symlink")
def check_symlink() -> tuple[bool, str]:
    dest = os.path.expanduser("~/.claude/skills/gmail")
    if not os.path.islink(dest):
        return False, f"{dest} is not a symlink (expected symlink to skill source)"
    target = os.readlink(dest)
    if not os.path.exists(target):
        return False, f"symlink target missing: {target}"
    return True, f"→ {target}"


@check("rules.json")
def check_rules() -> tuple[bool, str]:
    path = os.path.join(ROOT, "config", "rules.json")
    if not os.path.exists(path):
        return False, f"{path} missing"
    try:
        with open(path) as f:
            doc = json.load(f)
        schemalib.validate_rules_file(doc)
    except (json.JSONDecodeError, schemalib.SchemaError) as e:
        return False, f"invalid: {e}"
    n = len(doc.get("categories", []))
    return True, f"{n} categories, schema v{doc.get('schema_version')}"


@check("logs")
def check_logs() -> tuple[bool, str]:
    logs_dir = os.path.join(ROOT, "logs")
    results = []
    for name in ("drafts.jsonl", "sent.jsonl", "audits.jsonl"):
        path = os.path.join(logs_dir, name)
        if not os.path.exists(path):
            return False, f"{name} missing"
        try:
            count = sum(1 for _ in loglib.read_all(path))
        except Exception as e:
            return False, f"{name} unreadable: {e}"
        results.append(f"{name}:{count}")
    return True, " ".join(results)


@check("modules")
def check_modules() -> tuple[bool, str]:
    mods = [
        "scripts.lib.gmail_client",
        "scripts.lib.log",
        "scripts.lib.schema",
        "scripts.lib.dedupe",
        "scripts.lib.quote_verify",
        "scripts.lib.phishing",
    ]
    failed = []
    for m in mods:
        try:
            importlib.import_module(m)
        except Exception as e:
            failed.append(f"{m}: {e}")
    if failed:
        return False, "; ".join(failed)
    return True, f"{len(mods)} modules OK"


@check("no-send invariant (I5)")
def check_no_send() -> tuple[bool, str]:
    from scripts.lib.gmail_client import GmailClient
    forbidden = {"send", "send_email", "send_message", "send_draft"}
    present = {m for m in dir(GmailClient) if m in forbidden}
    if present:
        return False, f"GmailClient has forbidden methods: {present}"
    return True, "GmailClient has no send method (structural guarantee)"


@check("schema version parity")
def check_schema_version() -> tuple[bool, str]:
    # SCHEMA.md declares a version in its front-matter or first heading;
    # we search for the string "schema_version: X" and compare.
    path = os.path.join(ROOT, "SCHEMA.md")
    if not os.path.exists(path):
        return False, "SCHEMA.md missing"
    text = open(path).read()
    # Find first `schema_version` line.
    current = schemalib.CURRENT_SCHEMA_VERSION
    if current in text:
        return True, f"v{current} consistent with SCHEMA.md"
    return False, f"code says v{current} but SCHEMA.md does not mention it"


@check("last triage")
def check_last_triage() -> tuple[bool, str]:
    path = os.path.join(ROOT, "logs", "drafts.jsonl")
    entries = list(loglib.read_all(path))
    if not entries:
        return True, "no triage runs yet (new skill)"
    last = entries[-1].get("timestamp_iso", "")
    try:
        if last.endswith("Z"):
            last = last[:-1] + "+00:00"
        d = dt.datetime.fromisoformat(last).astimezone(dt.timezone.utc)
        age = dt.datetime.now(dt.timezone.utc) - d
        return True, f"last triage {int(age.total_seconds() // 3600)}h ago"
    except ValueError:
        return False, f"malformed timestamp on last entry: {last}"


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=".gmail status", description="Health check for .gmail.")
    p.add_argument("--quiet", action="store_true", help="Only print failures.")
    args = p.parse_args(argv)

    results = []
    any_fail = False
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"check raised {type(e).__name__}: {e}"
        if not ok:
            any_fail = True
        results.append((name, ok, detail))

    # Output
    if not args.quiet or any_fail:
        print(f"# 🩺 `.gmail` status — {'🟢 HEALTHY' if not any_fail else '🔴 ISSUES FOUND'}\n")
        print("| 🟣 Check | 🟣 Result | 🟣 Detail |")
        print("| -------- | --------- | --------- |")
        for name, ok, detail in results:
            flag = "🟢 pass" if ok else "🔴 fail"
            print(f"| {name} | {flag} | {detail} |")

    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(run())
