"""Requirement 5: the judge, plus the failure classifier the optimizer relies on.

PRIMARY: deterministic checks (cheap, objective, reproducible)
  fact recall    share of expected facts found in the answer (numbers/IDs must match exactly)
  citations      at least one expected source cited; no citation to a file that was not retrieved
  refusal        refused iff the case should be refused
  grounding      every number/ID in the answer must appear in the retrieved context, the tool
                 results or the question (novel numbers = likely hallucination)
  length         word count vs the contract (tracked separately, never rewarded)

SECONDARY: LLM judge, defended against its known failure modes
  position bias        pointwise scoring against reference facts; never "A vs B"
  self-preference      runs on JUDGE_MODEL (a different model family when available); the answer
                       is shown with citations/markdown stripped so it is not recognisable by style
  verbosity bias       binary questions about facts only; the rubric says length is irrelevant;
                       length is measured deterministically instead
  unfounded verdicts   every verdict must quote evidence; quotes are verified and an unverified
                       verdict is discarded
  Authority: the judge may VETO a deterministic pass (e.g. a wrong claim with no numbers) but can
  never rescue a deterministic fail. Every disagreement is logged for the report.
"""
from __future__ import annotations

import re
from typing import Any

from rich.console import Console
from rich.progress import track

from .llm import SETTINGS, LLMJSONError, llm_json, render, stage
from .runner import AgentRunner
from .schemas import AgentAnswer, AgentDefinition, CaseResult, EvalCase, JudgeOut, Scorecard
from .textutil import contains_quote, extract_ids, extract_numbers, fact_recall, truncate, word_count

console = Console()

FACT_PASS = 0.6            # share of expected facts an answer must contain
IGNORED_NUMBERS = {"0", "1", "2", "3"}   # counting words ("2 options") are not treated as claims


def _strip_for_checks(answer: str) -> str:
    text = re.sub(r"\[\s*sources?\s*:[^\]]*\]", " ", answer, flags=re.I)
    text = re.sub(r"(?m)^\s*(\d+[.)]|[-*])\s+", " ", text)     # list markers
    return text


def _strip_style(answer: str) -> str:
    """Remove citations and markdown so the judge sees content, not style."""
    text = _strip_for_checks(answer)
    text = re.sub(r"[*_#>`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _novel_specifics(claim: str, ctx: str) -> set[str]:
    """Numbers, IDs and capitalised names (not sentence-initial) in `claim` that `ctx` never mentions."""
    ctx_low = ctx.lower()
    specifics = set(extract_numbers(claim)) - extract_numbers(ctx)
    specifics |= {i for i in extract_ids(claim) if i not in ctx_low}
    sentence_start = True
    for tok in re.findall(r"[A-Za-z]{2,}|[.!?:;]", claim):
        if tok in ".!?:;":
            sentence_start = True
            continue
        if not sentence_start and tok[0].isupper() and len(tok) >= 3 and tok.lower() not in ctx_low:
            specifics.add(tok)
        sentence_start = False
    return specifics


def context_text(ans: AgentAnswer) -> str:
    parts = [c.text for c in ans.retrieved] + [f"{t.name} result: {t.result}" for t in ans.tools_called if t.ok]
    return "\n".join(parts)


# ------------------------------------------------------------------ deterministic layer
def deterministic(case: EvalCase, ans: AgentAnswer, d: AgentDefinition) -> CaseResult:
    ctx = context_text(ans)
    retrieved_sources = list(dict.fromkeys(c.source for c in ans.retrieved))
    body = _strip_for_checks(ans.answer)
    wc = word_count(ans.answer)
    allowed_nums = extract_numbers(ctx) | extract_numbers(case.question) | IGNORED_NUMBERS
    novel = sorted((extract_numbers(body) - allowed_nums)
                   | {i.upper() for i in extract_ids(body) - extract_ids(ctx) - extract_ids(case.question)})
    if ans.refused:
        novel = []
    base: dict[str, Any] = dict(
        case_id=case.id, type=case.type, split=case.split, question=case.question, answer=ans.answer,
        retrieved_sources=retrieved_sources, cited_sources=ans.cited_sources,
        tools_called=[t.name for t in ans.tools_called], refused=ans.refused, should_refuse=case.should_refuse,
        refused_correctly=(ans.refused == case.should_refuse), novel_numbers=novel, word_count=wc,
        over_length=wc > d.output_contract.max_words * 1.25, latency_s=ans.latency_s)

    if case.should_refuse:
        return CaseResult(**base, grounded=not novel, correct=ans.refused, citation_ok=True,
                          fact_recall=1.0 if ans.refused else 0.0, passed=ans.refused,
                          judge_notes="refused as required" if ans.refused else "answered a question it should refuse")

    recall, missing = fact_recall(case.expected_facts, body)
    ctx_recall, _ = fact_recall(case.expected_facts, ctx)
    called_tools = {f"tool:{t.name}" for t in ans.tools_called if t.ok}
    cited = ans.cited_sources
    fabricated = [c for c in cited if c not in retrieved_sources and c not in called_tools]
    if d.output_contract.require_citations:
        citation_ok = bool(cited) and any(c in case.expected_sources for c in cited) and not fabricated
    else:
        citation_ok = not fabricated
    correct = (not ans.refused) and recall >= FACT_PASS
    grounded = not novel
    notes = []
    if ans.refused:
        notes.append("refused an answerable question")
    if missing:
        notes.append(f"missing facts: {missing}")
    if novel:
        notes.append(f"numbers/IDs not in context: {novel}")
    if not citation_ok:
        notes.append(f"citation problem (cited {cited or 'nothing'}, expected {case.expected_sources}"
                     + (f", fabricated {fabricated}" if fabricated else "") + ")")
    return CaseResult(**base, grounded=grounded, correct=correct, citation_ok=citation_ok,
                      fact_recall=round(recall, 2), missing_facts=missing, context_fact_recall=round(ctx_recall, 2),
                      passed=correct and grounded and citation_ok, judge_notes="; ".join(notes))


# ------------------------------------------------------------------ LLM judge layer
def llm_judge(case: EvalCase, ans: AgentAnswer, r: CaseResult) -> None:
    """Mutates r: adds the judge verdict, veto and disagreement note."""
    ctx = context_text(ans)
    prompt = render("judge_rubric", question=case.question,
                    reference="\n".join(f"- {f}" for f in case.expected_facts) or "(none)",
                    context=truncate(ctx, 6000) or "(empty)", answer=truncate(_strip_style(ans.answer), 2500))
    try:
        v = llm_json(prompt, JudgeOut, temperature=0.0, model=SETTINGS.judge_model, max_tokens=500)
    except LLMJSONError as exc:
        r.judge = {"error": str(exc)[:200]}
        return
    answer_plain = _strip_style(ans.answer)
    evidence_ok = bool(v.evidence_quote) and contains_quote(v.evidence_quote, ctx, 85)
    contradiction_ok = bool(v.contradiction_quote) and contains_quote(v.contradiction_quote, answer_plain, 85)
    claim = v.unsupported_claim.strip()
    # A claim only counts if it is really in the answer, not in the context, AND contains a concrete
    # specific (number, code or capitalised name) that the context lacks. Vague fragments and negative
    # statements ("there is no X") cannot veto: a 3B judge flags those far too often.
    claim_ok = (bool(claim) and contains_quote(claim, answer_plain, 85) and not contains_quote(claim, ctx, 85)
                and bool(_novel_specifics(claim, ctx)))
    judge_pass = v.answers_question and v.supported_by_context and not v.contradicts_reference and not claim
    verdict = v.model_dump() | {"evidence_verified": evidence_ok, "contradiction_verified": contradiction_ok,
                                "unsupported_claim_verified": claim_ok, "judge_pass": judge_pass}
    discarded = v.supported_by_context and not evidence_ok
    if discarded:
        verdict["discarded"] = "claimed support without a verifiable (verbatim) evidence quote"
        r.judge_notes = (r.judge_notes + "; " if r.judge_notes else "") + "judge verdict discarded (unverifiable quote)"
    r.judge = verdict

    veto_reason = ""
    if v.contradicts_reference and contradiction_ok:
        veto_reason = f"contradicts the reference: '{truncate(v.contradiction_quote, 120)}'"
    elif claim_ok:
        veto_reason = f"unsupported claim: '{truncate(claim, 120)}'"
    if r.passed and veto_reason:
        r.judge_veto = True
        r.passed = False
        r.judge_disagreement = f"judge vetoed a deterministic pass ({veto_reason})"
    elif discarded:
        pass   # an unverifiable verdict carries no weight either way
    elif not r.passed and judge_pass and not ans.refused:
        r.judge_disagreement = ("deterministic checks failed but the judge found the answer correct and supported "
                                "(possible fact-matching false negative, or an over-specific expected fact; NOT rescued)")
    elif r.passed and not judge_pass:
        r.judge_disagreement = "judge said fail but gave no verifiable quote for it (ignored)"


# ------------------------------------------------------------------ failure taxonomy (critic)
def classify(case: EvalCase, ans: AgentAnswer, r: CaseResult) -> tuple[str, str]:
    """Rules first; the LLM judge's verified verdict only breaks the hallucination/prompt tie."""
    expected_hit = all(s in r.retrieved_sources for s in case.expected_sources) if case.expected_sources else True
    if case.should_refuse:
        return "wrong_refusal", "over-answering: answered an out-of-scope question instead of refusing"
    if r.refused:
        if ans.abstained_no_context:
            return "retrieval_miss", "nothing passed the min_score gate, so the agent abstained"
        if not expected_hit or r.context_fact_recall < 0.5:
            return "retrieval_miss", (f"refused; the needed passage was not retrieved (expected {case.expected_sources}, "
                                      f"retrieved {r.retrieved_sources}, context fact recall {r.context_fact_recall})")
        return "wrong_refusal", f"refused although the context held the answer (context fact recall {r.context_fact_recall})"
    if r.novel_numbers:
        return "hallucination", f"answer contains numbers/IDs absent from the context: {r.novel_numbers}"
    if r.judge_veto:
        return "hallucination", r.judge_disagreement
    if not expected_hit or r.context_fact_recall < 0.5:
        return "retrieval_miss", (f"key facts were not in the retrieved context (context fact recall "
                                  f"{r.context_fact_recall}; expected {case.expected_sources}, retrieved {r.retrieved_sources})")
    j = r.judge or {}
    if j.get("contradiction_verified") or j.get("unsupported_claim_verified"):
        return "hallucination", "judge (verified) found a claim not supported by the context"
    reasons = []
    if not r.correct:
        reasons.append(f"context had the facts but the answer missed {r.missing_facts}")
    if not r.citation_ok:
        reasons.append("citation contract not followed")
    return "prompt_defect", "; ".join(reasons) or "answer did not meet the contract"


# ------------------------------------------------------------------ evaluation driver
def run_agent(definition: AgentDefinition, cases: list[EvalCase]) -> list[AgentAnswer]:
    runner = AgentRunner(definition)
    out = []
    with stage("agent_under_test"):
        for c in track(cases, description=f"  running agent v{definition.version}", console=console):
            out.append(runner.answer(c.question))
    return out


def judge_answers(definition: AgentDefinition, cases: list[EvalCase], answers: list[AgentAnswer]) -> list[CaseResult]:
    results = [deterministic(c, a, definition) for c, a in zip(cases, answers)]
    with stage("judge"):
        for c, a, r in track(list(zip(cases, answers, results)), description="  judging", console=console):
            if not c.should_refuse and not a.refused:   # nothing for an LLM to judge in a refusal
                llm_judge(c, a, r)
    for c, a, r in zip(cases, answers, results):
        if not r.passed:
            r.failure_category, r.diagnosis = classify(c, a, r)   # type: ignore[assignment]
    return results


def _rate(xs: list[bool]) -> float:
    return round(sum(xs) / len(xs), 3) if xs else 1.0


def make_scorecard(iteration: int, version: int, results: list[CaseResult]) -> Scorecard:
    answered = [r for r in results if not r.refused]
    answerable = [r for r in results if not r.should_refuse]
    cats: dict[str, int] = {}
    for r in results:
        if r.failure_category:
            cats[r.failure_category] = cats.get(r.failure_category, 0) + 1
    by_type: dict[str, str] = {}
    for t in ("answerable", "edge_ambiguous", "edge_multi_doc", "out_of_scope"):
        rs = [r for r in results if r.type == t]
        if rs:
            by_type[t] = f"{sum(r.passed for r in rs)}/{len(rs)}"
    return Scorecard(
        iteration=iteration, definition_version=version, n_cases=len(results),
        pass_rate=_rate([r.passed for r in results]),
        dev_pass_rate=_rate([r.passed for r in results if r.split == "dev"]),
        holdout_pass_rate=_rate([r.passed for r in results if r.split == "holdout"]),
        grounded_rate=_rate([r.grounded for r in answered]),
        correct_rate=_rate([r.correct for r in answerable]),
        refusal_accuracy=_rate([bool(r.refused_correctly) for r in results]),
        citation_rate=_rate([r.citation_ok for r in answerable if not r.refused]),
        over_length_rate=_rate([r.over_length for r in answered]),
        failures_by_category=cats, pass_by_type=by_type,
        avg_latency_s=round(sum(r.latency_s for r in results) / max(1, len(results)), 2),
        judge_vetoes=sum(r.judge_veto for r in results),
        judge_disagreements=sum(bool(r.judge_disagreement) for r in results),
        results=results)


def evaluate(definition: AgentDefinition, cases: list[EvalCase], iteration: int) -> tuple[Scorecard, list[AgentAnswer]]:
    answers = run_agent(definition, cases)
    results = judge_answers(definition, cases, answers)
    return make_scorecard(iteration, definition.version, results), answers
