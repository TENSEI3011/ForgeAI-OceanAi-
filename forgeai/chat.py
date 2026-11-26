"""Requirement 8: a minimal, generic chat runner. Loads ANY agent definition produced by the factory.

  python chat.py runs/<name>/agent_definition_final.json
  commands: /sources (retrieved chunks of the last answer), /tools, /prompt, /reset, /quit
"""
from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .llm import stage
from .runner import AgentRunner, load_definition
from .textutil import truncate

console = Console()


def chat_loop(definition_path: str) -> None:
    d = load_definition(definition_path)
    runner = AgentRunner(d)
    console.print(Panel(f"[bold]{d.name}[/] (v{d.version})\n{d.description}\n\ndocuments: {', '.join(runner.sources)}\n"
                        f"tools: {', '.join(d.tools) or 'none'}\n\n/sources /tools /prompt /reset /quit",
                        title="ForgeAI chat runner"))
    history: list[dict] = []
    last = None
    while True:
        try:
            q = console.input("[bold cyan]you> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q in {"/quit", "/exit", "/q"}:
            break
        if q == "/reset":
            history, last = [], None
            console.print("[dim]conversation cleared[/]")
            continue
        if q == "/prompt":
            console.print(Panel(d.system_prompt, title="system prompt"))
            continue
        if q in {"/sources", "/tools"}:
            if not last:
                console.print("[dim]ask something first[/]")
            elif q == "/sources":
                for i, c in enumerate(last.retrieved, 1):
                    console.print(f"[bold][{i}] {c.source}[/] score={c.score} cosine={c.dense}\n{truncate(c.text, 400)}\n")
                if not last.retrieved:
                    console.print("[dim]nothing passed the retrieval gate[/]")
            else:
                for t in last.tools_called:
                    console.print(f"[bold]{t.name}[/]({t.args}) -> {truncate(t.result, 500)}")
                if not last.tools_called:
                    console.print("[dim]no tools called[/]")
            continue
        with stage("chat"), console.status("thinking..."):
            last = runner.answer(q, history)
        console.print(Panel(Markdown(last.answer), title=f"{d.name}", subtitle=f"{last.latency_s:.1f}s"
                            + (f" | tools: {', '.join(t.name for t in last.tools_called)}" if last.tools_called else "")))
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": last.answer}]
