"""Generated eval cases must be dropped when their evidence does not check out."""
import forgeai.evalgen as E
from forgeai.ingest import Chunk, Doc
from forgeai.schemas import (AgentDefinition, Chunking, GenCaseOut, GenFact, OutputContract, PromptSpec,
                             Requirements, RetrievalConfig)

DOC = Doc("leave.md", "text", "Employees get 21 working days of annual leave. Sick leave is 12 days per year.")
CHUNK = Chunk("leave.md#0", "leave.md", DOC.text)


def _gen():
    req = Requirements(brief="b", agent_name="a", scope="s", audience="staff", tone="t",
                       must_answer_topics=["leave"], must_refuse_topics=[])
    d = AgentDefinition(name="a", created_from="r", system_prompt="p",
                        prompt_spec=PromptSpec(role="r", rules=[], refuse_topics=[], answer_style="s"),
                        chunking=Chunking(chunk_size=500, chunk_overlap=50), retrieval=RetrievalConfig(top_k=3),
                        output_contract=OutputContract(refusal_phrase="no"), documents_dir=".")
    return E.EvalGenerator(req, d, [DOC], [CHUNK], index=None)


def test_good_case_is_kept(monkeypatch):
    monkeypatch.setattr(E, "llm_json", lambda *a, **k: GenCaseOut(
        question="How much annual leave do I get?",
        facts=[GenFact(fact="21 working days", quote="Employees get 21 working days of annual leave.")]))
    case = _gen().gen_single(CHUNK, "answerable")
    assert case is not None and case.verified and case.expected_facts == ["21 working days"]


def test_fabricated_quote_is_dropped(monkeypatch):
    g = _gen()
    monkeypatch.setattr(E, "llm_json", lambda *a, **k: GenCaseOut(
        question="How much annual leave do I get?",
        facts=[GenFact(fact="25 working days", quote="Employees get 25 working days of annual leave.")]))
    assert g.gen_single(CHUNK, "answerable") is None
    assert "quote not found" in g.dropped[0]["reason"]


def test_fact_not_supported_by_quote_is_dropped(monkeypatch):
    g = _gen()
    monkeypatch.setattr(E, "llm_json", lambda *a, **k: GenCaseOut(
        question="How much sick leave do I get?",
        facts=[GenFact(fact="15 days of sick leave", quote="Sick leave is 12 days per year.")]))
    assert g.gen_single(CHUNK, "answerable") is None


def test_set_is_topped_up_to_the_minimum_when_a_type_stays_short(monkeypatch):
    """Multi-doc pairs that never verify must not leave the set below 20 cases."""
    g = _gen()
    made = iter(range(1000))
    monkeypatch.setattr(g, "_pairs", lambda n: [(CHUNK, CHUNK)] * n)
    monkeypatch.setattr(g, "gen_multi", lambda a, b: None)                      # every pair fails
    monkeypatch.setattr(g, "_round_robin", lambda n: [CHUNK] * n)
    monkeypatch.setattr(g, "gen_single", lambda ch, kind, style=None: E.EvalCase(
        id="x", type=kind, question=f"q{next(made)}", verified=True))
    monkeypatch.setattr(g, "gen_out_of_scope", lambda n: [E.EvalCase(
        id="x", type="out_of_scope", question=f"o{next(made)}", should_refuse=True) for _ in range(n)])
    result = g.generate(20)
    assert len(result.cases) >= 20
    assert not any(c.type == "edge_multi_doc" for c in result.cases)
    assert any("topped up" in n for n in result.notes)


def test_question_that_leaks_the_answer_is_dropped(monkeypatch):
    g = _gen()
    monkeypatch.setattr(E, "llm_json", lambda *a, **k: GenCaseOut(
        question="Is it true that sick leave is 12 days per year?",
        facts=[GenFact(fact="12 days per year", quote="Sick leave is 12 days per year.")]))
    assert g.gen_single(CHUNK, "answerable") is None
    assert "leaks" in g.dropped[0]["reason"]
