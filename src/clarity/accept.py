"""Persistent exemptions stored in .clarity-accept."""

from __future__ import annotations

from pathlib import Path

ACCEPT_FILE = ".clarity-accept"


def load_accepted(path: str | Path = ACCEPT_FILE) -> set[str]:
    p = Path(path)

    if not p.exists():
        return set()

    ids = set()

    for line in p.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()

        if token:
            ids.add(token)

    return ids


def accept(finding_id: str, path: str | Path = ACCEPT_FILE) -> bool:
    """Append an exemption. Returns False if already present."""
    if finding_id in load_accepted(path):
        return False

    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(finding_id + "\n")

    return True
