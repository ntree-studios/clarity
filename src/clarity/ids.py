"""Stable finding identifiers: hash of rule id plus normalized span."""

import hashlib
import re

_WS = re.compile(r"\s+")


def normalize_span(span: str) -> str:
    return _WS.sub(" ", span).strip().lower()


def finding_id(rule_id: str, span: str) -> str:
    digest = hashlib.sha256(f"{rule_id}\x00{normalize_span(span)}".encode()).hexdigest()
    return digest[:12]
