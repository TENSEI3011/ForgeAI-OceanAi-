"""Command line interface.

  python -m forgeai build --brief "..." --docs DIR --out runs/NAME [--answers FILE] [--non-interactive]
                          [--approve] [--max-iters 3] [--n-evals 24] [--max-tokens N] [--max-seconds N]
  python -m forgeai eval  --definition DEF.json --evals EVALS.json [--out DIR] [--compare results_iterN.json]
  python -m forgeai chat  DEF.json
  python -m forgeai check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _cmd_build(a: argparse.Namespace) -> int:
    from .factory import build
    brief = a.brief or Path(a.brief_file).read_text(encoding="utf-8").strip()
    interactive = not a.non_interactive and not a.answers
    return build(brief, a.docs, a.out, answers=a.answers, interactive=interactive, approve=a.approve,
                 max_iters=a.max_iters, n_evals=a.n_evals, max_tokens=a.max_tokens, max_seconds=a.max_seconds,
                 tournament=a.tournament)


def _cmd_eval(a: argparse.Namespace) -> int:
    """Re-run an eval set against a definition. With --compare: regression report vs older results."""
    from rich.console import Console

    from .evalgen import load_evals
    from .judge import evaluate
    from .report import scorecard_table
    from .runner import load_definition
    console = Console()
    d = load_definition(a.definition)
    cases = load_evals(a.evals)
    card, answers = evaluate(d, cases, 0)
    console.print(scorecard_table([card], []))
    out = Path(a.out) if a.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "eval_results.json").write_text(json.dumps({"scorecard": card.model_dump(), "answers": [
            x.model_dump() for x in answers]}, indent=2, ensure_ascii=False), encoding="utf-8")
    if a.compare:
        old = json.loads(Path(a.compare).read_text(encoding="utf-8"))["scorecard"]["results"]
        old_pass = {r["case_id"]: r["passed"] for r in old}
        broke = [r for r in card.results if old_pass.get(r.case_id) and not r.passed]
        fixed = [r for r in card.results if old_pass.get(r.case_id) is False and r.passed]
        lines = [f"# {a.title}", "", f"Definition `{a.definition}` on eval set `{a.evals}`, compared with results "
                 f"`{a.compare}`.", "",
                 f"Pass rate now **{card.pass_rate:.0%}** ({sum(r.passed for r in card.results)}/{card.n_cases}) vs "
                 f"before **{sum(old_pass.values()) / max(1, len(old_pass)):.0%}**. Failures now by category: "
                 f"{card.failures_by_category or 'none'}.", "",
                 f"## Passed before, fails now ({len(broke)})"]
        lines += [f"- **{r.case_id}** ({r.type}): {r.question}\n  - answer: {' '.join(r.answer.split())[:300]}\n"
                  f"  - {r.failure_category}: {r.diagnosis}" for r in broke]
        lines += ["", f"## Failed before, passes now ({len(fixed)})"] + [f"- **{r.case_id}**: {r.question}" for r in fixed]
        text = "\n".join(lines) + "\n"
        console.print(text)
        if out:
            (out / "COMPARISON.md").write_text(text, encoding="utf-8")
    return 0


def _cmd_chat(a: argparse.Namespace) -> int:
    from .chat import chat_loop
    chat_loop(a.definition)
    return 0


def _cmd_summary(a: argparse.Namespace) -> int:
    """Print a Markdown results table computed from run folders (used for the README)."""
    print("| Run | Tools attached | Groundability flags | Evals (dropped) | Baseline | Final | Holdout (final) | Iterations | Stop reason |")
    print("|---|---|---|---|---|---|---|---|---|")
    for run in a.runs:
        r = Path(run)
        cards = json.loads((r / "scorecard.json").read_text(encoding="utf-8"))
        final_def = json.loads((r / "agent_definition_final.json").read_text(encoding="utf-8"))
        final = [c for c in cards if c["definition_version"] == final_def["version"]][-1]
        req = json.loads((r / "requirements.json").read_text(encoding="utf-8"))
        gen = json.loads((r / "evals_generation_log.json").read_text(encoding="utf-8"))
        it = json.loads((r / "iteration_log.json").read_text(encoding="utf-8"))
        flags = [g["topic"] for g in req.get("groundability", []) if g["status"] != "supported"]
        fmt = lambda c: f"{round(c['pass_rate'] * c['n_cases'])}/{c['n_cases']} ({c['pass_rate']:.0%})"  # noqa: E731
        print(f"| `{r.name}` | {', '.join(final_def['tools']) or 'none'} | {', '.join(flags) or 'none'} | "
              f"{gen['n_cases']} ({gen['n_dropped']}) | {fmt(cards[0])} | {fmt(final)} | "
              f"{final['holdout_pass_rate']:.0%} | {len(it['iterations'])} | {it['stop_reason']} |")
    return 0


def _cmd_check(_: argparse.Namespace) -> int:
    from .llm import SETTINGS, check_backend
    problems = check_backend()
    print(f"backend={SETTINGS.backend} model={SETTINGS.model} judge={SETTINGS.judge_model} embed={SETTINGS.embed_model}")
    print("\n".join(problems) if problems else "OK: backend ready")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="forgeai", description="ForgeAI: the agent that builds agents")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build, test and optimise an agent from a brief + documents")
    g = b.add_mutually_exclusive_group(required=True)
    g.add_argument("--brief", help="one-paragraph brief")
    g.add_argument("--brief-file", help="file containing the brief")
    b.add_argument("--docs", required=True, help="folder of documents")
    b.add_argument("--out", required=True, help="run folder, e.g. runs/my_agent")
    b.add_argument("--answers", help="requester notes JSON used to answer clarifying questions")
    b.add_argument("--non-interactive", action="store_true", help="never prompt; assume defaults")
    b.add_argument("--approve", action="store_true", help="human checkpoint before generation")
    b.add_argument("--max-iters", type=int, default=3)
    b.add_argument("--n-evals", type=int, default=24)
    b.add_argument("--max-tokens", type=int, default=None, help="token budget for the whole run")
    b.add_argument("--max-seconds", type=float, default=None, help="wall-time budget for the whole run")
    b.add_argument("--no-cache", action="store_true", help="disable the on-disk LLM response cache")
    b.add_argument("--tournament", action="store_true", help="stretch: 3 candidate prompts, dev evals pick the winner")
    b.set_defaults(fn=_cmd_build)

    e = sub.add_parser("eval", help="re-run an eval set (regression mode with --compare)")
    e.add_argument("--definition", required=True)
    e.add_argument("--evals", required=True)
    e.add_argument("--out")
    e.add_argument("--compare", help="older results_iterN.json to diff against")
    e.add_argument("--title", default="Regression report", help="title of COMPARISON.md")
    e.set_defaults(fn=_cmd_eval)

    c = sub.add_parser("chat", help="chat with a generated agent")
    c.add_argument("definition")
    c.set_defaults(fn=_cmd_chat)

    k = sub.add_parser("check", help="check the LLM backend")
    k.set_defaults(fn=_cmd_check)

    s = sub.add_parser("summary", help="Markdown results table from run folders")
    s.add_argument("runs", nargs="+")
    s.set_defaults(fn=_cmd_summary)

    args = p.parse_args(argv)
    if getattr(args, "no_cache", False):
        os.environ["FORGEAI_LLM_CACHE"] = "0"
        from .llm import SETTINGS
        SETTINGS.use_cache = False
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
