"""Shared utilities for garuda-frr-sidecar image modules.

Modules in this image (render_frr, transit_watcher, vty_bridge, vtysh_client)
all live in /usr/lib/frr/ at runtime and import each other directly.
"""

from __future__ import annotations


def csv_split(value: str) -> list[str]:
    """Split a CSV string into a list, stripping whitespace from each item.

    Returns an empty list for empty or whitespace-only input.
    """
    if not value or not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
