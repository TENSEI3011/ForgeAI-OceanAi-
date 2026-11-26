"""Exact lookup / filter over CSV files that live in the agent's documents folder."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rapidfuzz import process

from ..ingest import _read_table, row_to_text

MAX_ROWS = 8


def _num(v: str) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def list_tables(docs_dir: str) -> dict[str, list[str]]:
    out = {}
    for p in sorted(Path(docs_dir).rglob("*")):
        if p.suffix.lower() in {".csv", ".tsv"}:
            cols, _ = _read_table(p)
            out[p.relative_to(docs_dir).as_posix()] = cols
    return out


def run(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    docs_dir = ctx["documents_dir"]
    tables = list_tables(docs_dir)
    if not tables:
        return "ERROR: no CSV files in the documents folder"
    file = str(args.get("file") or "")
    if file not in tables:   # tolerate missing/approximate file names
        file = process.extractOne(file, list(tables))[0] if file else next(iter(tables))
    cols, rows = _read_table(Path(docs_dir) / file)
    column = str(args.get("column") or "")
    value = str(args.get("value") or "").strip()
    match = str(args.get("match") or "equals").lower()
    if column not in cols:
        if not column:
            # no column: search every column for the value
            hits = [r for r in rows if value.lower() in row_to_text(r).lower()]
            return _format(file, hits, f"any column contains '{value}'")
        column = process.extractOne(column, cols)[0]

    def keep(row: dict[str, str]) -> bool:
        cell = row.get(column, "")
        if match in {"lt", "<", "less_than"}:
            a, b = _num(cell), _num(value)
            return a is not None and b is not None and a < b
        if match in {"gt", ">", "greater_than"}:
            a, b = _num(cell), _num(value)
            return a is not None and b is not None and a > b
        if match == "contains":
            return value.lower() in cell.lower()
        return cell.lower() == value.lower()

    hits = [r for r in rows if keep(r)]
    if not hits and match == "equals":   # graceful fallback to substring match
        hits = [r for r in rows if value.lower() in r.get(column, "").lower()]
    return _format(file, hits, f"{column} {match} '{value}'")


def _format(file: str, hits: list[dict[str, str]], desc: str) -> str:
    if not hits:
        return f"{file}: no rows where {desc}"
    lines = [f"{file}: {len(hits)} row(s) where {desc}" + (f" (showing first {MAX_ROWS})" if len(hits) > MAX_ROWS else "")]
    lines += [f"- {row_to_text(r)}" for r in hits[:MAX_ROWS]]
    return "\n".join(lines)
