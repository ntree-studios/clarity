"""Persistent exemptions stored in .clarity-accept."""

from __future__ import annotations

from pathlib import Path

ACCEPT_FILE = ".clarity-accept"


def write_path() -> Path:
    """The working-directory config when it exists, so a read-only user config is safe."""
    from clarity.resolve import find_project_dir

    project = find_project_dir(Path.cwd())

    return project / ACCEPT_FILE if project else Path(ACCEPT_FILE)


def read_paths() -> list[Path]:
    from clarity.resolve import find_project_dir, user_dir

    project = find_project_dir(Path.cwd())
    nearest = [project / ACCEPT_FILE] if project else []
    found = [user_dir() / ACCEPT_FILE, Path(ACCEPT_FILE), *nearest]

    return [p for i, p in enumerate(found) if p.exists() and p not in found[:i]]


def load_accepted(path: str | Path | None = None) -> set[str]:
    ids: set[str] = set()

    for p in [Path(path)] if path is not None else read_paths():
        if not p.exists():
            continue

        for line in p.read_text(encoding="utf-8").splitlines():
            token = line.split("#", 1)[0].strip()

            if token:
                ids.add(token)

    return ids


def accept(finding_id: str, path: str | Path | None = None) -> bool:
    """Append an exemption. Returns False if already present."""
    target = Path(path) if path is not None else write_path()

    if finding_id in load_accepted(target):
        return False

    with target.open("a", encoding="utf-8") as fh:
        fh.write(finding_id + "\n")

    return True


MIN_PREFIX = 6


def is_accepted(finding_id: str, accepted: set[str]) -> bool:
    """True when an exemption equals the id or is a prefix of it (the report shows six chars)."""
    return any(len(a) >= MIN_PREFIX and finding_id.startswith(a) for a in accepted)
