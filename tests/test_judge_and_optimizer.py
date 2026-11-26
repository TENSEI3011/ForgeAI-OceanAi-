"""Judge deterministic checks, failure classification, optimizer rollback and the leak guard."""
from pathlib import Path

import forgeai.optimizer as O
from forgeai.judge import classify, deterministic, make_scorecard
from forgeai.schemas import (AgentAnswer, AgentDefinition, Chunking, EvalCase, OutputContract, PromptSpec,
                             RetrievalConfig, RetrievedChunk)

REFUSAL = "I'm sorry, I can't answer that from the documents I have access to."


def _definition() -> AgentDefinition:
    return AgentDefinition(name="t", created_from="r", system_prompt="p",
                           prompt_spec=PromptSpec(role="r", rules=["be brief"], refuse_topics=["tax"], answer_style="s"),
                           chunking=Chunking(chunk_size=800, chunk_overlap=100), retrieval=RetrievalConfig(top_k=5),
                           output_contract=OutputContract(refusal_phrase=REFUSAL), documents_dir=".")


CTX = [RetrievedChunk(chunk_id="leave.pdf#1", source="leave.pdf", text="Staff get 21 working days of annual leave.",
                      score=0.5, dense=0.6)]
CASE = EvalCase(id="A01", type="answerable", question="How much annual leave?", expected_sources=["leave.pdf"],
                expected_facts=["21 working days"])
OOS = EvalCase(id="O01", type="out_of_scope", question="What is my tax bracket?", should_refuse=True)


def _ans(text: str, cited=None, retrieved=CTX, refused=False) -> AgentAnswer:
    return AgentAnswer(question="q", answer=text, cited_sources=cited or [], retrieved=retrieved, refused=refused)


def test_correct_grounded_cited_answer_passes():
    r = deterministic(CASE, _ans("You get 21 working days [source: leave.pdf].", ["leave.pdf"]), _definition())
    assert r.passed and r.grounded and r.citation_ok


def test_novel_number_is_hallucination():
    a = _ans("You get 21 working days, plus 7 bonus days [source: leave.pdf].", ["leave.pdf"])
    r = deterministic(CASE, a, _definition())
    assert not r.passed and r.novel_numbers == ["7"]
    assert classify(CASE, a, r)[0] == "hallucination"


def test_missing_citation_is_prompt_defect():
    a = _ans("You get 21 working days.")
    r = deterministic(CASE, a, _definition())
    assert not r.passed and not r.citation_ok
    assert classify(CASE, a, r)[0] == "prompt_defect"


def test_refusal_checks_both_directions():
    assert deterministic(OOS, _ans(REFUSAL, refused=True), _definition()).passed
    over = _ans("Your tax bracket is 30%.")
    r = deterministic(OOS, over, _definition())
    assert not r.passed and classify(OOS, over, r)[0] == "wrong_refusal"
    under = _ans(REFUSAL, refused=True)
    r2 = deterministic(CASE, under, _definition())
    assert not r2.passed and classify(CASE, under, r2)[0] == "wrong_refusal"   # context had the fact
    miss = _ans(REFUSAL, retrieved=[], refused=True)
    r3 = deterministic(CASE, miss, _definition())
    assert classify(CASE, miss, r3)[0] == "retrieval_miss"


def test_optimizer_rolls_back_a_regression(monkeypatch, tmp_path: Path):
    d = _definition()
    miss = _ans(REFUSAL, retrieved=[], refused=True)
    miss.abstained_no_context = True
    bad = deterministic(CASE, miss, d)
    bad.failure_category, bad.diagnosis = classify(CASE, miss, bad)
    good_oos = deterministic(OOS, _ans(REFUSAL, refused=True), d)
    base = make_scorecard(0, 1, [bad, good_oos])          # 50%
    worse = make_scorecard(1, 2, [bad, deterministic(OOS, _ans("It is 30%."), d)])   # 0%
    monkeypatch.setattr(O, "evaluate", lambda definition, cases, it: (worse, [miss, miss]))
    opt = O.Optimizer([CASE, OOS], tmp_path)
    best, cards, records, reason = opt.run(d, base, [miss, _ans(REFUSAL, refused=True)], max_iters=1,
                                           save_definition=lambda x: None, save_results=lambda *a: None)
    assert records[0].decision == "reverted: regression"
    assert best.version == 1 and best.retrieval.top_k == 5          # original definition kept
    assert records[0].changes[0].category == "retrieval_miss"        # targeted fix, not regeneration


def test_citing_a_called_tool_is_not_fabrication():
    from forgeai.schemas import ToolCall
    a = _ans("You get 21 working days [source: leave.pdf]. Total 42 [source: calculator result].",
             ["leave.pdf", "tool:calculator"])
    a.tools_called = [ToolCall(name="calculator", args={"expression": "21*2"}, result="21*2 = 42")]
    r = deterministic(CASE, a, _definition())
    assert r.citation_ok and r.grounded and r.passed


def test_veto_needs_a_concrete_novel_specific():
    from forgeai.judge import _novel_specifics
    ctx = "Staff get 21 working days of annual leave. Approval by the line manager."
    assert not _novel_specifics("There is no combined rule for this.", ctx)          # negative claim
    assert not _novel_specifics("Note: These parts are categorized under", ctx)      # vague fragment
    assert _novel_specifics("Leave must be approved by the Chief Executive.", ctx)  # invented authority
    assert _novel_specifics("You get 25 days.", ctx)                                 # invented number


def test_leak_guard_rejects_rules_containing_answers(tmp_path: Path):
    opt = O.Optimizer([CASE, OOS], tmp_path)
    assert opt._leaks("Always say staff get 21 working days of leave.")
    assert opt._leaks("Answer from your general knowledge when unsure.")
    assert opt._leaks("When asked about leave, quote the number of days and the policy section.") is None
