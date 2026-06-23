"""Shared utilities for garuda_frr package."""

from __future__ import annotations


def csv_split(value: str) -> list[str]:
    """Split a CSV string into a list, stripping whitespace from each item.

    Returns an empty list for empty or whitespace-only input.
    """
    if not value or not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
