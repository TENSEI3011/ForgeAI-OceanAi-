"""Load a folder of documents and cut it into retrievable chunks.

Supported: .pdf .txt .md .csv .tsv .docx .html/.htm .json. Unknown files are skipped
*and reported* (the review folder is unseen, so we never fail silently on a format).

Chunking strategy
* prose: split on paragraphs, pack paragraphs up to `chunk_size` characters, split long
  paragraphs on sentence boundaries, carry `overlap` characters of trailing sentences into
  the next chunk. Every chunk remembers its page (PDF) and nearest heading.
* tables (CSV): one chunk per row rendered as "col: value | col: value", plus a schema
  chunk describing the columns, so both semantic and exact (BM25 / csv_lookup) access work.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = {".pdf", ".txt", ".md", ".csv", ".tsv", ".docx", ".html", ".htm", ".json"}


@dataclass
class Doc:
    source: str                      # file name relative to the docs folder
    type: str                        # pdf | text | table
    text: str                        # full plain text (tables: rendered rows)
    pages: list[str] = field(default_factory=list)         # PDF pages
    columns: list[str] = field(default_factory=list)       # tables
    rows: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Chunk:
    chunk_id: str
    source: str
    text: str
    page: int | None = None
    row: int | None = None
    heading: str = ""

    @property
    def embed_text(self) -> str:
        """Text used for embedding/BM25: prefixed with file + heading ("contextual header")."""
        head = f"{Path(self.source).stem.replace('_', ' ')}"
        if self.heading:
            head += f" > {self.heading}"
        return f"{head}\n{self.text}"


# ------------------------------------------------------------------ loading
def _read_pdf(path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return [(p.extract_text() or "").strip() for p in reader.pages]


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, flags=re.S)
        paras.append(html.unescape("".join(texts)))
    return "\n\n".join(t for t in paras if t.strip())


def _read_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<(br|/p|/div|/h\d|/li|/tr)[^>]*>", "\n", raw, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", raw))


def _read_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    try:
        delim = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|").delimiter
    except csv.Error:
        pass
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    cols = [c.strip() for c in (reader.fieldnames or [])]
    rows = []
    for r in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None})
    return cols, rows


def row_to_text(row: dict[str, str]) -> str:
    return " | ".join(f"{k}: {v}" for k, v in row.items() if v != "")


def load_documents(docs_dir: str | Path) -> tuple[list[Doc], list[str]]:
    """Return (documents, skipped_files)."""
    root = Path(docs_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"documents folder not found: {root}")
    docs: list[Doc] = []
    skipped: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        ext = path.suffix.lower()
        if ext not in SUPPORTED or path.name.startswith((".", "~$")):
            skipped.append(rel)
            continue
        try:
            if ext == ".pdf":
                pages = _read_pdf(path)
                docs.append(Doc(rel, "pdf", "\n\n".join(pages), pages=pages))
            elif ext in {".csv", ".tsv"}:
                cols, rows = _read_table(path)
                text = "\n".join(row_to_text(r) for r in rows)
                docs.append(Doc(rel, "table", text, columns=cols, rows=rows))
            elif ext == ".docx":
                docs.append(Doc(rel, "text", _read_docx(path)))
            elif ext in {".html", ".htm"}:
                docs.append(Doc(rel, "text", _read_html(path)))
            elif ext == ".json":
                data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                docs.append(Doc(rel, "text", json.dumps(data, indent=2, ensure_ascii=False)))
            else:
                docs.append(Doc(rel, "text", path.read_text(encoding="utf-8", errors="ignore")))
        except Exception as exc:  # a broken file must not kill an unattended run
            skipped.append(f"{rel} (unreadable: {exc})")
    docs = [d for d in docs if d.text.strip()]
    return docs, skipped


# ------------------------------------------------------------------ chunking
_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|(\d+(\.\d+)*\.?|[A-Z]\.|Section \d+[.:]?)\s+[A-Z].{0,80}|[A-Z][A-Z0-9 ,&/\-()]{3,70})$")


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 90 or line.endswith((".", ",", ";", ":")) and not line.startswith("#"):
        return False
    return bool(_HEADING_RE.match(line))


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"'])", text)
    return [p.strip() for p in parts if p.strip()]


def _paragraphs(text: str) -> list[str]:
    """Paragraphs, with PDF hard-wraps re-joined and headings kept as their own paragraph."""
    text = text.replace("\r", "")
    blocks = re.split(r"\n\s*\n", text)
    out: list[str] = []
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        buf: list[str] = []
        for line in lines:
            starts_item = bool(re.match(r"^([-*•]|\d+[.)]|\(?[a-z]\))\s", line))
            if _is_heading(line) or starts_item:
                if buf:
                    out.append(" ".join(buf))
                    buf = []
                if _is_heading(line):
                    out.append(line)
                    continue
            buf.append(line)
        if buf:
            out.append(" ".join(buf))
    return out


def _chunk_prose(doc: Doc, chunk_size: int, overlap: int, start_id: int) -> list[Chunk]:
    units = [(i + 1, t) for i, t in enumerate(doc.pages)] if doc.pages else [(None, doc.text)]
    chunks: list[Chunk] = []
    heading = ""
    n = start_id
    for page, text in units:
        buf: list[str] = []
        size = 0      # chars in buffer (including carried-over overlap)
        fresh = 0     # chars added since the last flush (overlap tail excluded)

        def flush() -> None:
            nonlocal buf, size, fresh, n
            body = " ".join(buf).strip()
            if len(body) >= 20:
                chunks.append(Chunk(f"{doc.source}#{n}", doc.source, body, page=page, heading=heading))
                n += 1
            # overlap: keep trailing sentences up to `overlap` chars for the next chunk
            tail: list[str] = []
            tail_len = 0
            for sent in reversed(_split_sentences(body)):
                if tail_len + len(sent) > overlap:
                    break
                tail.insert(0, sent)
                tail_len += len(sent) + 1
            buf, size, fresh = tail, tail_len, 0

        for para in _paragraphs(text):
            if _is_heading(para):
                if fresh:
                    flush()
                buf, size, fresh = [], 0, 0   # never carry overlap across a heading
                heading = para.lstrip("# ").strip()
                continue
            pieces = [para] if len(para) <= chunk_size else _split_sentences(para)
            for piece in pieces:
                if size + len(piece) > chunk_size and fresh:
                    flush()
                buf.append(piece)
                size += len(piece) + 1
                fresh += len(piece) + 1
        if fresh:
            flush()
    return chunks


def _chunk_table(doc: Doc, start_id: int) -> list[Chunk]:
    n = start_id
    schema = (f"Table {doc.source} has {len(doc.rows)} rows. Columns: {', '.join(doc.columns)}. "
              f"Example row: {row_to_text(doc.rows[0]) if doc.rows else '(empty)'}")
    chunks = [Chunk(f"{doc.source}#{n}", doc.source, schema, heading="table schema")]
    n += 1
    for i, row in enumerate(doc.rows):
        chunks.append(Chunk(f"{doc.source}#{n}", doc.source, row_to_text(row), row=i + 1, heading="row"))
        n += 1
    return chunks


def chunk_documents(docs: list[Doc], chunk_size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        if doc.type == "table":
            chunks.extend(_chunk_table(doc, 0))
        else:
            chunks.extend(_chunk_prose(doc, chunk_size, min(overlap, chunk_size // 2), 0))
    return chunks


def doc_stats(docs: list[Doc]) -> dict[str, float]:
    """Numbers the generator uses to pick chunking/retrieval parameters deterministically."""
    prose = [d for d in docs if d.type != "table"]
    paras = [p for d in prose for p in _paragraphs(d.text) if not _is_heading(p)]
    return {
        "n_docs": len(docs),
        "n_tables": sum(d.type == "table" for d in docs),
        "table_rows": sum(len(d.rows) for d in docs),
        "prose_chars": sum(len(d.text) for d in prose),
        "avg_paragraph_chars": (sum(map(len, paras)) / len(paras)) if paras else 0.0,
    }


def headings_of(doc: Doc, limit: int = 15) -> list[str]:
    if doc.type == "table":
        return []
    heads = [p.lstrip("# ").strip() for p in _paragraphs(doc.text) if _is_heading(p)]
    return heads[:limit]
