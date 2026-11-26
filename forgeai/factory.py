"""The factory: brief + documents -> tested agent + honest report.

  intake -> groundability guard -> [human checkpoint] -> generate -> evalgen
         -> baseline eval -> critic-optimizer loop -> report

Every stage writes its artifact into the run folder as soon as it finishes, so a crash still
leaves evidence. Stage failures are logged to errors.log and run_status.json.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path
from typing import Any, Callable, TypeVar

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel

from .evalgen import EvalGenerator, save_evals
from .generator import choose_retrieval, generate_definition
from .groundability import GroundabilityAbort, run_groundability
from .ingest import load_documents
from .intake import requirements_markdown, run_intake
from .judge import evaluate
from .llm import CALL_LOG, SETTINGS, check_backend, get_stats, reset_stats, stage
from .optimizer import Optimizer, save_iteration_log
from .report import write_report, write_scorecards
from .runner import get_index
from .schemas import AgentAnswer, AgentDefinition, Requirements, Scorecard

console = Console()
T = TypeVar("T")


def _dump(path: Path, obj: Any) -> None:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


class Run:
    """Bookkeeping for one factory run folder."""

    def __init__(self, out_dir: Path):
        self.out = out_dir
        self.status: dict[str, Any] = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "stages": {}}

    def save_status(self) -> None:
        self.status["run_stats"] = get_stats().to_dict()
        _dump(self.out / "run_status.json", self.status)
        _dump(self.out / "run_stats.json", get_stats().to_dict())

    def stage(self, name: str, fn: Callable[[], T]) -> T:
        console.rule(f"[bold blue]{name}")
        t0 = time.time()
        try:
            with stage(name):
                result = fn()
            self.status["stages"][name] = {"status": "ok", "seconds": round(time.time() - t0, 1)}
            return result
        except Exception as exc:
            self.status["stages"][name] = {"status": f"failed: {type(exc).__name__}: {exc}",
                                           "seconds": round(time.time() - t0, 1)}
            with open(self.out / "errors.log", "a", encoding="utf-8") as fh:
                fh.write(f"[{name}] {traceback.format_exc()}\n")
            raise
        finally:
            self.save_status()


def _approve(req: Requirements, out: Path) -> Requirements:
    """Human checkpoint: accept, edit (requirements.json) or abort before generation."""
    console.print(Panel(Markdown(requirements_markdown(req)), title="Requirements for approval"))
    while True:
        choice = input("Approve requirements? [y]es / [e]dit / [a]bort: ").strip().lower() or "y"
        if choice.startswith("a"):
            raise SystemExit("aborted by requester at the requirements checkpoint")
        if choice.startswith("y"):
            return req
        console.print(f"Edit [bold]{out / 'requirements.json'}[/] in any editor, save it, then press Enter.")
        input()
        try:
            req = Requirements.model_validate_json((out / "requirements.json").read_text(encoding="utf-8-sig"))
            (out / "requirements.md").write_text(requirements_markdown(req), encoding="utf-8")
            console.print(Panel(Markdown(requirements_markdown(req)), title="Edited requirements"))
        except Exception as exc:
            console.print(f"[red]Invalid requirements.json: {exc}[/]")


def build(brief: str, docs_dir: str, out_dir: str, answers: str | None = None, interactive: bool = False,
          approve: bool = False, max_iters: int = 3, n_evals: int = 24, max_tokens: int | None = None,
          max_seconds: float | None = None, tournament: bool = False) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    reset_stats(max_tokens, max_seconds)
    CALL_LOG["path"] = out / "llm_calls.jsonl"
    CALL_LOG["path"].write_text("", encoding="utf-8")
    run = Run(out)
    (out / "brief.txt").write_text(brief, encoding="utf-8")

    problems = check_backend()
    for p in problems:
        console.print(f"[yellow]preflight:[/] {p}")
    if any("cannot reach" in p or "not pulled (run" in p for p in problems):
        console.print("[red]Backend not ready; aborting.[/]")
        return 1
    console.print(Panel(f"[bold]ForgeAI[/] building an agent\nbrief: {escape(brief)}\ndocs: {docs_dir}\nout: {out}\n"
                        f"model: {SETTINGS.model} | judge: {SETTINGS.judge_model} | backend: {SETTINGS.backend}"))

    docs, skipped = load_documents(docs_dir)
    if skipped:
        console.print(f"[yellow]skipped files:[/] {skipped}")
    if not docs:
        console.print("[red]No readable documents found.[/]")
        return 1
    docs_rel = Path(os.path.relpath(Path(docs_dir).resolve(), Path.cwd())).as_posix()
    run.status["documents"] = {"loaded": [d.source for d in docs], "skipped": skipped}

    # 1. intake -------------------------------------------------------------------------
    req = run.stage("intake", lambda: run_intake(brief, docs, answers, interactive))
    _dump(out / "requirements.json", req)

    # 2. groundability guard -------------------------------------------------------------
    chunking, _, _ = choose_retrieval(docs)
    _, chunks, index = get_index(docs_rel, chunking.chunk_size, chunking.chunk_overlap)
    try:
        req = run.stage("groundability", lambda: run_groundability(req, index))
    except GroundabilityAbort as exc:
        _dump(out / "requirements.json", req)
        _dump(out / "groundability.json", [g.model_dump() for g in req.groundability])
        (out / "requirements.md").write_text(requirements_markdown(req), encoding="utf-8")
        (out / "REPORT.md").write_text(f"# ForgeAI report: build STOPPED at the groundability guard\n\n{exc}\n\n"
                                       "See `requirements.md` for the per-topic evidence.\n", encoding="utf-8")
        console.print(f"[red bold]Stopped by the groundability guard:[/] {exc}")
        return 2
    _dump(out / "requirements.json", req)
    _dump(out / "groundability.json", [g.model_dump() for g in req.groundability])
    (out / "requirements.md").write_text(requirements_markdown(req), encoding="utf-8")
    if approve:
        req = _approve(req, out)
        _dump(out / "requirements.json", req)

    # 3. generate ------------------------------------------------------------------------
    definition, meta = run.stage("generate", lambda: generate_definition(
        req, docs, docs_rel, (out / "requirements.json").as_posix()))
    _dump(out / "agent_definition_v1.json", definition)
    _dump(out / "tool_selection.json", meta)
    # the generator may have reconciled tool-served topics with the tools actually attached
    _dump(out / "requirements.json", req)
    _dump(out / "groundability.json", [g.model_dump() for g in req.groundability])
    (out / "requirements.md").write_text(requirements_markdown(req), encoding="utf-8")

    # 4. eval generation -----------------------------------------------------------------
    _, chunks, index = get_index(docs_rel, definition.chunking.chunk_size, definition.chunking.chunk_overlap)
    gen = EvalGenerator(req, definition, docs, chunks, index)
    eg = run.stage("evalgen", lambda: gen.generate(n_evals))
    save_evals(eg, out)
    cases = eg.cases
    console.print(f"  {len(cases)} verified cases, {len(eg.dropped)} dropped")
    evalgen_log = json.loads((out / "evals_generation_log.json").read_text(encoding="utf-8"))

    def save_results(it: int, card: Scorecard, answers_: list[AgentAnswer]) -> None:
        _dump(out / f"results_iter{it}.json", {"scorecard": card.model_dump(),
                                               "answers": [a.model_dump() for a in answers_]})

    def save_definition(d: AgentDefinition) -> None:
        _dump(out / f"agent_definition_v{d.version}.json", d)

    # 4b. optional prompt tournament (stretch): the dev split picks the system prompt ------
    extra_sections: list[str] = []
    if tournament:
        from .tournament import run_tournament, tournament_markdown
        definition, tres = run.stage("tournament", lambda: run_tournament(req, docs, definition, cases))
        _dump(out / "tournament.json", tres)
        _dump(out / "agent_definition_v1.json", definition)
        extra_sections.append(tournament_markdown(tres))
        console.print(f"  tournament winner: {tres['winner']}")

    # 5. baseline ------------------------------------------------------------------------
    card0, answers0 = run.stage("baseline_eval", lambda: evaluate(definition, cases, 0))
    save_results(0, card0, answers0)
    console.print(f"  baseline: {card0.pass_rate:.0%} pass (dev {card0.dev_pass_rate:.0%}, holdout "
                  f"{card0.holdout_pass_rate:.0%}); failures {card0.failures_by_category}")

    # 6. optimise ------------------------------------------------------------------------
    opt = Optimizer(cases, out)
    final_def, cards, records, stop_reason = run.stage(
        "optimize", lambda: opt.run(definition, card0, answers0, max_iters, save_definition, save_results))
    save_iteration_log(records, opt.rejected_patches, stop_reason, out)
    _dump(out / "agent_definition_final.json", final_def)
    final_card = next(c for c in reversed(cards) if c.definition_version == final_def.version)
    final_answers = [AgentAnswer.model_validate(a) for a in json.loads(
        (out / f"results_iter{final_card.iteration}.json").read_text(encoding="utf-8"))["answers"]]

    # 7. report --------------------------------------------------------------------------
    write_scorecards(cards, records, out)
    run.stage("report", lambda: write_report(out, req, final_def, meta["tool_decisions"], cases, evalgen_log, cards,
                                             records, stop_reason, final_answers, extra_sections))
    run.status["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    run.status["final"] = {"definition_version": final_def.version, "pass_rate": final_card.pass_rate,
                           "holdout_pass_rate": final_card.holdout_pass_rate, "stop_reason": stop_reason}
    run.save_status()
    CALL_LOG["path"] = None
    console.print(Panel(f"[bold green]Done.[/] final v{final_def.version}: {final_card.pass_rate:.0%} pass "
                        f"(baseline {card0.pass_rate:.0%}); holdout {final_card.holdout_pass_rate:.0%}\n"
                        f"report: {out / 'REPORT.md'}\nchat:   python chat.py {out / 'agent_definition_final.json'}"))
    return 0
