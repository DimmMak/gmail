"""Gmail client wrapper.

Primary backend: Gmail MCP server (tools exposed in the Claude Code harness).
Fallback backend: Cowork direct-IMAP adapter (future work, not wired in v0.1).

Design notes
------------
- MCP is the ONLY backend in v0.1. Cowork methods raise NotImplementedError
  to document the interface without committing to an implementation.
- No `send` method exists on this class. That absence IS invariant I5 — the
  structural no-send guarantee. Do not add one without updating SKILL.md,
  ARCHITECTURE.md, and the capability surface.
- All methods are documented contracts; in practice, Claude (the harness)
  calls the MCP tools directly. This module exists so Python entry points
  (triage.py, review.py, audit.py) have a typed seam to program against
  and for future Cowork wiring.

Stdlib only.
"""

from __future__ import annotations

from typing import Any, Iterable


class GmailClientError(Exception):
    """Raised on any backend failure. Caller handles I7 graceful degradation."""


class GmailClient:
    """Typed seam over the Gmail MCP surface.

    In v0.1 the methods are stubs that document the contract. Runtime behavior
    is delegated to the MCP tools invoked directly by the Claude harness:

        mcp__gmail__search_threads
        mcp__gmail__get_thread
        mcp__gmail__create_draft
        mcp__gmail__list_drafts
        mcp__gmail__list_labels
        mcp__gmail__create_label

    When Cowork support is wired, pass backend="cowork" to the constructor.
    """

    def __init__(self, backend: str = "mcp") -> None:
        if backend not in {"mcp", "cowork"}:
            raise GmailClientError(f"unknown backend: {backend}")
        self.backend = backend

    # ---- read surface -------------------------------------------------

    def search_threads(self, query: str) -> list[dict[str, Any]]:
        """Return a list of thread metadata dicts matching `query`.

        Contract (per MCP tool `search_threads`):
            input:  Gmail search string, e.g. "is:unread newer_than:1d"
            output: [{"thread_id": str, "snippet": str, "from": str,
                      "subject": str, "date_iso": str}, ...]
        """
        if self.backend == "cowork":
            raise NotImplementedError("Cowork IMAP backend is future work (v0.2+).")
        # MCP path: the harness invokes the MCP tool. This stub documents
        # the contract; the real call is made at the harness level.
        raise NotImplementedError(
            "GmailClient.search_threads: invoke MCP tool `search_threads` "
            "from the harness. This Python seam exists for future Cowork wiring."
        )

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Return full thread with messages.

        Contract:
            output: {"thread_id": str,
                     "messages": [{"from", "to", "subject", "date_iso", "body"}, ...]}
        """
        if self.backend == "cowork":
            raise NotImplementedError("Cowork IMAP backend is future work (v0.2+).")
        raise NotImplementedError(
            "GmailClient.get_thread: invoke MCP tool `get_thread` from the harness."
        )

    def list_drafts(self) -> list[dict[str, Any]]:
        """Return current drafts in the mailbox.

        Contract:
            output: [{"draft_id": str, "thread_id": str, "snippet": str}, ...]
        """
        if self.backend == "cowork":
            raise NotImplementedError("Cowork IMAP backend is future work (v0.2+).")
        raise NotImplementedError(
            "GmailClient.list_drafts: invoke MCP tool `list_drafts` from the harness."
        )

    def list_labels(self) -> list[dict[str, Any]]:
        """Return Gmail labels.

        Contract:
            output: [{"label_id": str, "name": str, "type": "system" | "user"}, ...]
        """
        if self.backend == "cowork":
            raise NotImplementedError("Cowork IMAP backend is future work (v0.2+).")
        raise NotImplementedError(
            "GmailClient.list_labels: invoke MCP tool `list_labels` from the harness."
        )

    # ---- write surface ------------------------------------------------

    def create_draft(self, thread_id: str, text: str) -> dict[str, Any]:
        """Create a reply draft in the given thread.

        Contract:
            input:  thread_id, plain-text body (no subject, no signature)
            output: {"draft_id": str, "thread_id": str}

        Note: this is the ONLY write path to Gmail in v0.1. There is no `send`.
        """
        if self.backend == "cowork":
            raise NotImplementedError("Cowork IMAP backend is future work (v0.2+).")
        raise NotImplementedError(
            "GmailClient.create_draft: invoke MCP tool `create_draft` from the harness."
        )

    # ---- capability surface the class deliberately does NOT expose ----
    # send(...)      — absent on purpose. Invariant I5.
    # delete(...)    — absent on purpose. See SKILL.md Non-Goals.
    # modify(...)    — absent on purpose. See SKILL.md Non-Goals.


def iter_unread(client: GmailClient) -> Iterable[dict[str, Any]]:
    """Convenience iterator over unread threads. Newest first."""
    yield from client.search_threads("is:unread")
