"""Requirement 3: the agent generator.

Produces a complete declarative AgentDefinition from Requirements + documents:

* system prompt   LLM writes the role, domain rules and answer style; code wraps them in a
                  fixed guardrail template (grounding, citations, refusal phrase, refuse list).
                  Invariants are enforced by code, not left to a 4B model to remember.
* retrieval       deterministic policy from document statistics (prose vs tables, paragraph
                  length): chunk size/overlap, top_k, hybrid mode, min_score.
* tools           LLM decides per registry tool WITH a quote from the requester's own words;
                  code verifies the quote, checks preconditions (csv_lookup needs a CSV), then a
                  second, skeptical LLM pass must agree. Every decision is logged.
* output contract citations required, fixed refusal phrase, word limit.
"""
from __future__ import annotations

from typing import Any

from rich.console import Console

from .ingest import Doc, doc_stats
from .intake import docs_overview
from .llm import LLMJSONError, llm_json, render
from .schemas import (AgentDefinition, Chunking, LLMConfig, OutputContract, PromptDraftOut, PromptSpec,
                      Requirements, RetrievalConfig, ToolSelectionOut)
from .textutil import contains_quote, extract_numbers, normalize
from .tools.registry import TOOLS, registry_for_prompt

console = Console()

REFUSAL_PHRASE = "I'm sorry, I can't answer that from the documents I have access to."


# ------------------------------------------------------------------ system prompt
def render_system_prompt(spec: PromptSpec, contract: OutputContract, tools: list[str]) -> str:
    """Deterministically render the agent's system prompt from its structured spec."""
    bullets = lambda xs: "\n".join(f"- {x}" for x in xs) or "- (none)"  # noqa: E731
    numbered = lambda xs: "\n".join(f"{i}. {x}" for i, x in enumerate(xs, 1)) or "(none)"  # noqa: E731
    if tools:
        lines = [f"- {t}: {TOOLS[t].description}" for t in tools]
        tools_section = ("## Tools\nThe system may run these tools for you and show their results:\n" + "\n".join(lines)
                         + "\nTreat tool results as facts and say which tool a figure came from.")
        if "calculator" in tools:
            tools_section += " Any computed number must come from a calculator result, never from mental arithmetic."
    else:
        tools_section = ("## Tools\nYou have no tools. Answer only from the context passages; do not compute "
                         "new figures that the documents do not state.")
    partial = ""
    if spec.partial_topics:
        partial = ("\n## Partially covered topics\nThe documents only partly cover these. Answer what is covered and "
                   "say clearly what is not:\n" + bullets(spec.partial_topics))
    return render("agent_system_prompt", role=spec.role.strip(), audience=spec.audience or "general users",
                  answer_topics=bullets(spec.answer_topics), refuse_topics=bullets(spec.refuse_topics),
                  refusal=contract.refusal_phrase, rules=numbered(spec.rules), tools_section=tools_section,
                  partial=partial, answer_style=spec.answer_style.strip(), max_words=str(contract.max_words),
                  tone=(spec.tone or "professional").strip().rstrip("."), citation_rule=(
                      "Cite the file name after every fact like this: [source: <file name>]."
                      if contract.require_citations else "Mention which document the answer comes from."))


# ------------------------------------------------------------------ retrieval policy
def choose_retrieval(docs: list[Doc]) -> tuple[Chunking, RetrievalConfig, dict[str, str]]:
    s = doc_stats(docs)
    why: dict[str, str] = {}
    if s["prose_chars"] == 0:
        size, ov = 600, 80
        why["chunking"] = "only tabular data: rows are chunked one per row; prose chunk size is irrelevant"
    elif s["avg_paragraph_chars"] > 600 or s["prose_chars"] > 80_000:
        size, ov = 1100, 160
        why["chunking"] = (f"long prose (avg paragraph {s['avg_paragraph_chars']:.0f} chars, {s['prose_chars']:.0f} "
                           "chars total): larger chunks keep rules and their conditions together")
    elif s["avg_paragraph_chars"] < 220:
        size, ov = 650, 100
        why["chunking"] = (f"short paragraphs/list items (avg {s['avg_paragraph_chars']:.0f} chars): smaller chunks "
                           "keep retrieval precise")
    else:
        size, ov = 850, 130
        why["chunking"] = f"medium prose (avg paragraph {s['avg_paragraph_chars']:.0f} chars): balanced chunks"
    top_k = 6 if s["n_tables"] else 5
    why["retrieval"] = ("hybrid dense+BM25: dense handles paraphrase, BM25 handles exact codes/IDs"
                        + ("; tables present, so top_k 6 to fit several rows" if s["n_tables"] else "")
                        + "; min_score 0.20 so off-topic questions retrieve nothing and the agent abstains")
    return Chunking(chunk_size=size, chunk_overlap=ov), RetrievalConfig(top_k=top_k, mode="hybrid", min_score=0.2), why


# ------------------------------------------------------------------ tools
def requester_words(req: Requirements) -> str:
    """Only text the requester actually supplied (brief + human/file answers), never LLM assumptions."""
    answers = [qa.answer for qa in req.clarifying_qa if qa.answered_by != "assumed_default"]
    return " ".join([req.brief, *answers])


def _first_sentence(quote: str) -> str:
    """Small models sometimes repeat a quote several times; keep the first sentence only."""
    quote = quote.strip()
    first = quote.split(". ")[0].strip()
    return first if len(first) >= 3 else quote[:200]


def _quote_ok(quote: str, source_text: str) -> bool:
    q = normalize(quote).strip(" .\"'")
    if len(q) < 3:
        return False
    return q in normalize(source_text) or contains_quote(q, source_text, 85)


def select_tools(req: Requirements, docs: list[Doc], overview: str) -> tuple[list[str], dict[str, str], list[dict[str, Any]]]:
    words = requester_words(req)
    has_tables = any(d.type == "table" for d in docs)
    log: list[dict[str, Any]] = []
    try:
        first = llm_json(render("generator_tools", brief=req.brief, requester=words, scope=req.scope,
                                topics=req.must_answer_topics, docs=overview, registry=registry_for_prompt()),
                         ToolSelectionOut, temperature=0.0)
        decisions = {d.name: d for d in first.decisions if d.name in TOOLS}
    except LLMJSONError as exc:
        decisions = {}
        log.append({"tool": "*", "attached": False, "reason": f"tool selection failed, attaching none: {exc}"})

    tentative: dict[str, str] = {}
    quotes: dict[str, str] = {}
    for name, spec in TOOLS.items():
        d = decisions.get(name)
        if d is None or not d.needed:
            log.append({"tool": name, "attached": False, "reason": (d.rationale if d else "not proposed") or "not needed"})
        elif spec.requires_tables and not has_tables:
            log.append({"tool": name, "attached": False, "reason": "precondition failed: no CSV/TSV table in documents"})
        elif not _quote_ok(d.brief_quote, words):
            log.append({"tool": name, "attached": False,
                        "reason": f"justification quote not found in the requester's words: '{d.brief_quote}'"})
        else:
            tentative[name] = d.rationale or d.brief_quote
            quotes[name] = _first_sentence(d.brief_quote)

    # Skeptical second opinion: every tentatively attached tool must survive a critic pass that sees the
    # same documents and the quoted justification, and checks that the words really ask for the tool.
    final: dict[str, str] = {}
    if tentative:
        try:
            candidates = [t | {"requester_words": quotes[t["name"]]} for t in registry_for_prompt()
                          if t["name"] in tentative]
            critic = llm_json(render("generator_tool_critic", brief=req.brief, requester=words, docs=overview,
                                     tools=candidates), ToolSelectionOut, temperature=0.0)
            verdict = {d.name: d for d in critic.decisions}
        except LLMJSONError:
            verdict = {}
        for name, why in tentative.items():
            v = verdict.get(name)
            if v is not None and v.needed and _quote_ok(v.brief_quote, words):
                final[name] = why
                log.append({"tool": name, "attached": True, "reason": why,
                            "brief_quote": _first_sentence(v.brief_quote)})
            else:
                log.append({"tool": name, "attached": False,
                            "reason": "critic pass rejected it" + (f": {v.rationale}" if v else " (no verdict)")})
    return list(final), final, log


# ------------------------------------------------------------------ main entry
def _clean_rules(rules: list[str], docs: list[Doc]) -> tuple[list[str], list[str]]:
    """Drop rules that state numbers the documents never mention (the model inventing policy)."""
    doc_numbers = set().union(*(extract_numbers(d.text) for d in docs)) if docs else set()
    kept, dropped = [], []
    for r in rules:
        r = r.strip()
        if not r or len(r) > 400:
            continue
        if extract_numbers(r) - doc_numbers - {"1", "2", "3"}:
            dropped.append(r)
        else:
            kept.append(r)
    return kept, dropped


def generate_definition(req: Requirements, docs: list[Doc], docs_dir: str,
                        requirements_path: str) -> tuple[AgentDefinition, dict[str, Any]]:
    overview = docs_overview(req.documents)
    chunking, retrieval, why = choose_retrieval(docs)
    console.print("[bold]Generator[/] selecting tools ...")
    tools, rationale, tool_log = select_tools(req, docs, overview)
    console.print(f"  tools attached: {tools or 'none'}")
    # Reconcile with the groundability guard: a topic the documents cannot support but a tool could
    # is only answerable if that tool really got attached; otherwise it must be refused.
    for g in req.groundability:
        if g.served_by_tool and g.served_by_tool not in tools:
            g.status = "unsupported"
            g.note += f"; the '{g.served_by_tool}' tool was not attached, so this topic cannot be served"
            if g.topic in req.must_answer_topics:
                req.must_answer_topics.remove(g.topic)
            req.must_refuse_topics.append(f"{g.topic} (requested, but not covered by the documents)")
            req.warnings.append(f"UNSUPPORTED: '{g.topic}' would need the '{g.served_by_tool}' tool, which tool "
                                "selection did not attach. Moved to must-refuse.")

    partial = [g.topic for g in req.groundability if g.status == "partial"]
    draft = llm_json(render("generator_prompt", brief=req.brief, scope=req.scope, audience=req.audience,
                            tone=req.tone, topics=req.must_answer_topics, refuse=req.must_refuse_topics,
                            warnings=req.warnings or ["none"], docs=overview,
                            tools=tools or ["none"]), PromptDraftOut, temperature=0.3)
    rules, dropped = _clean_rules(draft.rules, docs)
    spec = PromptSpec(role=draft.role, audience=req.audience, tone=req.tone, answer_topics=req.must_answer_topics,
                      rules=rules, refuse_topics=req.must_refuse_topics, answer_style=draft.answer_style,
                      partial_topics=partial)
    contract = OutputContract(format="markdown", require_citations=True, refusal_phrase=REFUSAL_PHRASE,
                              max_words=max(60, min(250, draft.max_words)))
    definition = AgentDefinition(
        name=req.agent_name, version=1, created_from=requirements_path, description=req.scope,
        system_prompt=render_system_prompt(spec, contract, tools), prompt_spec=spec, chunking=chunking,
        retrieval=retrieval, tools=tools, tool_rationale=rationale, output_contract=contract,
        documents_dir=docs_dir, llm=LLMConfig(temperature=0.2), config_rationale=why)
    meta = {"tool_decisions": tool_log, "dropped_rules": dropped}
    return definition, meta
