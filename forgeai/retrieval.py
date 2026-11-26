"""Hybrid retrieval: dense (MiniLM via Ollama, cosine) + BM25, fused with Reciprocal Rank Fusion.

Why hybrid: dense vectors handle paraphrase ("time off" ~ "vacation days"); BM25 handles
exact tokens a 384-d embedding blurs (part numbers, codes, rare names). RRF fuses ranks,
so neither score scale has to be calibrated against the other.

`min_score` is applied to the dense cosine similarity (a stable, comparable number), with
one exception: a chunk that is the top BM25 hit on a rare exact token (e.g. a part number)
is kept even if its cosine is low. If nothing survives the gate the runner abstains,
which is the agent's first defence against answering from irrelevant context.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .ingest import Chunk
from .llm import embed
from .textutil import STOPWORDS, extract_ids, stem, tokens


def _bm25_tokens(text: str) -> list[str]:
    out = []
    for tok in tokens(text):
        if tok in STOPWORDS:
            continue
        out.append(stem(tok))
        # also index the parts of compound IDs: "hx-2040" -> "hx", "2040"
        if re.search(r"[-_/.]", tok):
            out.extend(p for p in re.split(r"[-_/.]", tok) if p and p not in STOPWORDS)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.lens = np.array([len(d) for d in docs], dtype=np.float32)
        self.avg = float(self.lens.mean()) if len(docs) else 1.0
        self.tf = [Counter(d) for d in docs]
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.docs), dtype=np.float32)
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(t)
                if f:
                    out[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
        return out


@dataclass
class Hit:
    chunk: Chunk
    score: float     # fused score used for ranking
    dense: float     # cosine similarity (used for the min_score gate)
    bm25: float


class Index:
    """In-memory index over chunks. Embeddings are cached per chunk text in .cache/emb.sqlite."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.vectors = embed([c.embed_text for c in chunks]) if chunks else np.zeros((0, 384))
        self.bm25 = BM25([_bm25_tokens(c.embed_text) for c in chunks])
        self.id_sets = [extract_ids(c.embed_text) for c in chunks]   # for the exact-identifier boost

    def search(self, query: str, top_k: int = 5, mode: str = "hybrid", min_score: float = 0.0,
               extra_queries: list[str] | None = None) -> tuple[list[Hit], int]:
        """Return (hits, n_filtered). n_filtered = candidates dropped by the min_score gate."""
        if not self.chunks:
            return [], 0
        queries = [query] + [q for q in (extra_queries or []) if q and q != query]
        qvecs = embed(queries)
        dense = (self.vectors @ qvecs.T).max(axis=1)                     # best cosine over queries
        bm = np.max(np.vstack([self.bm25.scores(_bm25_tokens(q)) for q in queries]), axis=0)
        bm_top = float(bm.max()) if len(bm) else 0.0

        if mode == "dense":
            fused = dense.copy()
        elif mode == "bm25":
            fused = bm.copy()
        else:  # reciprocal rank fusion
            fused = np.zeros(len(self.chunks), dtype=np.float32)
            for scores in (dense, bm):
                order = np.argsort(-scores)
                ranks = np.empty_like(order)
                ranks[order] = np.arange(len(order))
                fused += np.where(scores > 0, 1.0 / (60 + ranks + 1), 0.0)

        # Exact-identifier boost: if the query names an ID (part number, form code) that a chunk
        # contains verbatim, that chunk goes to the top. Plain RRF weights dense and BM25 equally, so
        # semantically similar rows could outrank the one exact match (found by manual testing).
        query_ids = set().union(*(extract_ids(q) for q in queries))
        exact = np.zeros(len(self.chunks), dtype=bool)
        if query_ids and mode != "dense":
            exact = np.array([bool(query_ids & s) for s in self.id_sets])
            fused = fused + exact.astype(np.float32)

        order = np.argsort(-fused)
        hits: list[Hit] = []
        filtered = 0
        for i in order[: max(top_k * 4, 20)]:
            if fused[i] <= 0:
                continue
            strong_lexical = bool(exact[i]) or (bm_top > 0 and bm[i] >= 0.8 * bm_top
                                                and self._has_rare_exact_match(queries, i))
            if dense[i] < min_score and not strong_lexical:
                filtered += 1
                continue
            hits.append(Hit(self.chunks[i], float(fused[i]), float(dense[i]), float(bm[i])))
            if len(hits) >= top_k:
                break
        return hits, filtered

    def _has_rare_exact_match(self, queries: list[str], i: int) -> bool:
        """True if an ID-like or rare token from the query occurs verbatim in chunk i."""
        text = self.chunks[i].embed_text.lower()
        for q in queries:
            for tok in tokens(q):
                if re.search(r"\d", tok) and re.search(r"[a-z]", tok) and tok in text:
                    return True
        return False

    def max_similarity(self, query: str) -> tuple[float, Chunk | None]:
        if not self.chunks:
            return 0.0, None
        sims = self.vectors @ embed([query])[0]
        i = int(np.argmax(sims))
        return float(sims[i]), self.chunks[i]
