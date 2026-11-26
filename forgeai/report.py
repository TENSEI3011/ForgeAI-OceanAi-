"""Requirement 7: honest reporting.

scorecard.json / scorecard.md   per-iteration metrics (all, dev, holdout), failures by category
REPORT.md                       what was built, how it was tested, what improved, and - most
                                importantly - what still fails and why, with the raw evidence
                                (question, answer, retrieved sources) attached to every claim.

Numbers in the report are computed from the result files; nothing is typed in by hand.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .llm import LLMJSONError, SETTINGS, get_stats, llm_json, render, stage
from .schemas import (AgentAnswer, AgentDefinition, EvalCase, IterationRecord, Requirements, RootCauseOut,
                      Scorecard)
from .textutil import truncate

CATS = ["retrieval_miss", "prompt_defect", "hallucination", "wrong_refusal"]


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def scorecard_table(cards: list[Scorecard], records: list[IterationRecord]) -> str:
    decision = {r.iteration: r.decision for r in records}
    head = ("| Iter | Def | Pass (all) | Dev | Holdout | Correct | Grounded | Refusal acc. | Citations | "
            + " | ".join(CATS) + " | Avg latency | Decision |")
    lines = [head, "|" + "|".join(["---"] * (head.count("|") - 1)) + "|"]
    for c in cards:
        n_pass = sum(r.passed for r in c.results)
        cats = " | ".join(str(c.failures_by_category.get(k, 0)) for k in CATS)
        lines.append(f"| {c.iteration} | v{c.definition_version} | {n_pass}/{c.n_cases} ({_pct(c.pass_rate)}) | "
                     f"{_pct(c.dev_pass_rate)} | {_pct(c.holdout_pass_rate)} | {_pct(c.correct_rate)} | "
                     f"{_pct(c.grounded_rate)} | {_pct(c.refusal_accuracy)} | {_pct(c.citation_rate)} | {cats} | "
                     f"{c.avg_latency_s:.1f}s | {decision.get(c.iteration, 'baseline')} |")
    return "\n".join(lines)


def write_scorecards(cards: list[Scorecard], records: list[IterationRecord], out_dir: Path) -> None:
    summary = [c.model_dump(exclude={"results"}) for c in cards]
    (out_dir / "scorecard.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md = ["# Scorecard", "", scorecard_table(cards, records), "",
          "Pass (all) counts every case; the optimizer only saw **dev** failures, **holdout** cases were never used "
          "to choose fixes. Correct = expected-fact recall >= 60% on answerable cases. Grounded = no numbers/IDs "
          "outside the retrieved context. Columns per category count failing cases.", ""]
    for c in cards:
        md.append(f"- iteration {c.iteration}: by type {c.pass_by_type}; judge vetoes {c.judge_vetoes}; "
                  f"judge/deterministic disagreements {c.judge_disagreements}; over-length answers {_pct(c.over_length_rate)}")
    (out_dir / "scorecard.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def root_causes(final: Scorecard, cases: dict[str, EvalCase], answers: dict[str, AgentAnswer]) -> dict[str, str]:
    out: dict[str, str] = {}
    with stage("report"):
        for r in [x for x in final.results if not x.passed][:14]:
            c, a = cases[r.case_id], answers[r.case_id]
            ctx = "\n".join(f"({x.source}) {truncate(x.text, 300)}" for x in a.retrieved[:4]) or "(nothing retrieved)"
            try:
                out[r.case_id] = llm_json(render(
                    "report_root_cause", question=c.question, expected=c.expected_facts or "(should be refused)",
                    sources=c.expected_sources or "-", answer=truncate(a.answer, 600), context=ctx,
                    category=r.failure_category or "-", diagnosis=r.diagnosis), RootCauseOut,
                    temperature=0.1, max_tokens=300).explanation
            except LLMJSONError:
                out[r.case_id] = "(explanation unavailable)"
    return out


def write_report(out_dir: Path, req: Requirements, definition: AgentDefinition, tool_log: list[dict[str, Any]],
                 cases: list[EvalCase], evalgen_log: dict[str, Any], cards: list[Scorecard],
                 records: list[IterationRecord], stop_reason: str, final_answers: list[AgentAnswer],
                 extra_sections: list[str] | None = None) -> None:
    final = next(c for c in reversed(cards) if c.definition_version == definition.version)
    base = cards[0]
    by_id = {c.id: c for c in cases}
    ans_by_id = {c.id: a for c, a in zip(cases, final_answers)}
    explanations = root_causes(final, by_id, ans_by_id)
    stats = get_stats().to_dict()
    n_pass = sum(r.passed for r in final.results)
    hold = [r for r in final.results if r.split == "holdout"]

    L: list[str] = [f"# ForgeAI report: {definition.name}", ""]
    L += [f"> **Final result: {n_pass}/{final.n_cases} eval cases pass ({_pct(final.pass_rate)})** with agent "
          f"definition v{definition.version}. Baseline v1 was {sum(r.passed for r in base.results)}/{base.n_cases} "
          f"({_pct(base.pass_rate)}). Held-out cases (never used for fixing): {sum(r.passed for r in hold)}/{len(hold)} "
          f"({_pct(final.holdout_pass_rate)}).", ">",
          f"> Generator model `{stats['model']}`, judge model `{stats['judge_model']}`, embeddings `{stats['embed_model']}`"
          f" ({stats['backend']}). {stats['total_calls']} LLM calls, {stats['total_tokens']:,} tokens, "
          f"{stats['wall_seconds'] / 60:.1f} min wall time.", ""]

    L += ["## 1. Brief and requirements", "", f"**Brief:** {req.brief}", "",
          f"- **Scope:** {req.scope}", f"- **Audience:** {req.audience}", f"- **Tone:** {req.tone}",
          f"- **Must answer:** {', '.join(req.must_answer_topics)}",
          f"- **Must refuse:** {', '.join(req.must_refuse_topics)}", "",
          "Clarifying questions asked (max 5):", ""]
    L += [f"{i}. {qa.question} -> _{qa.answer}_ ({qa.answered_by})" for i, qa in enumerate(req.clarifying_qa, 1)]
    L += ["", "## 2. Groundability guard", ""]
    if req.warnings:
        L += ["**Warnings raised before generation:**", ""] + [f"- ⚠ {w}" for w in req.warnings] + [""]
    else:
        L += ["No topic was flagged: every requested topic has verified supporting evidence in the documents.", ""]
    L += ["| Topic | Status | LLM said | Similarity | Evidence / note |", "|---|---|---|---|---|"]
    for g in req.groundability:
        ev = f"\"{truncate(g.evidence[0].snippet, 90)}\" ({g.evidence[0].source})" if g.evidence else truncate(g.note, 120)
        L.append(f"| {g.topic} | **{g.status}** | {g.llm_status} | {g.top_similarity:.2f} | {ev.replace('|', '/')} |")

    L += ["", "## 3. Generated agent", "",
          f"- Retrieval: {definition.retrieval.mode}, top_k={definition.retrieval.top_k}, "
          f"min_score={definition.retrieval.min_score}, query_rewrite={definition.retrieval.query_rewrite}; "
          f"chunks {definition.chunking.chunk_size} chars / overlap {definition.chunking.chunk_overlap}",
          f"- Output contract: citations required={definition.output_contract.require_citations}, max "
          f"{definition.output_contract.max_words} words, refusal phrase \"{definition.output_contract.refusal_phrase}\"",
          f"- Temperature: {definition.llm.temperature}", "", "**Tool decisions** (attached only with a verified quote "
          "from the requester's words AND agreement from a skeptical second pass):", ""]
    for t in tool_log:
        L.append(f"- `{t['tool']}`: {'**attached**' if t['attached'] else 'not attached'} - {t['reason']}")
    L += ["", f"Full system prompt and config: `agent_definition_final.json` (v{definition.version}).", ""]

    by_type = evalgen_log.get("by_type", {})
    L += ["## 4. Eval set (generated, then verified)", "",
          f"{len(cases)} cases: " + ", ".join(f"{k} {v}" for k, v in by_type.items())
          + f". Split: {evalgen_log.get('by_split')}.",
          f"{evalgen_log.get('n_dropped', 0)} generated cases were **dropped by verification** "
          f"(out of {evalgen_log.get('generation_attempts', '?')} generation calls); reasons are in "
          "`evals_generation_log.json`."]
    reasons: dict[str, int] = {}
    for d in evalgen_log.get("dropped_cases", []):
        key = d["reason"].split(":")[0][:70]
        reasons[key] = reasons.get(key, 0) + 1
    L += [f"- {k}: {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])]
    L += [f"- note: {n}" for n in evalgen_log.get("notes", [])]

    L += ["", "## 5. Critic-optimizer iterations", "", scorecard_table(cards, records), "",
          f"**Stop reason:** {stop_reason}", ""]
    for r in records:
        L.append(f"- **Iteration {r.iteration}** ({', '.join(r.categories_targeted)}): "
                 + "; ".join(c.what for c in r.changes if c.category != "(rendered)")
                 + f". Dev {_pct(r.before_dev)} -> {_pct(r.after_dev)}, overall {_pct(r.before_score)} -> "
                   f"{_pct(r.after_score)}. Fixed: {', '.join(r.flipped_to_pass) or 'none'}; broke: "
                   f"{', '.join(r.flipped_to_fail) or 'none'}. **{r.decision}**.")
    L += ["", "Full diffs: `iteration_log.md`.", ""]

    L += ["## 6. Final results by case", "", "| Case | Type | Split | Pass | Category | Fact recall | Cited | Note |",
          "|---|---|---|---|---|---|---|---|"]
    for r in final.results:
        L.append(f"| {r.case_id} | {r.type} | {r.split} | {'✅' if r.passed else '❌'} | {r.failure_category or ''} | "
                 f"{'' if r.should_refuse else f'{r.fact_recall:.0%}'} | {', '.join(r.cited_sources) or '-'} | "
                 f"{truncate(r.judge_notes, 80).replace('|', '/')} |")

    fails = [r for r in final.results if not r.passed]
    L += ["", f"## 7. What still fails and why ({len(fails)} case(s))", ""]
    if not fails:
        L += ["Every case passes. Treat this with suspicion: with this eval-set size it may mean the cases are too "
              "easy rather than that the agent is perfect.", ""]
    cats: dict[str, int] = {}
    for r in fails:
        cats[r.failure_category or "?"] = cats.get(r.failure_category or "?", 0) + 1
    if cats:
        L += ["Remaining failures by category: " + ", ".join(f"{k} {v}" for k, v in cats.items()), ""]
    for r in fails:
        c = by_id[r.case_id]
        L += [f"### {r.case_id} ({r.type}, {r.split}) - {r.failure_category}", "",
              f"- **Question:** {c.question}",
              f"- **Expected:** {'refusal' if c.should_refuse else '; '.join(c.expected_facts)} "
              f"(sources: {', '.join(c.expected_sources) or '-'})",
              f"- **Agent answered:** {truncate(' '.join(r.answer.split()), 450)}",
              f"- **Retrieved:** {', '.join(r.retrieved_sources) or 'nothing'} | tools: {', '.join(r.tools_called) or 'none'}",
              f"- **Rule-based diagnosis:** {r.diagnosis}",
              f"- **Root cause (LLM explanation of the evidence above):** {explanations.get(r.case_id, '-')}", ""]

    dis = [r for r in final.results if r.judge_disagreement]
    L += ["## 8. Judge vs deterministic checks", "",
          "The deterministic checks decide pass/fail. The LLM judge can veto a pass but never rescue a fail. "
          "Disagreements are listed so a human can audit both:", ""]
    L += [f"- {r.case_id}: {r.judge_disagreement}" for r in dis] or ["- none in the final iteration"]

    L += ["", "## 9. Known limitations (read before trusting the numbers)", ""]
    per_case = 100 / max(1, final.n_cases)
    lim = [
        f"**Small eval set:** {final.n_cases} cases, so one case moves the pass rate by {per_case:.1f} points; "
        f"the holdout has only {len(hold)} cases. Differences of 1-2 cases between iterations are within noise.",
        "**Generated evals share blind spots with the generator:** cases come from the same documents and a "
        "small model; verification guarantees the expected facts are really in the documents, not that the "
        "questions are representative of real users.",
        "**Fact matching is lexical:** numbers/IDs must match exactly and words must overlap. A correct answer "
        "that paraphrases heavily can fail (see judge disagreements); a wrong answer that repeats the right "
        "words can pass if the judge misses it.",
        "**Numbers grounding:** novel numbers are flagged as hallucinations, which also flags correct mental "
        "arithmetic, and the counting numbers 0-3 are ignored.",
    ]
    if SETTINGS.judge_model == SETTINGS.model:
        lim.append("**Self-preference risk:** the judge used the same model as the agent (no JUDGE_MODEL set).")
    else:
        lim.append(f"**Judge noise:** the judge (`{SETTINGS.judge_model}`) is itself a small model; its verdicts are "
                   "only trusted when it quotes verifiable evidence.")
    if any(t in definition.tools for t in ("weather", "current_date")):
        lim.append("**Live tools untested:** weather/date outputs change over time, so no static eval case can "
                   "check them; only tool routing was exercised.")
    if stats["warnings"]:
        lim.append("**Runtime warnings:** " + "; ".join(sorted(set(stats["warnings"])))[:600])
    lim.append("**Optimizer overfitting:** fixes were chosen on dev failures only; compare dev vs holdout in the "
               "table above. A dev gain without a holdout gain is likely overfitting.")
    L += [f"- {x}" for x in lim]
    for sec in extra_sections or []:
        L += ["", sec]
    L += ["", "## Artifacts in this folder", "",
          "`requirements.json/.md`, `groundability.json`, `tool_selection.json`, `agent_definition_v*.json`, "
          "`agent_definition_final.json`, `evals.json`, `evals_generation_log.json`, `results_iter*.json`, "
          "`scorecard.json/.md`, `iteration_log.json/.md`, `run_stats.json`, `llm_calls.jsonl` (every prompt and "
          "response of this run)."]
    (out_dir / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
