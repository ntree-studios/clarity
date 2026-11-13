"""Finding and sizing a folder of writing."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
HARD_DOCS, HARD_WORDS = 10, 5_000
RELIABLE_DOCS, RELIABLE_WORDS = 25, 20_000
WORD = re.compile(r"\w+")


@dataclass
class Size:
    path: str
    documents: int
    words: int

    @property
    def reliability(self) -> str:
        """insufficient below the hard floor, provisional below the reliable floor."""
        if self.documents < HARD_DOCS or self.words < HARD_WORDS:
            return "insufficient"

        if self.documents < RELIABLE_DOCS or self.words < RELIABLE_WORDS:
            return "provisional"

        return "reliable"


def corpus_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    return sorted(p for p in path.rglob("*") if p.suffix in TEXT_SUFFIXES)


def documents(path: Path) -> Iterator[tuple[Path, str]]:
    """Readable UTF-8 documents under path; unreadable files are skipped."""
    for file in corpus_files(path):
        try:
            yield file, file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue


def measure_size(path: Path) -> Size:
    if not path.exists():
        raise ValueError(f"{path}: no such file or folder")

    docs = words = 0

    for _, text in documents(path):
        docs += 1
        words += len(WORD.findall(text))

    return Size(str(path), docs, words)


def require_floor(size: Size) -> None:
    """Refuse to produce a ratio from a corpus too thin to mean anything."""
    if size.reliability == "insufficient":
        raise ValueError(
            f"{size.path} has {size.documents} documents and {size.words:,} words. "
            f"A ratio needs at least {HARD_DOCS} documents and {HARD_WORDS:,} words per corpus. "
            "Add more writing; a ratio from less is noise."
        )
