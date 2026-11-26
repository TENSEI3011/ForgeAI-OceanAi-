"""Generic agent runtime: executes ANY AgentDefinition (used by chat AND by the evals).

Flow for one question:
  1. retrieve top_k chunks (optional LLM query rewrite) and apply the min_score gate
  2. if the definition attaches tools: a small planner loop (max 3 steps) that emits
     {"action": "call"|"answer", "tool": ..., "args": {...}}; only attached tools can run
  3. if there is no context and no tool output -> abstain with the refusal phrase (no LLM call)
  4. answer with system prompt + numbered context + tool results + output contract
  5. post-process: extract citations, detect refusal, record latency
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from rapidfuzz import process

from .ingest import Chunk, Doc, chunk_documents, load_documents
from .llm import LLMJSONError, llm, llm_json, render
from .retrieval import Index
from .schemas import AgentAnswer, AgentDefinition, RetrievedChunk, ToolCall, ToolStepOut
from .textutil import is_refusal, truncate
from .tools.csv_lookup import list_tables
from .tools.registry import TOOLS, run_tool

MAX_TOOL_STEPS = 3
MAX_CONTEXT_CHARS = 9000

_INDEX_CACHE: dict[tuple[str, int, int], tuple[list[Doc], list[Chunk], Index]] = {}


def get_index(docs_dir: str, chunk_size: int, overlap: int) -> tuple[list[Doc], list[Chunk], Index]:
    """Build (or reuse) the index for a docs folder + chunking config."""
    key = (str(Path(docs_dir).resolve()), chunk_size, overlap)
    if key not in _INDEX_CACHE:
        docs, _ = load_documents(docs_dir)
        chunks = chunk_documents(docs, chunk_size, overlap)
        _INDEX_CACHE[key] = (docs, chunks, Index(chunks))
    return _INDEX_CACHE[key]


def contract_instructions(d: AgentDefinition) -> str:
    c = d.output_contract
    lines = []
    if c.require_citations:
        lines.append("After every sentence that states a fact, cite its file like this: [source: <file name>].")
    lines.append(f'If the passages and tool results do not contain the answer, reply exactly: "{c.refusal_phrase}"')
    lines.append(f"Keep the answer under {c.max_words} words.")
    if c.format == "json":
        fields = c.fields or ["answer", "sources"]
        lines.append(f"Return a JSON object with keys: {', '.join(fields)}.")
    return "\n".join(f"- {l}" for l in lines)


class AgentRunner:
    def __init__(self, definition: AgentDefinition):
        self.d = definition
        self.docs_dir = definition.documents_dir
        self.docs, self.chunks, self.index = get_index(
            self.docs_dir, definition.chunking.chunk_size, definition.chunking.chunk_overlap)
        self.sources = sorted({doc.source for doc in self.docs})
        self.tables = list_tables(self.docs_dir) if "csv_lookup" in definition.tools else {}

    # -------------------------------------------------------------- retrieval
    def retrieve(self, question: str, history: list[dict] | None = None) -> tuple[list[RetrievedChunk], int, str]:
        r = self.d.retrieval
        query = question
        if history and len(question.split()) < 8:   # short follow-ups inherit the last user turn
            last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
            query = f"{last_user} {question}"
        extra: list[str] = []
        rewritten = ""
        if r.query_rewrite:
            rewritten = llm(render("runner_query_rewrite", question=query), temperature=0.0, max_tokens=60).strip()
            rewritten = rewritten.strip('"').split("\n")[0][:200]
            extra.append(rewritten)
        hits, filtered = self.index.search(query, r.top_k, r.mode, r.min_score, extra)
        chunks = [RetrievedChunk(chunk_id=h.chunk.chunk_id, source=h.chunk.source, text=h.chunk.text,
                                 score=round(h.score, 4), dense=round(h.dense, 4), page=h.chunk.page) for h in hits]
        return chunks, filtered, rewritten

    @staticmethod
    def format_context(chunks: list[RetrievedChunk], per_chunk: int) -> str:
        parts, used = [], 0
        for i, c in enumerate(chunks, 1):
            where = f", page {c.page}" if c.page else ""
            block = f"[{i}] source: {c.source}{where}\n{truncate(c.text, per_chunk)}"
            if used + len(block) > MAX_CONTEXT_CHARS:
                break
            parts.append(block)
            used += len(block)
        return "\n\n".join(parts) if parts else "(no relevant passages found)"

    # -------------------------------------------------------------- tools
    def _tool_menu(self) -> str:
        lines = []
        for name in self.d.tools:
            spec = TOOLS[name]
            params = ", ".join(f'"{k}": {v}' for k, v in spec.params.items()) or "none"
            lines.append(f"- {name}: {spec.description} Args: {{{params}}}")
            if name == "csv_lookup" and self.tables:
                for f, cols in self.tables.items():
                    lines.append(f"    table {f} columns: {', '.join(cols)}")
        return "\n".join(lines)

    def _tool_loop(self, question: str, context: str) -> list[ToolCall]:
        calls: list[ToolCall] = []
        seen: set[str] = set()
        for _ in range(MAX_TOOL_STEPS):
            results = "\n".join(f"- {c.name}({json.dumps(c.args)}) -> {truncate(c.result, 800)}" for c in calls) or "(none yet)"
            try:
                step = llm_json(render("runner_tool_step", tools=self._tool_menu(), context=truncate(context, 2500),
                                       results=results, question=question), ToolStepOut, temperature=0.0, max_tokens=160)
            except LLMJSONError:
                break
            if step.action != "call" or not step.tool:
                break
            sig = f"{step.tool}:{json.dumps(step.args, sort_keys=True)}"
            if sig in seen:          # the model is looping on the same call
                break
            seen.add(sig)
            result, ok = run_tool(step.tool, step.args, {"documents_dir": self.docs_dir}, self.d.tools)
            calls.append(ToolCall(name=step.tool, args=step.args, result=result, ok=ok))
        return calls

    # -------------------------------------------------------------- answer
    def answer(self, question: str, history: list[dict] | None = None) -> AgentAnswer:
        t0 = time.time()
        retrieved, _filtered, rewritten = self.retrieve(question, history)
        per_chunk = self.d.chunking.chunk_size + 200
        context = self.format_context(retrieved, per_chunk)
        tool_calls = self._tool_loop(question, context) if self.d.tools else []
        good_tools = [c for c in tool_calls if c.ok]
        refusal = self.d.output_contract.refusal_phrase

        if not retrieved and not good_tools:
            # Nothing relevant passed the gate: abstain deterministically instead of guessing.
            return AgentAnswer(question=question, answer=refusal, retrieved=[], tools_called=tool_calls,
                               refused=True, abstained_no_context=True, latency_s=round(time.time() - t0, 2),
                               rewritten_query=rewritten)

        tool_text = "\n".join(f"- {c.name}({json.dumps(c.args)}) returned:\n{truncate(c.result, 1500)}"
                              for c in tool_calls) or "(no tools used)"
        conv = ""
        if history:
            conv = "\n".join(f"{m['role']}: {truncate(m['content'], 300)}" for m in history[-4:])
        prompt = render("runner_answer", context=context, tool_results=tool_text,
                        conversation=conv or "(new conversation)", question=question,
                        contract=contract_instructions(self.d))
        text = llm(prompt, system=self.d.system_prompt, temperature=self.d.llm.temperature,
                   max_tokens=min(900, int(self.d.output_contract.max_words * 2.5) + 80)).strip()
        return AgentAnswer(question=question, answer=text, cited_sources=self.extract_citations(text),
                           retrieved=retrieved, tools_called=tool_calls, refused=is_refusal(text, refusal),
                           latency_s=round(time.time() - t0, 2), rewritten_query=rewritten)

    def extract_citations(self, text: str) -> list[str]:
        """Map every [source: ...] mention to a real file name (fuzzy), keeping unknown ones visible."""
        found: list[str] = []
        for group in re.findall(r"\[\s*sources?\s*:\s*([^\]]+)\]", text, flags=re.I):
            for name in re.split(r"[;,]|\band\b", group):
                name = re.sub(r",?\s*(page|p\.|row)\s*\d+.*$", "", name.strip(), flags=re.I).strip(" '\"`")
                if not name:
                    continue
                tool = next((t for t in self.d.tools if t.replace("_", " ") in name.lower().replace("_", " ")), None)
                best = process.extractOne(name, self.sources) if self.sources else None
                if tool and not (best and best[1] >= 90):
                    resolved = f"tool:{tool}"          # citing an attached tool's result is legitimate
                else:
                    resolved = best[0] if best and best[1] >= 80 else f"UNKNOWN:{name}"
                if resolved not in found:
                    found.append(resolved)
        return found


def load_definition(path: str | Path) -> AgentDefinition:
    # utf-8-sig: tolerate the byte-order mark Windows editors/PowerShell add
    return AgentDefinition.model_validate_json(Path(path).read_text(encoding="utf-8-sig"))


def answer_to_dict(a: AgentAnswer) -> dict[str, Any]:
    return a.model_dump()
