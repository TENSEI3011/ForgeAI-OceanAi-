"""Stretch goal: prompt tournament.

The generator proposes 3 candidate system prompts (the standard draft plus a conservative and a
helpful variant). Each candidate is evaluated on the DEV split only (holdout stays untouched) and the
eval set picks the winner. Selection is pointwise by the eval set, not by an LLM comparing two prompts,
so there is no position bias to defend against. Ties are broken by fewer hallucinations, then fewer
wrong refusals, then the shorter prompt.
"""
from __future__ import annotations

from typing import Any

from rich.console import Console

from .generator import _clean_rules, render_system_prompt
from .ingest import Doc
from .intake import docs_overview
from .judge import evaluate
from .llm import LLMJSONError, llm_json, render
from .schemas import AgentDefinition, EvalCase, PromptDraftOut, Requirements

console = Console()

VARIANTS = {
    "conservative": "Variant style: CONSERVATIVE. Rules should favour precision: answer only what the documents "
                    "state explicitly, keep answers short, and decline when the documents are unclear.",
    "helpful": "Variant style: HELPFUL. Rules should favour completeness: cover every part of the question the "
               "documents support, include all relevant conditions, limits and contacts, and combine documents "
               "when a question spans several.",
}


def run_tournament(req: Requirements, docs: list[Doc], base: AgentDefinition,
                   cases: list[EvalCase]) -> tuple[AgentDefinition, dict[str, Any]]:
    candidates: dict[str, AgentDefinition] = {"standard": base}
    overview = docs_overview(req.documents)
    for name, style in VARIANTS.items():
        prompt = render("generator_prompt", brief=req.brief, scope=req.scope, audience=req.audience, tone=req.tone,
                        topics=req.must_answer_topics, refuse=req.must_refuse_topics,
                        warnings=req.warnings or ["none"], docs=overview, tools=base.tools or ["none"])
        try:
            draft = llm_json(f"{prompt}\n\n{style}", PromptDraftOut, temperature=0.6)
        except LLMJSONError:
            continue
        cand = base.model_copy(deep=True)
        cand.prompt_spec.role = draft.role
        cand.prompt_spec.rules, _ = _clean_rules(draft.rules, docs)
        cand.prompt_spec.answer_style = draft.answer_style
        cand.output_contract.max_words = max(60, min(250, draft.max_words))
        cand.system_prompt = render_system_prompt(cand.prompt_spec, cand.output_contract, cand.tools)
        candidates[name] = cand

    dev = [c for c in cases if c.split == "dev"]
    rows = []
    for name, cand in candidates.items():
        console.print(f"[bold]Tournament[/] evaluating '{name}' on {len(dev)} dev cases")
        card, _ = evaluate(cand, dev, 0)
        cats = card.failures_by_category
        rows.append({"candidate": name, "dev_pass_rate": card.pass_rate, "passed": sum(r.passed for r in card.results),
                     "n": card.n_cases, "hallucination": cats.get("hallucination", 0),
                     "wrong_refusal": cats.get("wrong_refusal", 0), "prompt_chars": len(cand.system_prompt),
                     "rules": cand.prompt_spec.rules})
    rows.sort(key=lambda r: (-r["dev_pass_rate"], r["hallucination"], r["wrong_refusal"], r["prompt_chars"]))
    winner = rows[0]["candidate"]
    best = candidates[winner].model_copy(deep=True)
    best.config_rationale["system_prompt"] = (f"won the prompt tournament ({rows[0]['passed']}/{rows[0]['n']} dev cases) "
                                              f"against {', '.join(r['candidate'] for r in rows[1:])}")
    return best, {"winner": winner, "rows": rows, "candidates": {k: v.model_dump() for k, v in candidates.items()}}


def tournament_markdown(result: dict[str, Any]) -> str:
    lines = ["## Prompt tournament (stretch goal)", "",
             "Three candidate system prompts were evaluated on the dev split; the eval set picked the winner "
             "(holdout cases were not used). Ties: fewer hallucinations, then fewer wrong refusals, then shorter.", "",
             "| Candidate | Dev pass | Hallucinations | Wrong refusals | Prompt chars | Winner |", "|---|---|---|---|---|---|"]
    for r in result["rows"]:
        lines.append(f"| {r['candidate']} | {r['passed']}/{r['n']} ({r['dev_pass_rate']:.0%}) | {r['hallucination']} | "
                     f"{r['wrong_refusal']} | {r['prompt_chars']} | {'**yes**' if r['candidate'] == result['winner'] else ''} |")
    return "\n".join(lines)
