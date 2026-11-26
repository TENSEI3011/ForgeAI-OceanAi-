"""Requirement 2: the groundability guard.

For every must-answer topic we ask: can the documents actually support it?

  LLM verdict      supported / partial / unsupported + a verbatim quote from the excerpts
  quote check      the quote must really occur in the retrieved text, else the verdict is
                   downgraded (a model that cannot quote evidence does not get "supported")
  retrieval cap    low cosine similarity AND low keyword overlap cap the status, whatever
                   the LLM says (the LLM can lower a status, never raise it past the cap)

Unsupported topics are moved to must_refuse_topics, written into warnings and surfaced in
the report; the generated system prompt then tells the agent to decline them. If most
topics are unsupported the factory stops rather than build an agent that would have to
hallucinate.
"""
from __future__ import annotations

from rich.console import Console
from rich.markup import escape

from .llm import LLMJSONError, llm_json, render
from .retrieval import Index
from .schemas import Evidence, GroundingVerdictOut, Requirements, ToolForTopicOut, TopicGrounding
from .textutil import contains_quote, content_tokens, overlap, truncate
from .tools.registry import TOOLS, registry_for_prompt

console = Console()

SIM_LOW = 0.22    # below this (and little keyword overlap) a topic cannot be "supported" or "partial"
SIM_MID = 0.32    # below this (and modest keyword overlap) a topic cannot be "supported"
_RANK = {"unsupported": 0, "partial": 1, "supported": 2}


class GroundabilityAbort(RuntimeError):
    """Raised when the documents cannot support most of what the brief asks for."""


def check_topic(topic: str, index: Index, brief: str) -> TopicGrounding:
    hits, _ = index.search(topic, top_k=5, mode="hybrid", min_score=0.0)
    text = "\n".join(h.chunk.text for h in hits)
    top_sim = max((h.dense for h in hits), default=0.0)
    kw = overlap(content_tokens(topic), content_tokens(text))

    # deterministic cap from retrieval signals
    if top_sim < SIM_LOW and kw < 0.34:
        cap = "unsupported"
    elif top_sim < SIM_MID and kw < 0.5:
        cap = "partial"
    else:
        cap = "supported"

    excerpts = "\n\n".join(f"[{i}] ({h.chunk.source}) {truncate(h.chunk.text, 700)}" for i, h in enumerate(hits, 1))
    notes: list[str] = []
    try:
        v = llm_json(render("groundability_check", topic=topic, brief=brief, excerpts=excerpts or "(nothing found)"),
                     GroundingVerdictOut, temperature=0.0, max_tokens=400)
        llm_status, quote, reason = v.status, v.quote.strip(), v.reason
    except LLMJSONError as exc:
        llm_status, quote, reason = "unsupported", "", f"judge failed: {exc}"
    status = llm_status
    evidence: list[Evidence] = []
    if status != "unsupported":
        hit = next((h for h in hits if quote and contains_quote(quote, h.chunk.text, 88)), None)
        if hit is None:
            notes.append("LLM quote not found in the retrieved text")
            status = "partial" if (top_sim >= SIM_MID and kw >= 0.5) else "unsupported"
        else:
            evidence.append(Evidence(source=hit.chunk.source, snippet=truncate(quote, 300)))
    if _RANK[status] > _RANK[cap]:
        notes.append(f"capped to {cap} by retrieval signals (similarity {top_sim:.2f}, keyword overlap {kw:.2f})")
        status = cap
    if reason:
        notes.insert(0, reason)
    served_by = ""
    if status == "unsupported":
        # Documents cannot support it - but maybe a registry tool can (live data, dates, arithmetic).
        # Whether that tool is actually attached is reconciled by the generator.
        try:
            t = llm_json(render("groundability_tool", topic=topic, brief=brief, registry=registry_for_prompt()),
                         ToolForTopicOut, temperature=0.0, max_tokens=200)
            if t.tool in TOOLS:
                served_by = t.tool
                status = "supported"
                notes.append(f"not in the documents, but can be served by the '{t.tool}' tool: {t.reason}")
        except LLMJSONError:
            pass
    return TopicGrounding(topic=topic, status=status, evidence=evidence, note="; ".join(notes),
                          top_similarity=round(top_sim, 3), keyword_overlap=round(kw, 2), llm_status=llm_status,
                          served_by_tool=served_by)


def run_groundability(req: Requirements, index: Index) -> Requirements:
    results = [check_topic(t, index, req.brief) for t in req.must_answer_topics]
    req.groundability = results
    unsupported = [g for g in results if g.status == "unsupported"]
    partial = [g for g in results if g.status == "partial"]
    for g in results:
        colour = {"supported": "green", "partial": "yellow", "unsupported": "red"}[g.status]
        via = f" [cyan]via tool {g.served_by_tool}[/]" if g.served_by_tool else ""
        console.print(f"  [{colour}]{g.status:11}[/] {escape(g.topic)}{via} [dim](sim {g.top_similarity:.2f})[/]")

    for g in unsupported:
        req.warnings.append(f"UNSUPPORTED: the brief asks for '{g.topic}' but the documents do not cover it. "
                            "It was moved to must-refuse; the agent will decline instead of guessing.")
        req.must_answer_topics.remove(g.topic)
        req.must_refuse_topics.append(f"{g.topic} (requested, but not covered by the documents)")
    for g in partial:
        req.warnings.append(f"PARTIAL: documents only partly cover '{g.topic}'. The agent must say which parts "
                            "are not covered.")

    if results and len(unsupported) > len(results) / 2:
        raise GroundabilityAbort(
            f"{len(unsupported)} of {len(results)} requested topics are not supported by the documents "
            f"({', '.join(g.topic for g in unsupported)}). Building an agent now would force it to "
            "hallucinate or refuse most questions. Add documents that cover these topics, or narrow the brief.")
    return req
