"""Schema migration stub for .gmail.

v0.1 has no prior version, so there is nothing to migrate. This file exists
to document the pattern for future upgrades and to give operators a single
place to look when schema_version bumps.

Usage pattern for future versions:

    def v0_1_to_v0_2(entry: dict) -> dict:
        # e.g. rename field, add default, split one field into two.
        entry["schema_version"] = "0.2"
        return entry

    _CHAIN = [
        ("0.1", "0.2", v0_1_to_v0_2),
        ("0.2", "0.3", v0_2_to_v0_3),
    ]

    def migrate(from_version: str, to_version: str) -> None:
        # walk _CHAIN from from_version to to_version, rewriting each
        # logs/*.jsonl file in place (via write-to-temp + rename).

Stdlib only.
"""

from __future__ import annotations


class MigrationError(RuntimeError):
    pass


def migrate(from_version: str, to_version: str) -> None:
    """Walk the migration chain from from_version to to_version.

    v0.1 is the initial release — no chain exists yet.
    """
    raise NotImplementedError(
        f"No migration defined: {from_version} -> {to_version}. "
        "v0.1 is the initial release. When schema_version bumps, add the "
        "step to _CHAIN in this module and update SCHEMA.md + CHANGELOG.md."
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: migrate.py <from_version> <to_version>", file=sys.stderr)
        raise SystemExit(2)
    migrate(sys.argv[1], sys.argv[2])
