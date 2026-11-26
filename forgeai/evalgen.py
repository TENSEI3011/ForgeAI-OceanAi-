"""Requirement 4: the eval generator. Cases are GENERATED from the documents, then VERIFIED.

Case types (default mix for 24 cases):
  answerable      10  one passage -> question + 1-4 facts, each with a verbatim quote
                      (+ up to 2 arithmetic cases when the agent has a calculator)
  out_of_scope     5  half from must-refuse topics, half plausible-but-absent questions
  edge_ambiguous   4  vague / typo-ridden / indirect phrasing of a fact in one passage
  edge_multi_doc   5  two related passages from DIFFERENT documents (embedding-matched)

Verification (all deterministic, LLM claims are never taken on trust):
  a. every quote must occur in the claimed source document (normalised / near-verbatim)
  b. every fact's numbers and IDs must occur in its quote, and its words must overlap it
  c. out-of-scope questions must not be answerable: high similarity to any chunk, or an
     answerability check that finds a verified quote, drops the case
  d. the question must not leak its own answer, refer to "the passage", or duplicate another
  e. arithmetic cases: expression inputs must come from the quote/question and the expected
     number is recomputed by our own calculator
Failed cases are dropped (with the reason logged) and regenerated, for up to 3 rounds.
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from rich.console import Console

from .ingest import Chunk, Doc
from .llm import LLMJSONError, llm_json, render
from .retrieval import Index
from .schemas import (AgentDefinition, AnswerabilityOut, EvalCase, FactCheckOut, GenCaseOut, GenMultiCaseOut,
                      GenOOSOut, GenToolCaseOut, Requirements)
from .tools.registry import TOOLS
from .textutil import contains_quote, extract_ids, extract_numbers, fact_in_text, normalize, truncate
from .tools.calculator import calculate

console = Console()

OOS_MAX_SIM = 0.72        # an out-of-scope question this close to a chunk is suspicious
MAX_ROUNDS = 3
AMBIGUITY_STYLES = [
    "informal and typed in a hurry, with one or two spelling mistakes and no formal terms",
    "indirect: describe the user's own situation instead of naming the rule, item or section",
    "very short and underspecified (4-8 words), using everyday words instead of the document's terms",
]
_META_RE = re.compile(r"\b(passage|excerpt|the text|the document above|according to the (text|passage))\b", re.I)


@dataclass
class Quota:
    answerable: int = 10
    out_of_scope: int = 5
    edge_ambiguous: int = 4
    edge_multi_doc: int = 5

    @classmethod
    def for_total(cls, n: int) -> "Quota":
        n = max(20, n)
        q = cls(answerable=round(n * 10 / 24), out_of_scope=round(n * 5 / 24), edge_ambiguous=round(n * 4 / 24))
        q.edge_multi_doc = n - q.answerable - q.out_of_scope - q.edge_ambiguous
        return q


@dataclass
class EvalGenResult:
    cases: list[EvalCase]
    dropped: list[dict[str, Any]] = field(default_factory=list)
    attempts: int = 0
    notes: list[str] = field(default_factory=list)


class EvalGenerator:
    def __init__(self, req: Requirements, definition: AgentDefinition, docs: list[Doc], chunks: list[Chunk],
                 index: Index, seed: int = 13):
        self.req, self.d, self.docs, self.index = req, definition, docs, index
        self.rng = random.Random(seed)
        self.doc_text = {d.source: d.text for d in docs}
        self.chunks = chunks
        self.chunk_pos = {c.chunk_id: i for i, c in enumerate(chunks)}
        self.used: set[str] = set()
        self.reuse = False          # set from round 2 on: small corpora may run out of unused chunks
        self.dropped: list[dict[str, Any]] = []
        self.attempts = 0
        self.notes: list[str] = []
        self.questions: list[str] = []

    # -------------------------------------------------------------- sampling
    def _fresh(self, c: Chunk) -> bool:
        """Unused chunk, or any chunk once small corpora force reuse (later rounds)."""
        return self.reuse or c.chunk_id not in self.used

    def _candidates(self, doc: str) -> list[Chunk]:
        """Information-dense, unused chunks of one document (numbers/IDs make better test facts)."""
        cands = [c for c in self.chunks if c.source == doc and self._fresh(c)
                 and c.heading != "table schema" and len(c.text) >= (40 if c.row else 180)]
        self.rng.shuffle(cands)
        cands.sort(key=lambda c: -min(6, len(extract_numbers(c.text)) + len(extract_ids(c.text))))
        top = cands[: max(4, len(cands) // 2)]
        self.rng.shuffle(top)
        return top

    def _round_robin(self, n: int) -> list[Chunk]:
        docs = [d.source for d in self.docs]
        self.rng.shuffle(docs)
        pools = {d: self._candidates(d) for d in docs}
        picked: list[Chunk] = []
        while len(picked) < n and any(pools.values()):
            for d in docs:
                if pools[d] and len(picked) < n:
                    picked.append(pools[d].pop())
        return picked

    def _pairs(self, n: int) -> list[tuple[Chunk, Chunk]]:
        """Related chunk pairs from different documents (cosine similarity on chunk embeddings)."""
        cand = [c for c in self.chunks if self._fresh(c) and c.heading != "table schema"
                and len(c.text) >= (40 if c.row else 180)]
        if len(cand) > 260:   # keep the similarity matrix small
            cand = self.rng.sample(cand, 260)
        if len(cand) < 2:
            return []
        vec = self.index.vectors[[self.chunk_pos[c.chunk_id] for c in cand]]
        sims = vec @ vec.T
        multi_doc = len({c.source for c in cand}) > 1
        scored = []
        for i in range(len(cand)):
            for j in range(i + 1, len(cand)):
                a, b = cand[i], cand[j]
                if multi_doc and a.source == b.source:
                    continue
                if not multi_doc and abs(self.chunk_pos[a.chunk_id] - self.chunk_pos[b.chunk_id]) < 3:
                    continue
                if a.row and b.row:   # two table rows make a weak "cross-document" question
                    continue
                if 0.3 <= sims[i, j] <= 0.9:
                    scored.append((float(sims[i, j]), a, b))
        scored.sort(key=lambda t: -t[0])
        out, seen = [], set()
        for _, a, b in scored:
            if a.chunk_id in seen or b.chunk_id in seen:
                continue
            out.append((a, b))
            seen |= {a.chunk_id, b.chunk_id}
            if len(out) >= n:
                break
        if not multi_doc and out:
            self.notes.append("only one document: multi-doc cases use two distant sections of the same document")
        return out

    # -------------------------------------------------------------- checks
    def _drop(self, ctype: str, question: str, reason: str, origin: str) -> None:
        self.dropped.append({"type": ctype, "question": question, "reason": reason, "origin": origin})

    def _question_ok(self, q: str, facts: list[str]) -> str | None:
        """Return a rejection reason or None."""
        if len(q.split()) < 3:
            return "question too short"
        if _META_RE.search(q):
            return "question refers to 'the passage' instead of being a real user question"
        if facts and all(fact_in_text(f, q) for f in facts):
            return "question leaks its own answer"
        if any(fuzz.ratio(normalize(q), normalize(p)) >= 85 for p in self.questions):
            return "near-duplicate of an existing question"
        return None

    def _verify_fact(self, fact: str, quote: str, source: str, passage: str) -> str | None:
        if not contains_quote(quote, self.doc_text.get(source, ""), 90):
            return f"quote not found in {source}: '{truncate(quote, 80)}'"
        if not (fact_in_text(fact, quote) or fact_in_text(fact, passage)):
            return f"fact not supported by its quote: '{fact}'"
        if not extract_numbers(fact) <= extract_numbers(passage):
            return f"fact has numbers not in the source passage: '{fact}'"
        return None

    def _log_prompt(self) -> None:
        self.attempts += 1

    def _relevant(self, question: str, facts: list[str]) -> list[int]:
        """Second opinion that may only REMOVE facts that do not answer the question (never add)."""
        if len(facts) < 2:
            return list(range(len(facts)))
        listing = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(facts))
        try:
            out = llm_json(render("evalgen_fact_check", question=question, facts=listing), FactCheckOut,
                           temperature=0.0, max_tokens=120)
        except LLMJSONError:
            return list(range(len(facts)))
        keep = sorted({i - 1 for i in out.relevant if 1 <= i <= len(facts)})
        return keep or list(range(len(facts)))   # an empty verdict is treated as "no opinion"

    # -------------------------------------------------------------- generators
    def gen_single(self, chunk: Chunk, ctype: str, style: str = "") -> EvalCase | None:
        origin = chunk.chunk_id
        self.used.add(chunk.chunk_id)
        self._log_prompt()
        prompt = (render("evalgen_ambiguous", passage=chunk.text, source=chunk.source, style=style,
                         audience=self.req.audience)
                  if ctype == "edge_ambiguous" else
                  render("evalgen_answerable", passage=chunk.text, source=chunk.source, audience=self.req.audience,
                         scope=self.req.scope))
        try:
            out = llm_json(prompt, GenCaseOut, temperature=0.4, max_tokens=600)
        except LLMJSONError as exc:
            self._drop(ctype, "", f"generator returned invalid JSON 3 times: {exc}", origin)
            return None
        facts, quotes, reasons = [], [], []
        for f in out.facts:
            reason = self._verify_fact(f.fact, f.quote, chunk.source, chunk.text)
            if reason:
                reasons.append(reason)
            else:
                facts.append(f.fact.strip())
                quotes.append(f.quote.strip())
        if not facts:
            self._drop(ctype, out.question, "; ".join(reasons) or "no facts", origin)
            return None
        bad = self._question_ok(out.question, facts)
        if bad:
            self._drop(ctype, out.question, bad, origin)
            return None
        keep = self._relevant(out.question, facts)
        if len(keep) < len(facts):
            reasons.append(f"{len(facts) - len(keep)} fact(s) judged not part of the answer")
            facts, quotes = [facts[i] for i in keep], [quotes[i] for i in keep]
        self.questions.append(out.question)
        notes = f"removed {len(reasons)} fact(s): {'; '.join(reasons)}" if reasons else ""
        return EvalCase(id="", type=ctype, question=out.question.strip(), expected_sources=[chunk.source],
                        expected_facts=facts, source_quotes=quotes, verified=True, origin=origin,
                        tools_expected=["csv_lookup"] if chunk.row and "csv_lookup" in self.d.tools else [],
                        notes=(f"style: {style}. " if style else "") + notes)

    def gen_multi(self, a: Chunk, b: Chunk) -> EvalCase | None:
        origin = f"{a.chunk_id} + {b.chunk_id}"
        self.used |= {a.chunk_id, b.chunk_id}
        self._log_prompt()
        try:
            out = llm_json(render("evalgen_multidoc", passage_a=a.text, source_a=a.source, passage_b=b.text,
                                  source_b=b.source, audience=self.req.audience), GenMultiCaseOut,
                           temperature=0.4, max_tokens=700)
        except LLMJSONError as exc:
            self._drop("edge_multi_doc", "", f"invalid JSON: {exc}", origin)
            return None
        facts, quotes, reasons, sides = [], [], [], set()
        for f in out.facts:
            chunk = a if f.passage == "A" else b
            reason = self._verify_fact(f.fact, f.quote, chunk.source, chunk.text)
            if reason:
                reasons.append(reason)
            else:
                facts.append(f.fact.strip())
                quotes.append(f.quote.strip())
                sides.add(f.passage)
        if sides != {"A", "B"}:
            self._drop("edge_multi_doc", out.question,
                       "needs at least one verified fact from EACH passage; " + "; ".join(reasons), origin)
            return None
        bad = self._question_ok(out.question, facts)
        if bad:
            self._drop("edge_multi_doc", out.question, bad, origin)
            return None
        keep = self._relevant(out.question, facts)
        side_of = [f.passage for f in out.facts if f.fact.strip() in facts]
        if len(side_of) == len(facts) and {side_of[i] for i in keep} != {"A", "B"}:
            # after removing off-question facts it no longer needs both documents: not a multi-doc case
            self._drop("edge_multi_doc", out.question, "after the relevance check the answer no longer needs both "
                       "documents", origin)
            return None
        facts, quotes = [facts[i] for i in keep], [quotes[i] for i in keep]
        self.questions.append(out.question)
        return EvalCase(id="", type="edge_multi_doc", question=out.question.strip(),
                        expected_sources=list(dict.fromkeys([a.source, b.source])), expected_facts=facts,
                        source_quotes=quotes, verified=True, origin=origin)

    def gen_tool(self, chunk: Chunk) -> EvalCase | None:
        """Arithmetic case whose expected number is recomputed by our own calculator."""
        origin = chunk.chunk_id
        self.used.add(chunk.chunk_id)
        self._log_prompt()
        try:
            out = llm_json(render("evalgen_tool", passage=chunk.text, source=chunk.source, audience=self.req.audience),
                           GenToolCaseOut, temperature=0.4, max_tokens=500)
        except LLMJSONError as exc:
            self._drop("answerable", "", f"invalid JSON: {exc}", origin)
            return None
        if not contains_quote(out.quote, self.doc_text.get(chunk.source, ""), 90):
            self._drop("answerable", out.question, "tool case quote not found in source", origin)
            return None
        allowed = extract_numbers(out.quote) | extract_numbers(out.question) | extract_numbers(chunk.text)
        used_nums = extract_numbers(out.expression)
        if not used_nums or not used_nums <= allowed | {"100"}:
            self._drop("answerable", out.question, f"expression uses numbers not in quote/question: {out.expression}", origin)
            return None
        try:
            value = float(calculate(out.expression))
        except Exception as exc:
            self._drop("answerable", out.question, f"expression does not evaluate: {exc}", origin)
            return None
        expected = f"{value:,.2f}".rstrip("0").rstrip(".") if not value.is_integer() else f"{int(value)}"
        bad = self._question_ok(out.question, [expected])
        if bad:
            self._drop("answerable", out.question, bad, origin)
            return None
        self.questions.append(out.question)
        return EvalCase(id="", type="answerable", question=out.question.strip(), expected_sources=[chunk.source],
                        expected_facts=[expected], source_quotes=[out.quote.strip()], verified=True, origin=origin,
                        tools_expected=["calculator"], notes=f"arithmetic check: {out.expression} = {expected} (recomputed by calculator)")

    def gen_out_of_scope(self, n: int) -> list[EvalCase]:
        refuse = [t for t in self.req.must_refuse_topics if t.strip()]
        questions: list[tuple[str, str]] = []
        n_refuse = math.ceil(n / 2) if refuse else 0
        if n_refuse:
            self._log_prompt()
            try:
                out = llm_json(render("evalgen_oos_refuse", topics=refuse, audience=self.req.audience,
                                      n=str(n_refuse + 2)), GenOOSOut, temperature=0.6)
                questions += [(q, "must-refuse topic") for q in out.questions]
            except LLMJSONError as exc:
                self._drop("out_of_scope", "", f"invalid JSON: {exc}", "refuse topics")
        self._log_prompt()
        try:
            tools = "\n".join(f"- {t}: {TOOLS[t].description}" for t in self.d.tools) or "- none"
            out = llm_json(render("evalgen_oos_absent", scope=self.req.scope, audience=self.req.audience,
                                  docs="\n".join(f"- {d.source}: {d.summary}" for d in self.req.documents),
                                  tools=tools, n=str(n - n_refuse + 3)), GenOOSOut, temperature=0.6)
            questions += [(q, "plausible but absent from documents") for q in out.questions]
        except LLMJSONError as exc:
            self._drop("out_of_scope", "", f"invalid JSON: {exc}", "absent topics")

        cases: list[EvalCase] = []
        for q, origin in questions:
            if len(cases) >= n:
                break
            bad = self._question_ok(q, [])
            if bad:
                self._drop("out_of_scope", q, bad, origin)
                continue
            hits, _ = self.index.search(q, top_k=3, mode="hybrid", min_score=0.0)
            top_sim = max((h.dense for h in hits), default=0.0)
            if top_sim >= OOS_MAX_SIM:
                self._drop("out_of_scope", q, f"too similar to document text (cosine {top_sim:.2f}); may be answerable", origin)
                continue
            if origin != "must-refuse topic" or top_sim >= 0.45:
                # LLM answerability check, and its quote must be real to count
                excerpts = "\n\n".join(f"({h.chunk.source}) {truncate(h.chunk.text, 600)}" for h in hits)
                try:
                    a = llm_json(render("evalgen_answerability", question=q, excerpts=excerpts), AnswerabilityOut,
                                 temperature=0.0, max_tokens=300)
                    if a.answerable and a.quote and any(contains_quote(a.quote, h.chunk.text, 88) for h in hits):
                        self._drop("out_of_scope", q, f"secretly answerable from the documents: '{truncate(a.quote, 100)}'", origin)
                        continue
                except LLMJSONError:
                    pass
            self.questions.append(q)
            cases.append(EvalCase(id="", type="out_of_scope", question=q.strip(), should_refuse=True, verified=True,
                                  origin=origin, notes=f"max similarity to any chunk {top_sim:.2f}"))
        return cases

    # -------------------------------------------------------------- orchestration
    def generate(self, total: int = 24) -> EvalGenResult:
        quota = Quota.for_total(total)
        n_tool = 2 if "calculator" in self.d.tools else 0
        got: dict[str, list[EvalCase]] = {"answerable": [], "tool": [], "out_of_scope": [],
                                          "edge_ambiguous": [], "edge_multi_doc": []}
        want = {"answerable": quota.answerable - n_tool, "tool": n_tool, "out_of_scope": quota.out_of_scope,
                "edge_ambiguous": quota.edge_ambiguous, "edge_multi_doc": quota.edge_multi_doc}
        numeric_chunks = lambda: [c for c in self.chunks if self._fresh(c)  # noqa: E731
                                  and c.heading != "table schema" and len(extract_numbers(c.text)) >= 1
                                  and (c.row or len(c.text) >= 180)]
        for rnd in range(MAX_ROUNDS):
            if rnd >= 1 and len(got["tool"]) < want["tool"]:
                # arithmetic cases keep failing verification: refill the quota with plain answerable cases
                deficit = want["tool"] - len(got["tool"])
                self.notes.append(f"{deficit} arithmetic case(s) failed verification; replaced by answerable cases")
                want["tool"] -= deficit
                want["answerable"] += deficit
            need = {k: want[k] - len(v) for k, v in got.items()}
            if all(v <= 0 for v in need.values()):
                break
            console.print(f"[bold]Evalgen[/] round {rnd + 1}: need {', '.join(f'{k}={v}' for k, v in need.items() if v > 0)}")
            extra = 1 if rnd == 0 else 2   # oversample a little to absorb drops
            if rnd >= 1 and not self.reuse:
                self.reuse = True
                self.notes.append("round 2+: passages may be reused by a different case type (small corpus)")
            if need["edge_multi_doc"] > 0:
                pairs = self._pairs(need["edge_multi_doc"] + extra)
                if not pairs:   # e.g. a single table: no meaningful pairs exist; keep the total by refilling
                    self.notes.append(f"no related passage pairs found; {need['edge_multi_doc']} multi-doc slot(s) "
                                      "refilled with answerable cases")
                    want["answerable"] += need["edge_multi_doc"]
                    want["edge_multi_doc"] -= need["edge_multi_doc"]
                    need["answerable"] += need["edge_multi_doc"]
                for a, b in pairs:
                    if len(got["edge_multi_doc"]) >= want["edge_multi_doc"]:
                        break
                    if (c := self.gen_multi(a, b)):
                        got["edge_multi_doc"].append(c)
            if need["answerable"] > 0:
                for ch in self._round_robin(need["answerable"] + extra):
                    if len(got["answerable"]) >= want["answerable"]:
                        break
                    if (c := self.gen_single(ch, "answerable")):
                        got["answerable"].append(c)
            if need["tool"] > 0:
                pool = numeric_chunks()
                pool.sort(key=lambda c: (0 if c.row else 1))
                pool = pool[: max(10, need["tool"] * 4)]
                for ch in self.rng.sample(pool, min(len(pool), need["tool"] + extra)):
                    if len(got["tool"]) >= want["tool"]:
                        break
                    if (c := self.gen_tool(ch)):
                        got["tool"].append(c)
            if need["edge_ambiguous"] > 0:
                for i, ch in enumerate(self._round_robin(need["edge_ambiguous"] + extra)):
                    if len(got["edge_ambiguous"]) >= want["edge_ambiguous"]:
                        break
                    style = AMBIGUITY_STYLES[(len(got["edge_ambiguous"]) + i) % len(AMBIGUITY_STYLES)]
                    if (c := self.gen_single(ch, "edge_ambiguous", style)):
                        got["edge_ambiguous"].append(c)
            if need["out_of_scope"] > 0:
                got["out_of_scope"] += self.gen_out_of_scope(need["out_of_scope"])

        # The set must never fall below the requested size (minimum 20). If a type stayed short after
        # the rounds above (typically two-document pairs on a small corpus), top the total up with
        # single-passage answerable cases, the type that verifies most reliably. Found by a fresh run
        # that ended with 17 cases because only 2 of 5 multi-doc pairs survived verification.
        target = quota.answerable + quota.out_of_scope + quota.edge_ambiguous + quota.edge_multi_doc
        missing = target - sum(len(v) for v in got.values())
        if missing > 0:
            self.notes.append(f"{missing} case(s) short of {target} after {MAX_ROUNDS} rounds; "
                              "topped up with answerable cases")
            self.reuse = True
            for _ in range(MAX_ROUNDS):
                short = target - sum(len(v) for v in got.values())
                if short <= 0:
                    break
                console.print(f"[bold]Evalgen[/] top-up: need {short} more case(s)")
                for ch in self._round_robin(short + 2):
                    if sum(len(v) for v in got.values()) >= target:
                        break
                    if (c := self.gen_single(ch, "answerable")):
                        got["answerable"].append(c)

        cases = got["answerable"] + got["tool"] + got["edge_ambiguous"] + got["edge_multi_doc"] + got["out_of_scope"]
        prefix = {"answerable": "A", "out_of_scope": "O", "edge_ambiguous": "E", "edge_multi_doc": "M"}
        counters: dict[str, int] = {}
        for c in cases:
            counters[c.type] = counters.get(c.type, 0) + 1
            c.id = f"{prefix[c.type]}{counters[c.type]:02d}"
            # deterministic stratified split: every third case of each type is held out
            c.split = "holdout" if counters[c.type] % 3 == 0 else "dev"
        for k, v in want.items():
            if len(got[k]) < v:
                self.notes.append(f"{k}: generated {len(got[k])} of {v} wanted after {MAX_ROUNDS} rounds")
        return EvalGenResult(cases=cases, dropped=self.dropped, attempts=self.attempts, notes=self.notes)


def save_evals(result: EvalGenResult, out_dir: Path) -> None:
    (out_dir / "evals.json").write_text(json.dumps([c.model_dump() for c in result.cases], indent=2,
                                                   ensure_ascii=False), encoding="utf-8")
    by_type: dict[str, int] = {}
    for c in result.cases:
        by_type[c.type] = by_type.get(c.type, 0) + 1
    (out_dir / "evals_generation_log.json").write_text(json.dumps({
        "n_cases": len(result.cases), "by_type": by_type,
        "by_split": {s: sum(c.split == s for c in result.cases) for s in ("dev", "holdout")},
        "generation_attempts": result.attempts, "n_dropped": len(result.dropped), "notes": result.notes,
        "prompt_templates": sorted(p.name for p in (Path(__file__).resolve().parent.parent / "prompts").glob("evalgen_*.md")),
        "dropped_cases": result.dropped}, indent=2, ensure_ascii=False), encoding="utf-8")


def load_evals(path: str | Path) -> list[EvalCase]:
    return [EvalCase.model_validate(c) for c in json.loads(Path(path).read_text(encoding="utf-8-sig"))]
