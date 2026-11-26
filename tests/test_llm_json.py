"""llm_json must repair invalid model output by feeding the validation error back."""
import pytest
from pydantic import BaseModel

import forgeai.llm as L


class Out(BaseModel):
    name: str
    count: int


def test_bad_then_good_response_is_repaired(monkeypatch):
    replies = iter(['Sure! here you go: {"name": "x", "count": "many"}',   # invalid int
                    '```json\n{"name": "x", "count": 3}\n```'])
    prompts = []

    def fake_llm(prompt, **kw):
        prompts.append(prompt)
        return next(replies)

    monkeypatch.setattr(L, "llm", fake_llm)
    out = L.llm_json("give me json", Out)
    assert out == Out(name="x", count=3)
    assert len(prompts) == 2
    assert "could not be used" in prompts[1] and "count" in prompts[1]   # error was fed back


def test_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(L, "llm", lambda prompt, **kw: "no json here")
    with pytest.raises(L.LLMJSONError):
        L.llm_json("x", Out, retries=3)


def test_extract_json_handles_think_blocks_and_chatter():
    raw = "<think>hmm {not this}</think> Answer: {\"name\": \"a\", \"count\": 1} thanks"
    assert L.extract_json(raw) == '{"name": "a", "count": 1}'


def test_render_fills_placeholders_and_rejects_missing():
    text = L.render("runner_query_rewrite", question="how many days leave")
    assert "how many days leave" in text
    with pytest.raises(KeyError):
        L.render("runner_query_rewrite")
