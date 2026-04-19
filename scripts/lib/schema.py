"""Schema validator for .gmail log entries and rules.

Enforces invariant I4 (schema versioning): every entry must carry a
`schema_version` field. Also enforces required-field shape per SCHEMA.md.

Stdlib only.
"""

from __future__ import annotations

from typing import Any


CURRENT_SCHEMA_VERSION = "0.1"


class SchemaError(ValueError):
    """Raised when an entry fails schema validation."""


# Required top-level fields per entry type, mirrored from SCHEMA.md.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "draft": (
        "schema_version",
        "timestamp_iso",
        "thread_id",
        "thread_fingerprint",
        "category_id",
        "rules_version",
        "draft_preview",
        "confidence",
        "status",
    ),
    "sent": (
        "schema_version",
        "timestamp_iso",
        "thread_id",
        "original_draft_hash",
        "final_text",
        "edit_distance",
        "decision",
        "reviewer",
    ),
    "audit": (
        "schema_version",
        "timestamp_iso",
        "period",
        "sample_size",
        "findings",
        "suggested_prompt_changes",
    ),
    "rule": (
        "id",
        "match",
        "action",
        "min_confidence",
    ),
    "unsub": (
        "schema_version",
        "timestamp_iso",
        "thread_id",
        "sender",
        "subject",
        "action",
        "status",
    ),
}

_ALLOWED_STATUS = {"pending_review", "flagged_for_human", "skipped", "superseded"}
_ALLOWED_DECISION = {"approved", "edited", "rejected"}
_ALLOWED_ACTION = {"draft", "label", "flag"}


def validate(entry: dict[str, Any], entry_type: str) -> None:
    """Raise SchemaError if entry is invalid for the given type.

    entry_type must be one of: 'draft', 'sent', 'audit', 'rule'.
    """
    if entry_type not in _REQUIRED:
        raise SchemaError(f"unknown entry_type: {entry_type}")

    if not isinstance(entry, dict):
        raise SchemaError(f"entry must be a dict, got {type(entry).__name__}")

    missing = [k for k in _REQUIRED[entry_type] if k not in entry]
    if missing:
        raise SchemaError(f"{entry_type}: missing required fields: {missing}")

    # Type- and value-level checks per entry_type.
    if entry_type == "draft":
        fp = entry["thread_fingerprint"]
        if not isinstance(fp, dict) or not {"from", "subject", "date_iso"} <= set(fp):
            raise SchemaError("draft.thread_fingerprint must include from, subject, date_iso")
        if not isinstance(entry["confidence"], int) or not (1 <= entry["confidence"] <= 5):
            raise SchemaError("draft.confidence must be int 1-5")
        if entry["status"] not in _ALLOWED_STATUS:
            raise SchemaError(f"draft.status must be one of {_ALLOWED_STATUS}")
        if not isinstance(entry["draft_preview"], str) or len(entry["draft_preview"]) > 200:
            raise SchemaError("draft.draft_preview must be str <= 200 chars")
        # phishing_report is optional (backward-compat with v0.1.0 / v0.1.1 / v0.1.2 entries)
        if "phishing_report" in entry:
            pr = entry["phishing_report"]
            if not isinstance(pr, dict) or "total_score" not in pr:
                raise SchemaError("draft.phishing_report must be a dict with total_score")

    elif entry_type == "sent":
        if entry["decision"] not in _ALLOWED_DECISION:
            raise SchemaError(f"sent.decision must be one of {_ALLOWED_DECISION}")
        ed = entry["edit_distance"]
        if not isinstance(ed, (int, float)) or not (0.0 <= float(ed) <= 1.0):
            raise SchemaError("sent.edit_distance must be 0.0-1.0")

    elif entry_type == "audit":
        if not isinstance(entry["findings"], dict):
            raise SchemaError("audit.findings must be a dict")
        if not isinstance(entry["suggested_prompt_changes"], list):
            raise SchemaError("audit.suggested_prompt_changes must be a list")

    elif entry_type == "unsub":
        allowed_actions = {"none", "draft_queued", "manual_click",
                           "manual_mailto", "manual_gmail_ui", "dry_run"}
        if entry["action"] not in allowed_actions:
            raise SchemaError(f"unsub.action must be one of {allowed_actions}")

    elif entry_type == "rule":
        if entry["action"] not in _ALLOWED_ACTION:
            raise SchemaError(f"rule.action must be one of {_ALLOWED_ACTION}")
        mc = entry["min_confidence"]
        if not isinstance(mc, int) or not (1 <= mc <= 5):
            raise SchemaError("rule.min_confidence must be int 1-5")


def validate_rules_file(doc: dict[str, Any]) -> None:
    """Validate the full rules.json document."""
    if not isinstance(doc, dict):
        raise SchemaError("rules.json root must be an object")
    if "schema_version" not in doc:
        raise SchemaError("rules.json missing schema_version")
    if "categories" not in doc or not isinstance(doc["categories"], list):
        raise SchemaError("rules.json must have a categories list")
    ids = set()
    for cat in doc["categories"]:
        validate(cat, "rule")
        if cat["id"] in ids:
            raise SchemaError(f"duplicate category id: {cat['id']}")
        ids.add(cat["id"])
