"""Requirement 1: the intake interviewer.

1. Inspect the document folder (deterministic stats + a short LLM summary per document).
2. Ask the LLM for AT MOST 5 clarifying questions that the brief + docs actually leave open,
   each with a default assumption.
3. Get answers: interactively (CLI input), from an answers file (a simulated requester answers
   from the requester's notes), or by recording the default as an explicit assumption.
4. Draft the structured requirements (scope, audience, tone, must-answer, must-refuse).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from .ingest import Doc, headings_of, row_to_text
from .llm import LLMJSONError, llm_json, render
from .schemas import (QA, BriefDemandsOut, ClarifyingQuestion, ClarifyingQuestionsOut, DocInfo, DocSummaryOut,
                      RequesterAnswerOut, Requirements, RequirementsDraftOut)
from .textutil import content_tokens, overlap, truncate

console = Console()
MAX_QUESTIONS = 5


def inspect_documents(docs: list[Doc]) -> list[DocInfo]:
    infos = []
    for doc in docs:
        info = DocInfo(source=doc.source, type=doc.type, chars=len(doc.text), pages=len(doc.pages),
                       rows=len(doc.rows), columns=doc.columns, headings=headings_of(doc))
        if doc.type == "table":
            excerpt = (f"CSV table with {len(doc.rows)} rows. Columns: {', '.join(doc.columns)}\n"
                       + "\n".join(row_to_text(r) for r in doc.rows[:6]))
        else:
            excerpt = ("Headings: " + "; ".join(info.headings) + "\n\n" if info.headings else "") + doc.text[:2500]
        try:
            info.summary = llm_json(render("intake_doc_summary", source=doc.source, excerpt=excerpt),
                                    DocSummaryOut, max_tokens=300).summary
        except Exception as exc:
            info.summary = f"(summary unavailable: {exc})"
        infos.append(info)
    return infos


def docs_overview(infos: list[DocInfo]) -> str:
    """Compact text description of the folder, reused by several prompts."""
    lines = []
    for i in infos:
        shape = f"{i.rows} rows; columns: {', '.join(i.columns)}" if i.type == "table" else \
            f"{i.pages or 1} page(s), {i.chars} chars" + (f"; sections: {'; '.join(i.headings[:8])}" if i.headings else "")
        lines.append(f"- {i.source} ({i.type}, {shape})\n  Summary: {i.summary}")
    return "\n".join(lines)


def generate_questions(brief: str, overview: str) -> list[ClarifyingQuestion]:
    out = llm_json(render("intake_questions", brief=brief, docs=overview), ClarifyingQuestionsOut, temperature=0.2)
    seen, questions = set(), []
    for q in out.questions:
        key = q.question.strip().lower()
        if key and key not in seen:
            seen.add(key)
            questions.append(q)
    return questions[:MAX_QUESTIONS]   # hard cap enforced in code, not trusted to the model


def collect_answers(questions: list[ClarifyingQuestion], answers_file: str | None,
                    interactive: bool) -> list[QA]:
    notes: list[str] = []
    if answers_file:
        data = json.loads(Path(answers_file).read_text(encoding="utf-8-sig"))
        raw = data.get("requester_notes", data)
        notes = [str(n) for n in raw] if isinstance(raw, list) else [f"{k}: {v}" for k, v in raw.items()]
    numbered = "\n".join(f"{i}. {n}" for i, n in enumerate(notes, 1))
    qas: list[QA] = []
    for i, q in enumerate(questions, 1):
        if interactive and sys.stdin.isatty():
            console.print(f"\n[bold cyan]Q{i}.[/] {escape(q.question)}\n[dim](Enter = default: {escape(q.default_answer)})[/]")
            ans = input("> ").strip()
            qas.append(QA(question=q.question, answer=ans or q.default_answer,
                          answered_by="human" if ans else "assumed_default"))
        elif notes:
            # Simulated requester: the LLM only SELECTS which notes answer the question; the answer is
            # those notes verbatim, so the simulation can pick badly but can never invent a preference.
            r = llm_json(render("intake_simulated_requester", notes=numbered, question=q.question),
                         RequesterAnswerOut, temperature=0.0, max_tokens=60)
            picked = [notes[i - 1] for i in dict.fromkeys(r.note_numbers) if 1 <= i <= len(notes)]
            if picked:
                qas.append(QA(question=q.question, answer=" ".join(picked), answered_by="requester_file"))
            else:
                qas.append(QA(question=q.question, answer=q.default_answer, answered_by="assumed_default"))
        else:
            qas.append(QA(question=q.question, answer=q.default_answer, answered_by="assumed_default"))
    return qas


def extract_brief_demands(brief: str) -> list[str]:
    """What the brief itself asks for. Each demand must be made of the brief's own words (verified)."""
    try:
        out = llm_json(render("intake_brief_demands", brief=brief), BriefDemandsOut, temperature=0.0, max_tokens=300)
    except LLMJSONError:
        return []
    brief_words = content_tokens(brief)
    return [d.strip() for d in out.demands
            if content_tokens(d) and overlap(content_tokens(d), brief_words) >= 0.6]


def draft_requirements(brief: str, overview: str, qas: list[QA], infos: list[DocInfo]) -> Requirements:
    qa_text = "\n".join(f"Q: {qa.question}\nA: {qa.answer}" for qa in qas) or "(no questions asked)"
    demands = extract_brief_demands(brief)
    d = llm_json(render("intake_requirements", brief=brief, docs=overview, qa=qa_text,
                        demands="\n".join(f"- {x}" for x in demands) or "- (see brief)"),
                 RequirementsDraftOut, temperature=0.1)
    dedupe = lambda xs: list(dict.fromkeys(x.strip() for x in xs if x and x.strip()))  # noqa: E731
    topics = dedupe(d.must_answer_topics)
    # Enforced in code: every demand of the brief must be represented by a topic, otherwise the
    # groundability guard would never check it (a small model tends to list the documents' contents
    # instead of what the requester asked for).
    for demand in demands:
        # covered if half of the demand's words are in a topic, or half of a topic's words are in the demand
        if not any(overlap(content_tokens(demand), content_tokens(t)) >= 0.5 or
                   overlap(content_tokens(t), content_tokens(demand)) >= 0.5 for t in topics):
            topics.append(demand)
    return Requirements(brief=brief, agent_name=d.agent_name.strip()[:60], scope=d.scope, audience=d.audience,
                        tone=d.tone, must_answer_topics=topics, must_refuse_topics=dedupe(d.must_refuse_topics),
                        brief_demands=demands, clarifying_qa=qas, documents=infos)


def requirements_markdown(req: Requirements) -> str:
    lines = [f"# Requirements: {req.agent_name}", "", f"**Brief:** {req.brief}", "",
             f"**Scope:** {req.scope}", "", f"**Audience:** {req.audience}", "", f"**Tone:** {req.tone}", "",
             "## Must answer"]
    status = {g.topic: g for g in req.groundability}
    for t in req.must_answer_topics:
        g = status.get(t)
        lines.append(f"- {t}" + (f"  _(groundability: {g.status})_" if g else ""))
    lines += ["", "## Must refuse"] + [f"- {t}" for t in req.must_refuse_topics]
    if req.warnings:
        lines += ["", "## ⚠ Warnings"] + [f"- {w}" for w in req.warnings]
    lines += ["", "## Clarifying questions"]
    for qa in req.clarifying_qa:
        lines.append(f"- **Q:** {qa.question}\n  **A:** {qa.answer}  _({qa.answered_by})_")
    if req.groundability:
        lines += ["", "## Groundability check", "", "| Topic | Status | Top similarity | Evidence |", "|---|---|---|---|"]
        for g in req.groundability:
            ev = truncate(g.evidence[0].snippet, 120).replace("|", "/") + f" ({g.evidence[0].source})" if g.evidence else g.note
            lines.append(f"| {g.topic} | **{g.status}** | {g.top_similarity:.2f} | {ev} |")
    lines += ["", "## Documents"] + [f"- `{d.source}` ({d.type}): {d.summary}" for d in req.documents]
    return "\n".join(lines) + "\n"


def run_intake(brief: str, docs: list[Doc], answers_file: str | None, interactive: bool) -> Requirements:
    console.print("[bold]Intake[/] inspecting documents ...")
    infos = inspect_documents(docs)
    overview = docs_overview(infos)
    questions = generate_questions(brief, overview)
    console.print(f"[bold]Intake[/] {len(questions)} clarifying question(s)")
    qas = collect_answers(questions, answers_file, interactive)
    for qa in qas:
        console.print(f"  [cyan]Q:[/] {escape(qa.question)}\n  [green]A:[/] {escape(qa.answer)} [dim]({qa.answered_by})[/]")
    return draft_requirements(brief, overview, qas, infos)
