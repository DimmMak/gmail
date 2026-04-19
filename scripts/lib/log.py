"""Append-only JSONL log writer.

Enforces invariants:
    I2 — append-only: only `append` exists; no update/delete.
    I4 — schema versioning: every write is validated via schema.py first.
    I7 — graceful degradation: malformed read lines are skipped with a warning.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Iterator

from . import schema


# Map filename stems to schema entry_type.
_TYPE_FOR_STEM = {
    "drafts": "draft",
    "sent": "sent",
    "audits": "audit",
}


def _infer_entry_type(log_path: str) -> str:
    stem = os.path.splitext(os.path.basename(log_path))[0]
    if stem not in _TYPE_FOR_STEM:
        raise ValueError(
            f"cannot infer entry_type from log filename '{stem}'. "
            f"Known stems: {list(_TYPE_FOR_STEM)}"
        )
    return _TYPE_FOR_STEM[stem]


def append(log_path: str, entry: dict[str, Any], entry_type: str | None = None) -> None:
    """Validate and append one JSON line to log_path.

    Creates the file if missing. Always writes with trailing newline.
    entry_type defaults to inference from the filename stem.
    """
    et = entry_type or _infer_entry_type(log_path)
    schema.validate(entry, et)

    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")


def read_all(log_path: str) -> Iterator[dict[str, Any]]:
    """Yield each JSON line as a dict. Skip malformed lines with a warning.

    Graceful: if the file does not exist, yield nothing.
    """
    if not os.path.exists(log_path):
        return
    with open(log_path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                print(
                    f"[log.read_all] WARN {log_path}:{lineno} malformed line skipped: {exc}",
                    file=sys.stderr,
                )
                continue


def count(log_path: str) -> int:
    """Return number of well-formed entries in log."""
    return sum(1 for _ in read_all(log_path))
