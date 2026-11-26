"""Two bugs found by a live test of the hosted app on an unseen brief."""
import pytest

import forgeai.llm as L
from forgeai.ingest import Doc, row_to_text
from forgeai.intake import table_excerpt


def _rates_table() -> Doc:
    """Like the test CSV: the first 6 rows are all Deck ranks, Engine and Catering come later."""
    depts = ["Deck"] * 6 + ["Engine"] * 6 + ["Catering"] * 2
    rows = [{"rank_code": f"R-{i:02d}", "department": d, "basic_hourly_usd": f"{10 + i}.00"}
            for i, d in enumerate(depts, 1)]
    return Doc("rates.csv", "table", "\n".join(row_to_text(r) for r in rows),
               columns=["rank_code", "department", "basic_hourly_usd"], rows=rows)


def test_table_excerpt_shows_every_category_not_just_the_first_rows():
    ex = table_excerpt(_rates_table())
    assert "department: Deck, Engine, Catering" in ex       # complete, from all 14 rows
    assert "R-14" in ex and "R-01" in ex                    # samples span the whole table
    assert "rank_code:" not in ex.split("sample rows")[0]   # unique-per-row columns are not "categories"


class _Resp:
    def __init__(self, status: int, text: str = "", content: str = ""):
        self.status_code, self.text, self.headers, self._content = status, text, {}, content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}], "usage": {}}


DAILY = ('{"error":{"message":"Rate limit reached for model `qwen/qwen3.8-27b` on tokens per day (TPD): '
         'Limit 200000, Used 199642, Requested 907. Please try again in 3m57.168s."}}')


@pytest.fixture
def groq(monkeypatch):
    monkeypatch.setattr(L.SETTINGS, "groq_key", "test-key")
    monkeypatch.setattr(L, "_GROQ_EXHAUSTED", {})
    monkeypatch.setattr(L, "_GROQ_FALLBACK_NOTED", set())
    monkeypatch.setattr(L.time, "sleep", lambda s: pytest.fail("must not wait on a daily quota"))
    calls = []

    def use(responses):
        def post(url, json=None, **kw):
            calls.append(json["model"])
            return responses[json["model"]]
        monkeypatch.setattr(L.requests, "post", post)
        return calls
    return use


def test_daily_quota_switches_to_the_next_model_without_waiting(groq):
    calls = groq({"qwen/qwen3.8-27b": _Resp(429, DAILY), "openai/gpt-oss-120b": _Resp(200, content="77 hours")})
    text, _, _ = L._groq_chat([{"role": "user", "content": "q"}], "qwen/qwen3.8-27b", 0.0, 100, None)
    assert text == "77 hours" and calls == ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]
    assert any("daily quota for qwen/qwen3.8-27b" in w for w in L.STATS.warnings)
    # the exhausted model is remembered: the next call goes straight to the fallback
    L._groq_chat([{"role": "user", "content": "q"}], "qwen/qwen3.8-27b", 0.0, 100, None)
    assert calls[-1] == "openai/gpt-oss-120b" and calls.count("qwen/qwen3.8-27b") == 1


def test_every_model_out_of_quota_raises_a_clear_quota_error(groq):
    groq({m: _Resp(429, DAILY) for m in ["qwen/qwen3.8-27b", *L.GROQ_FALLBACK_MODELS]})
    with pytest.raises(L.LLMQuotaError):
        L._groq_chat([{"role": "user", "content": "q"}], "qwen/qwen3.8-27b", 0.0, 100, None)
