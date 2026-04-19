"""Read `prompt_version` from the header comment of a prompt markdown file.

Format expected (at top of every prompts/*.md):

    <!--
    prompt_version: "0.1.0"
    last_changed: "YYYY-MM-DD"
    -->

This module parses that header deterministically so triage log entries
can attribute drafts to specific prompt versions. Enables the monthly
architect audit to say "edit rate went up starting with prompt/draft.md
v0.3" instead of just "edit rate went up."

Stdlib only. Pure functions.
"""

from __future__ import annotations

import os
import re


_HEADER_RE = re.compile(
    r"<!--\s*\n"
    r"\s*prompt_version:\s*\"?([^\"\s\n]+)\"?\s*\n"
    r"(?:\s*last_changed:\s*\"?([^\"\s\n]+)\"?\s*\n)?"
    r"\s*-->",
    re.MULTILINE,
)


def read_version(prompt_path: str) -> dict[str, str | None]:
    """Parse the prompt_version / last_changed header.

    Returns {"prompt_version": str|None, "last_changed": str|None}.
    Missing header → both fields None. Never raises on a well-formed md.
    """
    if not os.path.exists(prompt_path):
        return {"prompt_version": None, "last_changed": None}

    try:
        # Only look at first 500 bytes — header must be at top.
        # errors="replace" tolerates non-UTF-8 input without crashing
        # (e.g. a file corrupted or accidentally binary). The header
        # must still be valid UTF-8 to match; replacement chars won't.
        with open(prompt_path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(500)
    except (OSError, IsADirectoryError):
        return {"prompt_version": None, "last_changed": None}

    m = _HEADER_RE.search(head)
    if not m:
        return {"prompt_version": None, "last_changed": None}
    return {
        "prompt_version": m.group(1),
        "last_changed": m.group(2),
    }


def read_all(prompts_dir: str) -> dict[str, dict[str, str | None]]:
    """Read version headers for every *.md in prompts_dir.

    Returns {prompt_name_without_extension: {prompt_version, last_changed}}.
    """
    out: dict[str, dict[str, str | None]] = {}
    if not os.path.isdir(prompts_dir):
        return out
    for fname in sorted(os.listdir(prompts_dir)):
        if not fname.endswith(".md"):
            continue
        key = fname[:-3]
        out[key] = read_version(os.path.join(prompts_dir, fname))
    return out
