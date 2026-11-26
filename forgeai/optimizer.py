"""Requirement 6: the critic-optimizer loop.

  run evals -> classify every failure -> pick the dominant category (max 2 per iteration so the
  effect is attributable) -> apply a TARGETED fix -> re-run -> keep, or roll back on regression.

Fix map (never a full regeneration):
  retrieval_miss  deterministic ladder: widen (top_k, hybrid, lower min_score if abstaining)
                  -> LLM query rewrite -> re-chunk
  hallucination   deterministic ladder: stricter grounding rule + lower temperature
                  -> raise min_score + off-topic rule
  prompt_defect   LLM writes a minimal patch (add/modify <= 3 rules) from 2-3 failing examples;
                  code applies it to PromptSpec.rules and re-renders the prompt (diff logged)
  wrong_refusal   over-answering -> add generalised refuse topics (LLM names the topic)
                  under-answering -> lower min_score + LLM patch clarifying what is in scope

Distrust built in:
  * the optimizer only sees DEV failures; HOLDOUT cases are scored but never used for fixes,
    so the report can show whether fixes generalise or just overfit the dev cases
  * patches that leak eval answers (numbers/IDs/phrases from expected facts or questions) into
    the prompt are rejected and logged: no teaching to the test
  * a change that lowers the dev pass rate is reverted ("reverted: regression")
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Callable

from rapidfuzz import fuzz
from rich.console import Console
from rich.markup import escape

from .generator import render_system_prompt
from .judge import evaluate
from .llm import LLMJSONError, get_stats, llm_json, render, stage
from .schemas import (AgentAnswer, AgentDefinition, CaseResult, Change, EvalCase, IterationRecord, PromptPatchOut,
                      Scorecard, TopicOut)
from .textutil import extract_ids, extract_numbers, fact_in_text, normalize, truncate

console = Console()

TARGET_PASS = 0.9
MIN_GAIN = 0.02
MAX_RULES = 12

STRICT_RULES = [
    "Before writing any number, amount, date or code, find it in the context passages or tool results; if it "
    "is not there, do not write it.",
    "If the passages discuss a different subject than the question, reply with the refusal sentence instead of "
    "answering from loosely related text.",
]
SCOPE_RULE = ("Decline any question whose subject is not listed under 'What you answer', even if the context "
              "contains loosely related words.")
COMPLETENESS_RULE = ("If the question has several parts or conditions, answer every part separately, giving the "
                     "specific value, person or deadline the context states for each, and cite each part.")


def _diff(before: str, after: str, label: str) -> str:
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), f"{label} (before)", f"{label} (after)",
                                 lineterm="", n=1)
    return truncate("\n".join(lines), 4000)


class Optimizer:
    def __init__(self, cases: list[EvalCase], out_dir: Path):
        self.cases = cases
        self.by_id = {c.id: c for c in cases}
        self.out_dir = out_dir
        self.tried: set[str] = set()
        self.rejected_patches: list[dict] = []
        self.pending_rules: list[str] = []      # rules written by the patch in the current iteration
        self.failed_rules: list[str] = []       # rules from patches that were reverted (shown to the patcher)
        self.n_patches = 0
        # material a patch must never contain: expected numbers/IDs and long question fragments
        self.leak_numbers = set().union(*(extract_numbers(" ".join(c.expected_facts)) for c in cases)) - {
            "0", "1", "2", "3", "4", "5", "10", "100"}
        self.leak_ids = set().union(*(extract_ids(" ".join(c.expected_facts + [c.question])) for c in cases))

    # ---------------------------------------------------------------- leak guard
    def _leaks(self, text: str) -> str | None:
        nums = extract_numbers(text) & self.leak_numbers
        if nums:
            return f"contains expected answer numbers {sorted(nums)}"
        ids = extract_ids(text) & self.leak_ids
        if ids:
            return f"contains IDs from the eval set {sorted(ids)}"
        for c in self.cases:
            for f in c.expected_facts:
                if len(f.split()) >= 3 and fact_in_text(f, text):
                    return f"restates an expected fact: '{f}'"
            if fuzz.partial_ratio(normalize(c.question), normalize(text)) >= 90 and len(c.question) > 30:
                return f"copies an eval question ({c.id})"
        if re.search(r"\b(general|outside|own|prior|world) knowledge\b", text, re.I) and not re.search(r"\b(not|never|no)\b", text, re.I):
            return "weakens the grounding rules"
        return None

    # ---------------------------------------------------------------- fixers
    def fix_retrieval(self, d: AgentDefinition, fails: list[CaseResult], answers: dict[str, AgentAnswer]) -> list[Change]:
        r = d.retrieval
        before = r.model_dump_json(indent=1) + "\n" + d.chunking.model_dump_json(indent=1)
        abstained = [f.case_id for f in fails if answers[f.case_id].abstained_no_context]
        vague = [f.case_id for f in fails if f.type == "edge_ambiguous"]
        ladder = ["retrieval:widen", "retrieval:rewrite", "retrieval:rechunk"]
        if len(vague) > len(fails) / 2:
            ladder = ["retrieval:rewrite", "retrieval:widen", "retrieval:rechunk"]
        step = next((s for s in ladder if s not in self.tried), None)
        if step is None:
            return []
        self.tried.add(step)
        if step == "retrieval:widen":
            what = []
            if r.top_k < 10:
                what.append(f"top_k {r.top_k} -> {min(10, r.top_k + 3)}")
                r.top_k = min(10, r.top_k + 3)
            if r.mode != "hybrid":
                what.append(f"mode {r.mode} -> hybrid")
                r.mode = "hybrid"
            if abstained and r.min_score > 0.1:
                what.append(f"min_score {r.min_score:.2f} -> {r.min_score - 0.05:.2f}")
                r.min_score = round(r.min_score - 0.05, 2)
            why = "the expected passages were not in the retrieved context; retrieve more candidates"
            if abstained:
                why += f" ({len(abstained)} case(s) abstained because nothing passed the min_score gate)"
        elif step == "retrieval:rewrite":
            r.query_rewrite = True
            what = ["enabled LLM query rewrite (search with the original AND a rewritten formal query)"]
            why = "user wording differs from document wording (typos, vague or indirect phrasing)"
        else:
            old = d.chunking.chunk_size
            new = int(old * 0.7) if old >= 800 else int(old * 1.4)
            d.chunking.chunk_size = max(300, min(1600, new))
            d.chunking.chunk_overlap = int(d.chunking.chunk_size * 0.2)
            what = [f"chunk_size {old} -> {d.chunking.chunk_size}, overlap -> {d.chunking.chunk_overlap} (index rebuilt)"]
            why = "facts were split across or buried in chunks; change granularity"
        after = r.model_dump_json(indent=1) + "\n" + d.chunking.model_dump_json(indent=1)
        return [Change(category="retrieval_miss", what="; ".join(what) or step, why=why,
                       failures_addressed=[f.case_id for f in fails], diff=_diff(before, after, "retrieval config"))]

    def fix_hallucination(self, d: AgentDefinition, fails: list[CaseResult], answers: dict[str, AgentAnswer]) -> list[Change]:
        step = next((s for s in ("hallucination:strict", "hallucination:gate") if s not in self.tried), None)
        if step is None:
            return []
        self.tried.add(step)
        before = "\n".join(d.prompt_spec.rules) + f"\ntemperature={d.llm.temperature} min_score={d.retrieval.min_score}"
        what = []
        if step == "hallucination:strict":
            if STRICT_RULES[0] not in d.prompt_spec.rules:
                d.prompt_spec.rules.append(STRICT_RULES[0])
                what.append("added strict number-grounding rule")
            if d.llm.temperature > 0.05:
                what.append(f"temperature {d.llm.temperature} -> 0.0")
                d.llm.temperature = 0.0
            d.output_contract.require_citations = True
        else:
            if STRICT_RULES[1] not in d.prompt_spec.rules:
                d.prompt_spec.rules.append(STRICT_RULES[1])
                what.append("added off-topic refusal rule")
            if d.retrieval.min_score < 0.4:
                what.append(f"min_score {d.retrieval.min_score:.2f} -> {d.retrieval.min_score + 0.05:.2f}")
                d.retrieval.min_score = round(d.retrieval.min_score + 0.05, 2)
        after = "\n".join(d.prompt_spec.rules) + f"\ntemperature={d.llm.temperature} min_score={d.retrieval.min_score}"
        return [Change(category="hallucination", what="; ".join(what) or step,
                       why="answers contained figures or claims that are not in the retrieved context",
                       failures_addressed=[f.case_id for f in fails], diff=_diff(before, after, "rules/config"))]

    def _patch(self, d: AgentDefinition, fails: list[CaseResult], answers: dict[str, AgentAnswer], category: str,
               problem: str) -> list[Change]:
        """Ask the LLM for a minimal rule patch based on 2-3 failing examples, then vet and apply it."""
        examples = []
        start = (self.n_patches * 3) % max(1, len(fails))     # rotate examples between attempts
        self.n_patches += 1
        for f in (fails[start:] + fails[:start])[:3]:
            c, a = self.by_id[f.case_id], answers[f.case_id]
            ctx = "\n".join(f"({x.source}) {truncate(x.text, 350)}" for x in a.retrieved[:2]) or "(none)"
            examples.append(f"Question: {c.question}\nWhat a correct answer needed: {c.expected_facts}\n"
                            f"Context given:\n{ctx}\nAgent answer: {truncate(a.answer, 500)}\nWhat went wrong: {f.diagnosis}")
        try:
            previous = "\n".join(f"- {r}" for r in self.failed_rules) or "- none"
            out = llm_json(render("optimizer_patch", problem=problem, role=d.prompt_spec.role,
                                  rules="\n".join(f"{i}. {r}" for i, r in enumerate(d.prompt_spec.rules)),
                                  examples="\n\n---\n".join(examples), previous=previous),
                           PromptPatchOut, temperature=0.2)
        except LLMJSONError as exc:
            return [Change(category=category, what="no change (patch generation failed)", why=str(exc)[:200],
                           failures_addressed=[f.case_id for f in fails])]
        before = "\n".join(d.prompt_spec.rules)
        applied, rejected = [], []
        for m in out.modify_rules[:3]:
            idx, text = m.get("index"), str(m.get("new_text", "")).strip()
            if not isinstance(idx, int) or not (0 <= idx < len(d.prompt_spec.rules)) or not text:
                continue
            if d.prompt_spec.rules[idx] in STRICT_RULES or d.prompt_spec.rules[idx] in (SCOPE_RULE, COMPLETENESS_RULE):
                rejected.append({"rule": text, "reason": "may not rewrite an optimizer safety rule"})
                continue
            leak = self._leaks(text)
            if leak:
                rejected.append({"rule": text, "reason": leak})
                continue
            applied.append(f"modified rule {idx}")
            d.prompt_spec.rules[idx] = text
            self.pending_rules.append(text)
        for text in out.add_rules[:3]:
            leak = self._leaks(text) or ("too long" if len(text) > 350 else None)
            if leak:
                rejected.append({"rule": text, "reason": leak})
                continue
            if any(fuzz.ratio(normalize(text), normalize(r)) > 85 for r in d.prompt_spec.rules):
                continue
            if len(d.prompt_spec.rules) >= MAX_RULES:
                rejected.append({"rule": text, "reason": f"rule budget ({MAX_RULES}) reached"})
                continue
            d.prompt_spec.rules.append(text)
            applied.append("added rule")
            self.pending_rules.append(text)
        self.rejected_patches += [r | {"category": category} for r in rejected]
        what = f"{', '.join(applied) or 'no rule applied'}" + (f"; rejected {len(rejected)} leaking/invalid rule(s)" if rejected else "")
        return [Change(category=category, what=what, why=out.rationale or problem,
                       failures_addressed=[f.case_id for f in fails],
                       diff=_diff(before, "\n".join(d.prompt_spec.rules), "domain rules"))] if applied or rejected else []

    def fix_prompt(self, d: AgentDefinition, fails: list[CaseResult], answers: dict[str, AgentAnswer]) -> list[Change]:
        # rung 1 (deterministic, cheap): completeness rule when answers miss facts the context had
        if "prompt:completeness" not in self.tried and COMPLETENESS_RULE not in d.prompt_spec.rules \
                and any(f.missing_facts for f in fails):
            self.tried.add("prompt:completeness")
            before = "\n".join(d.prompt_spec.rules)
            d.prompt_spec.rules.append(COMPLETENESS_RULE)
            self.pending_rules.append(COMPLETENESS_RULE)
            return [Change(category="prompt_defect", what="added a completeness rule (answer every part, cite each)",
                           why="the retrieved context contained the expected facts but answers left some out",
                           failures_addressed=[f.case_id for f in fails],
                           diff=_diff(before, "\n".join(d.prompt_spec.rules), "domain rules"))]
        # rungs 2-3: LLM-written minimal patches (each told which earlier rules did not help)
        n = sum(1 for t in self.tried if t.startswith("prompt:patch"))
        if n >= 2:
            return []
        self.tried.add(f"prompt:patch{n + 1}")
        return self._patch(d, fails, answers, "prompt_defect",
                           "The right passages were retrieved, but the answers missed required facts or broke the "
                           "citation/format contract.")

    def fix_refusal(self, d: AgentDefinition, fails: list[CaseResult], answers: dict[str, AgentAnswer]) -> list[Change]:
        over = [f for f in fails if f.should_refuse]
        under = [f for f in fails if not f.should_refuse]
        changes: list[Change] = []
        if over and "refusal:topics" not in self.tried:
            self.tried.add("refusal:topics")
            before = "\n".join(d.prompt_spec.refuse_topics)
            added = []
            for f in over[:4]:
                try:
                    t = llm_json(render("optimizer_topic", question=self.by_id[f.case_id].question), TopicOut,
                                 temperature=0.0, max_tokens=80).topic.strip()
                except LLMJSONError:
                    continue
                if (t and len(t.split()) <= 8 and fuzz.ratio(normalize(t), normalize(self.by_id[f.case_id].question)) < 70
                        and not any(fuzz.ratio(normalize(t), normalize(x)) > 80 for x in d.prompt_spec.refuse_topics + added)):
                    added.append(t)
            d.prompt_spec.refuse_topics += added
            if SCOPE_RULE not in d.prompt_spec.rules:
                d.prompt_spec.rules.append(SCOPE_RULE)
            changes.append(Change(category="wrong_refusal",
                                  what=f"added {len(added)} generalised refuse topic(s) and an explicit scope rule",
                                  why="the agent answered questions it should have declined (over-answering)",
                                  failures_addressed=[f.case_id for f in over],
                                  diff=_diff(before, "\n".join(d.prompt_spec.refuse_topics), "refuse topics")))
        if under and "refusal:relax" not in self.tried:
            self.tried.add("refusal:relax")
            note = ""
            if d.retrieval.min_score > 0.1:
                note = f"; min_score {d.retrieval.min_score:.2f} -> {d.retrieval.min_score - 0.05:.2f}"
                d.retrieval.min_score = round(d.retrieval.min_score - 0.05, 2)
            patch = self._patch(d, under, answers, "wrong_refusal",
                                "The agent refused although the retrieved context contained the answer (often because "
                                "the user's wording differed from the document's wording).")
            for p in patch:
                p.what += note
            changes += patch
        return changes

    # ---------------------------------------------------------------- the loop
    def run(self, definition: AgentDefinition, card: Scorecard, answers: list[AgentAnswer], max_iters: int,
            save_definition: Callable[[AgentDefinition], None], save_results: Callable[[int, Scorecard, list[AgentAnswer]], None]
            ) -> tuple[AgentDefinition, list[Scorecard], list[IterationRecord], str]:
        fixers = {"retrieval_miss": self.fix_retrieval, "hallucination": self.fix_hallucination,
                  "prompt_defect": self.fix_prompt, "wrong_refusal": self.fix_refusal}
        best, best_card = definition, card
        best_answers = {c.id: a for c, a in zip(self.cases, answers)}
        cards, records = [card], []
        stop_reason = f"reached the maximum of {max_iters} iterations"
        version = definition.version
        for it in range(1, max_iters + 1):
            ok, why = get_stats().budget_left()
            if not ok:
                stop_reason = f"budget: {why}"
                break
            dev_fails = [r for r in best_card.results if not r.passed and r.split == "dev"]
            if best_card.dev_pass_rate >= TARGET_PASS or not dev_fails:
                stop_reason = f"dev pass rate {best_card.dev_pass_rate:.0%} reached the target ({TARGET_PASS:.0%})"
                break
            by_cat: dict[str, list[CaseResult]] = {}
            for r in dev_fails:
                by_cat.setdefault(r.failure_category or "prompt_defect", []).append(r)
            ordered = sorted(by_cat, key=lambda k: -len(by_cat[k]))

            version += 1
            cand = best.model_copy(deep=True)
            cand.version = version
            self.pending_rules = []
            changes: list[Change] = []
            targeted: list[str] = []
            with stage("optimizer"):
                for cat in ordered:
                    if len(targeted) == 2:
                        break
                    ch = fixers[cat](cand, by_cat[cat], best_answers)
                    if ch:
                        changes += ch
                        targeted.append(cat)
            if not changes:
                stop_reason = "no untried targeted fix left for the remaining failure categories"
                version -= 1
                break
            old_prompt = cand.system_prompt
            cand.system_prompt = render_system_prompt(cand.prompt_spec, cand.output_contract, cand.tools)
            if cand.system_prompt != old_prompt:
                changes.append(Change(category="(rendered)", what="system prompt re-rendered from the patched spec",
                                      why="see the changes above", failures_addressed=[],
                                      diff=_diff(old_prompt, cand.system_prompt, "system prompt")))
            save_definition(cand)
            console.print(f"[bold]Optimizer[/] iteration {it}: targeting {targeted}")
            for c in changes:
                if c.category != "(rendered)":
                    console.print(f"  ({c.category}) {escape(c.what)}")
            new_card, new_answers = evaluate(cand, self.cases, it)
            save_results(it, new_card, new_answers)
            cards.append(new_card)

            before_pass = {r.case_id: r.passed for r in best_card.results}
            targeted_ids = {i for c in changes for i in c.failures_addressed}
            flipped_ok = [r.case_id for r in new_card.results if r.passed and not before_pass[r.case_id] and r.case_id in targeted_ids]
            flipped_bad = [r.case_id for r in new_card.results if not r.passed and before_pass[r.case_id]]
            gain = new_card.dev_pass_rate - best_card.dev_pass_rate
            if gain < 0:
                decision = "reverted: regression"
            elif gain == 0:
                # no evidence the change helps: keep the simpler, already-measured definition
                decision = "reverted: no improvement"
            else:
                decision = "kept"
            records.append(IterationRecord(
                iteration=it, from_version=best.version, to_version=cand.version, categories_targeted=targeted,
                changes=changes, before_score=best_card.pass_rate, after_score=new_card.pass_rate,
                before_dev=best_card.dev_pass_rate, after_dev=new_card.dev_pass_rate, flipped_to_pass=flipped_ok,
                flipped_to_fail=flipped_bad, decision=decision,
                note=f"holdout {best_card.holdout_pass_rate:.0%} -> {new_card.holdout_pass_rate:.0%}"))
            console.print(f"  dev {best_card.dev_pass_rate:.0%} -> {new_card.dev_pass_rate:.0%} | overall "
                          f"{best_card.pass_rate:.0%} -> {new_card.pass_rate:.0%} | {decision}")
            if decision != "kept":
                self.failed_rules += self.pending_rules   # the next patch is told these did not help
            if decision == "kept":
                best, best_card = cand, new_card
                best_answers = {c.id: a for c, a in zip(self.cases, new_answers)}
                if gain < MIN_GAIN:
                    stop_reason = f"diminishing returns: iteration {it} gained {gain * 100:.1f} points (< {MIN_GAIN * 100:.0f})"
                    break
            # a reverted change costs nothing but eval time; the next iteration tries the next untried fix
        return best, cards, records, stop_reason


def save_iteration_log(records: list[IterationRecord], rejected: list[dict], stop_reason: str, out_dir: Path) -> None:
    (out_dir / "iteration_log.json").write_text(json.dumps(
        {"stop_reason": stop_reason, "iterations": [r.model_dump() for r in records],
         "rejected_patches": rejected}, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Iteration log", "", f"**Stop reason:** {stop_reason}", ""]
    if not records:
        lines.append("No optimisation iterations were run (see stop reason).")
    for r in records:
        lines += [f"## Iteration {r.iteration}: v{r.from_version} -> v{r.to_version} ({r.decision})", "",
                  f"- Targeted categories: {', '.join(r.categories_targeted)}",
                  f"- Overall pass rate: {r.before_score:.0%} -> {r.after_score:.0%}; dev: {r.before_dev:.0%} -> "
                  f"{r.after_dev:.0%}; {r.note}",
                  f"- Targeted failures that now pass: {', '.join(r.flipped_to_pass) or 'none'}",
                  f"- Previously passing cases that now fail: {', '.join(r.flipped_to_fail) or 'none'}", ""]
        for c in r.changes:
            lines += [f"### [{c.category}] {c.what}", "", f"Why: {c.why}", "",
                      f"Failures addressed: {', '.join(c.failures_addressed) or '-'}", ""]
            if c.diff:
                lines += ["```diff", c.diff, "```", ""]
    if rejected:
        lines += ["## Rejected patch rules (leak guard / validation)", ""]
        lines += [f"- ({x['category']}) `{truncate(x['rule'], 160)}`: {x['reason']}" for x in rejected]
    (out_dir / "iteration_log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
