"""Sensitive-app denylist: block capture for password managers, banking apps, etc.

Matches the active process name against the configured denylist. See SPEC.md §10.
"""

from __future__ import annotations

from collections.abc import Iterable


def is_denied(process_name: str, denylist: Iterable[str]) -> bool:
    """Return True if the (case-insensitive) process name is on the denylist."""
    name = (process_name or "").strip().lower()
    if not name:
        return False
    return any(name == entry.strip().lower() for entry in denylist)
