"""Baselines, drift and trend: whether a document reads like the writer's own work.

A baseline stores the mean and spread of every tracked metric across a corpus. Drift is the
distance of one document from it. A drift score is a distance, not a verdict.
"""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clarity.config import Config
from clarity.corpus import RELIABLE_DOCS, RELIABLE_WORDS, documents
from clarity.engine import analyze
from clarity.metrics import extract
from clarity.resolve import find_project_dir, user_dir

WITHIN = 1.5
SHOWN = 8


class BaselineError(ValueError):
    """A baseline that cannot be built, found or used."""


def store(create: bool = False) -> Path:
    """The project baselines folder (.clarity/baselines), created on demand."""
    folder = (find_project_dir(Path.cwd()) or Path.cwd() / ".clarity") / "baselines"

    if create:
        folder.mkdir(parents=True, exist_ok=True)

    return folder


def _paths(name: str) -> list[Path]:
    return [store() / f"{name}.json", user_dir() / "baselines" / f"{name}.json"]


def build(corpus: Path, name: str, config: Config) -> dict[str, Any]:
    """Compute every tracked metric across the corpus and store mean and spread per metric."""
    if not corpus.exists():
        raise BaselineError(f"{corpus}: no such file or folder")

    per_doc: list[dict[str, float]] = []
    hits: dict[str, int] = {}
    words = 0

    for file, text in documents(corpus):
        result = analyze(text, source=str(file), config=config)
        words += result["words"]
        per_doc.append(extract(result["prose_metrics"]["metrics"]))

        for f in result["findings"]:
            hits[f["rule"]] = hits.get(f["rule"], 0) + 1

    if len(per_doc) < RELIABLE_DOCS or words < RELIABLE_WORDS:
        raise BaselineError(
            f"{corpus} has {len(per_doc)} documents and {words:,} words. A baseline needs at "
            f"least {RELIABLE_DOCS} documents and {RELIABLE_WORDS:,} words; thinner data is "
            "noise presented as a norm."
        )

    metrics = {}

    for key in sorted({k for row in per_doc for k in row}):
        values = [row[key] for row in per_doc if key in row]

        if len(values) >= 2:
            metrics[key] = {"mean": statistics.fmean(values), "sd": statistics.stdev(values),
                            "n": len(values)}  # fmt: skip

    data = {
        "name": name,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "documents": len(per_doc),
        "words": words,
        "metrics": metrics,
        "rule_hits_per_1k": {r: round(n * 1000 / words, 3) for r, n in sorted(hits.items())},
    }
    path = store(create=True) / f"{name}.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {**data, "path": str(path)}


def load(name: str) -> dict[str, Any]:
    for path in _paths(name):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    raise BaselineError(f"no baseline named {name!r}; build one with: clarity baseline build PATH")


def names() -> list[str]:
    folders = (store(), user_dir() / "baselines")
    found = {p.stem for folder in folders for p in folder.glob("*.json")}

    return sorted(found)


def drift(metric_results: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """z-score of each tracked metric against the baseline, most divergent first."""
    values = extract(metric_results)
    rows = []

    for key, stats in base["metrics"].items():
        if key not in values or not stats["sd"]:
            continue

        z = (values[key] - stats["mean"]) / stats["sd"]
        rows.append({"metric": key, "value": values[key], "mean": stats["mean"], "sd": stats["sd"],
                     "z": z})  # fmt: skip

    rows.sort(key=lambda r: -abs(r["z"]))
    outside = [r for r in rows if abs(r["z"]) >= WITHIN]
    score = statistics.fmean(abs(r["z"]) for r in rows) if rows else 0.0

    return {
        "baseline": {"name": base["name"], "documents": base["documents"], "words": base["words"]},
        "most_divergent": outside[:SHOWN],
        "within_range": len(rows) - len(outside),
        "score": round(score, 2),
        "metrics": len(rows),
    }


def _num(x: float) -> str:
    return f"{x:.2f}" if abs(x) < 100 else f"{x:.0f}"


def format_drift(result: dict[str, Any]) -> str:
    b = result["baseline"]
    out = [f"baseline: {b['name']} ({b['documents']} docs, {b['words'] // 1000}k words)", ""]
    out.append("MOST DIVERGENT")

    for r in result["most_divergent"]:
        way = "above" if r["z"] > 0 else "below"
        out.append(f"  {r['metric']:<44}{abs(r['z']):>5.2f}   σ {way:<6}"
                   f"{_num(r['value'])} vs {_num(r['mean'])} ±{_num(r['sd'])}")  # fmt: skip

    if not result["most_divergent"]:
        out.append("  none")

    out += ["", "WITHIN RANGE", f"  {result['within_range']} metrics within {WITHIN:g}σ", "",
            f"DRIFT SCORE  {result['score']:g}   (mean absolute z across all {result['metrics']} "
            "metrics)", "", "Drift is a distance from the baseline, not a verdict. A document you "
            "wrote differently on purpose should drift."]  # fmt: skip

    return "\n".join(out)


def format_show(base: dict[str, Any]) -> str:
    out = [f"{base['name']}   {base['documents']} documents · {base['words']:,} words · "
           f"{base['created']}", "", f"{'METRIC':<46}{'MEAN':>9}{'SD':>9}"]  # fmt: skip

    for key, s in base["metrics"].items():
        out.append(f"{key:<46}{_num(s['mean']):>9}{_num(s['sd']):>9}")

    return "\n".join(out)


# ---- trend --------------------------------------------------------------------------------


def history_path(path: Path) -> Path:
    from clarity.harness import snapshot_dir

    return snapshot_dir() / f"{path.stem}.history.jsonl"


def _row(date: str, result: dict[str, Any]) -> dict[str, Any]:
    hits: dict[str, int] = {}

    for f in result["findings"]:
        hits[f["rule"]] = hits.get(f["rule"], 0) + 1

    return {"date": date, "words": result["words"], "score": result["score"], "rule_hits": hits,
            "metrics": extract(result["prose_metrics"]["metrics"])}  # fmt: skip


def record(path: Path, result: dict[str, Any]) -> None:
    """Append one row of history for a document: its rule hits, score and tracked metrics."""
    target = history_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_row(datetime.now(UTC).date().isoformat(), result)) + "\n")


def history(path: Path, config: Config) -> list[dict[str, Any]]:
    """Rows for a file (its snapshot history, then now) or a folder (drafts oldest first)."""
    if path.is_dir():
        drafts = sorted(
            (p for p in path.iterdir() if p.suffix in {".md", ".txt", ".markdown"}),
            key=lambda p: p.stat().st_mtime,
        )

        return [_row(datetime.fromtimestamp(p.stat().st_mtime, UTC).date().isoformat(),
                     analyze(p.read_text(encoding="utf-8"), source=str(p), config=config))
                for p in drafts]  # fmt: skip

    rows = []
    stored = history_path(path)

    if stored.is_file():
        lines = stored.read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line]

    now = analyze(path.read_text(encoding="utf-8"), source=str(path), config=config)
    rows.append(_row("now", now))

    return rows


def format_trend(rows: list[dict[str, Any]], rule: str | None, metric: str | None,
                 allowance: float | None) -> str:  # fmt: skip
    out = []

    for row in rows:
        if rule:
            n = row["rule_hits"].get(rule, 0)
            rate = n * 1000 / row["words"] if row["words"] else 0.0
            mark = ""

            if allowance is not None and rate <= allowance:
                mark = "   ← within allowance"

            noun = "hit" if n == 1 else "hits"
            out.append(f"  {row['date']:<12}{n:>3} {noun:<5}{rate:>6.1f}/1k{mark}")
        elif metric:
            value = row["metrics"].get(metric)
            shown = "n/a" if value is None else _num(value)
            out.append(f"  {row['date']:<12}{shown:>9}")
        else:
            out.append(f"  {row['date']:<12}score {row['score']:>5.1f}   "
                       f"{sum(row['rule_hits'].values()):>3} findings")  # fmt: skip

    return "\n".join(out)
