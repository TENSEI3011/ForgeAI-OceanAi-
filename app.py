"""ForgeAI web UI (optional stretch goal):  streamlit run app.py

Tabs: Factory (brief + documents -> run the factory with a live log), Runs (browse reports,
scorecards and iteration logs of any run) and Chat (talk to any generated agent definition).
The UI is a thin shell: the factory runs as the same CLI subprocess you would run by hand.
"""
from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
st.set_page_config(page_title="ForgeAI", page_icon="🛠️", layout="wide")

# Hosted deployments (e.g. Streamlit Community Cloud) pass settings such as LLM_BACKEND and GROQ_API_KEY as
# secrets. Expose them as environment variables BEFORE forgeai reads its configuration; the factory subprocess
# inherits them too. Locally there is no secrets file and .env is used as before.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float, bool)):
            os.environ[_k] = str(_v)     # secrets win, so a rotated API key replaces the old one
except Exception:
    pass
FACTORY_PASSWORD = os.getenv("FACTORY_PASSWORD", "")


@st.cache_resource(show_spinner="Preparing the demo documents (first start only)...")
def ensure_demo_docs() -> str:
    """The demo PDFs are not committed: rebuild them from demos/*/source/*.md if they are missing."""
    needed = [ROOT / "demos/hr_policy/docs/leave_policy.pdf", ROOT / "demos/hr_policy_v2/docs/leave_policy.pdf",
              ROOT / "demos/ship_spares/docs/supplier_terms_a.pdf"]
    if all(p.exists() for p in needed):
        return ""
    r = subprocess.run([sys.executable, "demos/synthesize.py", "--regression"], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return "" if r.returncode == 0 else f"Could not build the demo PDFs: {r.stderr[-400:]}"


_docs_problem = ensure_demo_docs()
if _docs_problem:
    st.warning(_docs_problem)


def run_dirs() -> list[Path]:
    return sorted([p for p in RUNS.glob("*") if (p / "brief.txt").exists()], key=lambda p: p.name)


st.title("ForgeAI: the agent that builds agents")
from forgeai.llm import SETTINGS, check_backend  # noqa: E402

# Settings are read once per process; take the current key on every run so a rotated key works at once
SETTINGS.groq_key = os.getenv("GROQ_API_KEY", SETTINGS.groq_key)

with st.sidebar:
    st.markdown(f"**Backend:** `{SETTINGS.backend}`  \n**Model:** `{SETTINGS.model}`  \n"
                f"**Judge:** `{SETTINGS.judge_model}`  \n**Embeddings:** `{SETTINGS.embed_id}`")
    problems = check_backend()
    if problems:   # a statement, not a bare expression: Streamlit "magic" would render the expression's value
        st.warning("\n".join(problems))
    else:
        st.success("backend ready")

tab_factory, tab_runs, tab_chat = st.tabs(["🏭 Factory", "📊 Runs", "💬 Chat"])

# ------------------------------------------------------------------ factory
with tab_factory:
    unlocked = True
    if FACTORY_PASSWORD:
        st.info("Building an agent uses the hosted model's quota, so the factory needs an access code. "
                "The Runs and Chat tabs are open to everyone.")
        code = st.text_input("Access code", type="password")
        unlocked = hmac.compare_digest(code.encode(), FACTORY_PASSWORD.encode())
        if code and not unlocked:
            st.error("Wrong access code.")
    brief = st.text_area("Brief (one paragraph)", height=110,
                         placeholder="I need an assistant that answers HR policy questions for shore staff.")
    demo_dirs = sorted(str(p.relative_to(ROOT).as_posix()) for p in (ROOT / "demos").glob("*/docs"))
    source = st.radio("Documents", ["Upload files", "Use an existing folder"], horizontal=True)
    docs_dir = None
    if source == "Upload files":
        files = st.file_uploader("PDF / TXT / MD / CSV / DOCX / HTML", accept_multiple_files=True)
    else:
        docs_dir = st.selectbox("Folder", demo_dirs)
        files = None
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("Run name", value=f"ui_{time.strftime('%Y%m%d_%H%M')}")
    n_evals = c2.number_input("Eval cases", 20, 40, 24)
    max_iters = c3.number_input("Max iterations", 0, 3, 3)
    if st.button("Build agent", type="primary", disabled=not brief.strip() or not unlocked):
        out = RUNS / name
        if files:
            docs_dir = str((out / "uploaded_docs").relative_to(ROOT))
            (ROOT / docs_dir).mkdir(parents=True, exist_ok=True)
            for f in files:
                (ROOT / docs_dir / Path(f.name).name).write_bytes(f.getbuffer())
        if not docs_dir:
            st.error("Add documents first.")
        else:
            cmd = [sys.executable, "-m", "forgeai", "build", "--brief", brief, "--docs", docs_dir, "--out",
                   str(out.relative_to(ROOT)), "--non-interactive", "--n-evals", str(n_evals),
                   "--max-iters", str(max_iters)]
            env = os.environ | {"PYTHONIOENCODING": "utf-8", "COLUMNS": "110", "NO_COLOR": "1"}
            log_box = st.empty()
            lines: list[str] = []
            with st.spinner("The factory is running unattended (this takes a while on a local model)..."):
                proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        encoding="utf-8", errors="replace", env=env)
                for line in proc.stdout:  # type: ignore[union-attr]
                    lines.append(line.rstrip())
                    log_box.code("\n".join(lines[-40:]))
                proc.wait()
            if (out / "REPORT.md").exists():
                st.success(f"Finished with exit code {proc.returncode}. Open the Runs tab for details.")
                st.markdown((out / "REPORT.md").read_text(encoding="utf-8"))
            else:
                st.error(f"Factory exited with code {proc.returncode}; see the log above.")

# ------------------------------------------------------------------ runs
with tab_runs:
    runs = run_dirs()
    if not runs:
        st.info("No runs yet.")
    else:
        run = st.selectbox("Run", runs, format_func=lambda p: p.name)
        st.caption((run / "brief.txt").read_text(encoding="utf-8"))
        view = st.radio("View", ["REPORT.md", "scorecard.md", "iteration_log.md", "requirements.md", "evals.json",
                                 "agent_definition_final.json"], horizontal=True)
        path = run / view
        if not path.exists():
            st.warning(f"{view} not found in this run")
        elif view.endswith(".md"):
            st.markdown(path.read_text(encoding="utf-8"))
        elif view == "evals.json":
            st.dataframe([{k: (", ".join(v) if isinstance(v, list) else v) for k, v in c.items()
                           if k in ("id", "type", "split", "question", "expected_facts", "expected_sources")}
                          for c in json.loads(path.read_text(encoding="utf-8"))], use_container_width=True)
        else:
            st.json(json.loads(path.read_text(encoding="utf-8")))

# ------------------------------------------------------------------ chat
with tab_chat:
    defs = sorted(RUNS.glob("*/agent_definition_final.json"))
    if not defs:
        st.info("Build an agent first.")
    else:
        from forgeai.runner import AgentRunner, load_definition
        chosen = st.selectbox("Agent", defs, format_func=lambda p: p.parent.name)
        key = f"chat::{chosen}"
        if st.session_state.get("chat_key") != key:
            st.session_state.update(chat_key=key, history=[], answers=[])
        definition = load_definition(chosen)

        @st.cache_resource(show_spinner="Building the agent's index...")
        def get_runner(path: str, version: int) -> AgentRunner:
            return AgentRunner(load_definition(path))

        runner = get_runner(str(chosen), definition.version)
        st.caption(f"{definition.name} v{definition.version} | tools: {', '.join(definition.tools) or 'none'} | "
                   f"documents: {', '.join(runner.sources)}")
        for i, m in enumerate(st.session_state.history):
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m["role"] == "assistant":
                    a = st.session_state.answers[i // 2]
                    with st.expander(f"sources ({len(a.retrieved)}) / tools ({len(a.tools_called)}) / {a.latency_s}s"):
                        for c in a.retrieved:
                            st.markdown(f"**{c.source}** (score {c.score}, cosine {c.dense})\n\n> {c.text[:400]}")
                        for t in a.tools_called:
                            st.code(f"{t.name}({t.args}) -> {t.result[:400]}")
        q = st.chat_input("Ask the agent...")
        if q:
            import forgeai.llm as _llm
            # getattr: after a hot redeploy Streamlit can keep an older forgeai.llm in memory; never crash on it
            quota_error = getattr(_llm, "LLMQuotaError", None)
            try:
                with st.spinner("thinking..."):
                    ans = runner.answer(q, st.session_state.history)
            except _llm.LLMError as exc:
                if quota_error is not None and isinstance(exc, quota_error):
                    st.warning("The hosted model's free daily quota is used up right now. It refills gradually, so "
                               "please try again later. (Run locally with Ollama, ForgeAI has no quota.)")
                else:
                    st.warning(f"The model could not answer just now ({str(exc)[:160]}). Please try again in a minute.")
                st.stop()
            st.session_state.history += [{"role": "user", "content": q}, {"role": "assistant", "content": ans.answer}]
            st.session_state.answers.append(ans)
            st.rerun()
