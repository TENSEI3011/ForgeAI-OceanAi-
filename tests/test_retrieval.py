"""Retrieval: an exact identifier in the query must win over semantically similar chunks."""
import numpy as np

import forgeai.retrieval as R
from forgeai.ingest import Chunk
from forgeai.llm import _hashed_vector


def _fake_embed(texts):
    m = np.vstack([_hashed_vector(t) for t in texts])
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1
    return m / n


def test_exact_id_match_is_ranked_first(monkeypatch):
    monkeypatch.setattr(R, "embed", _fake_embed)
    rows = [f"part_no: ME-10{i:02d} | description: main engine part {i} | unit_price_usd: {100 + i} | stock: {i}"
            for i in range(40)]
    chunks = [Chunk(f"cat.csv#{i}", "cat.csv", t, row=i) for i, t in enumerate(rows)]
    index = R.Index(chunks)
    hits, _ = index.search("What is the unit price and stock of part ME-1027?", top_k=5, mode="hybrid", min_score=0.9)
    assert hits and hits[0].chunk.text.startswith("part_no: ME-1027")   # boosted AND passes a strict gate
