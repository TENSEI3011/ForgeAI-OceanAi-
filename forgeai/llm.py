"""The ONLY place ForgeAI talks to a language model.

* llm()       -> plain text completion
* llm_json()  -> completion validated against a Pydantic schema, with repair-and-retry
* embed()     -> sentence embeddings (Ollama all-minilm, hashed fallback)
* render()    -> load a prompt template from prompts/*.md and fill {{placeholders}}

Every call is timed, token-counted and attributed to a pipeline stage (STATS), optionally
cached on disk (so re-runs are cheap and reproducible), and appended to a per-run call log
so every prompt the factory used is committed as evidence.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Type, TypeVar

import numpy as np
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
CACHE_DIR = ROOT / ".cache"

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------- configuration
FASTEMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"   # same model as Ollama's all-minilm
# Hosted defaults (Groq): generator and judge from DIFFERENT model families (self-preference defence)
GROQ_DEFAULT_MODEL = "qwen/qwen3.8-27b"
GROQ_DEFAULT_JUDGE = "openai/gpt-oss-20b"
GROQ_REASONING_PREFIXES = ("openai/gpt-oss",)


@dataclass
class Settings:
    backend: str = os.getenv("LLM_BACKEND", "ollama").lower()
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
    num_ctx: int = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
    embed_model: str = os.getenv("EMBED_MODEL", "all-minilm")
    # ollama (default) or fastembed: the same all-MiniLM-L6-v2 run in-process (ONNX, CPU), for hosting without Ollama
    embed_backend: str = os.getenv("EMBED_BACKEND", "ollama").lower()
    groq_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL") or GROQ_DEFAULT_MODEL
    use_cache: bool = os.getenv("FORGEAI_LLM_CACHE", "1") == "1"

    @property
    def model(self) -> str:
        return self.groq_model if self.backend == "groq" else self.ollama_model

    @property
    def embed_id(self) -> str:
        """Names the embedding source (also part of the embedding cache key, so the two never mix)."""
        return FASTEMBED_MODEL if self.embed_backend == "fastembed" else self.embed_model

    @property
    def judge_model(self) -> str:
        if self.backend == "groq":
            return os.getenv("GROQ_JUDGE_MODEL") or GROQ_DEFAULT_JUDGE
        return os.getenv("JUDGE_MODEL") or self.ollama_model


SETTINGS = Settings()


# ---------------------------------------------------------------- run statistics
@dataclass
class StageStats:
    calls: int = 0
    cached_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0


@dataclass
class RunStats:
    """Global counters for one factory run. Also enforces the optional budget."""
    stages: dict[str, StageStats] = field(default_factory=dict)
    started: float = field(default_factory=time.time)
    max_tokens: int | None = None
    max_seconds: float | None = None
    warnings: list[str] = field(default_factory=list)

    def record(self, stage: str, prompt_toks: int, completion_toks: int, seconds: float, cached: bool) -> None:
        s = self.stages.setdefault(stage, StageStats())
        s.calls += 1
        s.cached_calls += int(cached)
        s.prompt_tokens += prompt_toks
        s.completion_tokens += completion_toks
        s.seconds += seconds

    @property
    def total_tokens(self) -> int:
        return sum(s.prompt_tokens + s.completion_tokens for s in self.stages.values())

    @property
    def elapsed(self) -> float:
        return time.time() - self.started

    def budget_left(self) -> tuple[bool, str]:
        if self.max_tokens and self.total_tokens >= self.max_tokens:
            return False, f"token budget exhausted ({self.total_tokens} >= {self.max_tokens})"
        if self.max_seconds and self.elapsed >= self.max_seconds:
            return False, f"time budget exhausted ({self.elapsed:.0f}s >= {self.max_seconds:.0f}s)"
        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": SETTINGS.backend,
            "model": SETTINGS.model,
            "judge_model": SETTINGS.judge_model,
            "embed_model": SETTINGS.embed_id,
            "wall_seconds": round(self.elapsed, 1),
            "total_calls": sum(s.calls for s in self.stages.values()),
            "total_cached_calls": sum(s.cached_calls for s in self.stages.values()),
            "total_tokens": self.total_tokens,
            "budget": {"max_tokens": self.max_tokens, "max_seconds": self.max_seconds},
            "by_stage": {k: vars(v) | {"seconds": round(v.seconds, 1)} for k, v in self.stages.items()},
            "warnings": self.warnings,
        }


STATS = RunStats()
_STAGE = threading.local()
CALL_LOG: dict[str, Path | None] = {"path": None}


def reset_stats(max_tokens: int | None = None, max_seconds: float | None = None) -> RunStats:
    global STATS
    STATS = RunStats(max_tokens=max_tokens, max_seconds=max_seconds)
    return STATS


def get_stats() -> RunStats:
    return STATS


@contextlib.contextmanager
def stage(name: str) -> Iterator[None]:
    """Attribute every LLM call inside the block to a pipeline stage."""
    prev = getattr(_STAGE, "name", "other")
    _STAGE.name = name
    try:
        yield
    finally:
        _STAGE.name = prev


def current_stage() -> str:
    return getattr(_STAGE, "name", "other")


# ---------------------------------------------------------------- disk cache
class _Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
        self.lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self.lock:
            row = self.db.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, value: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, value))
            self.db.commit()


_LLM_CACHE: _Cache | None = None


def _cache() -> _Cache:
    global _LLM_CACHE
    if _LLM_CACHE is None:
        _LLM_CACHE = _Cache(CACHE_DIR / "llm.sqlite")
    return _LLM_CACHE


# ---------------------------------------------------------------- prompts
def render(name: str, **values: Any) -> str:
    """Load prompts/<name>.md and substitute {{key}} placeholders."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, val in values.items():
        if not isinstance(val, str):
            val = json.dumps(val, indent=2, ensure_ascii=False)
        text = text.replace("{{" + key + "}}", val)
    leftover = re.findall(r"\{\{(\w+)\}\}", text)
    if leftover:
        raise KeyError(f"prompt {name} has unfilled placeholders: {leftover}")
    return text


# ---------------------------------------------------------------- backends
class LLMError(RuntimeError):
    pass


def _post_with_retry(url: str, payload: dict, attempts: int = 3, timeout: float = 600) -> requests.Response:
    """POST with a hard timeout and retries, so a hung or dropped request cannot stall a run forever."""
    for i in range(attempts):
        try:
            return requests.post(url, json=payload, timeout=(10, timeout))
        except (requests.Timeout, requests.ConnectionError) as exc:
            if i == attempts - 1:
                raise LLMError(f"LLM request failed after {attempts} attempts: {exc}") from exc
            STATS.warnings.append(f"[{current_stage()}] LLM request retried after: {type(exc).__name__}")
            time.sleep(5 * (i + 1))
    raise AssertionError("unreachable")


def _ollama_chat(messages: list[dict], model: str, temperature: float, max_tokens: int,
                 fmt: Any) -> tuple[str, int, int]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "num_ctx": SETTINGS.num_ctx,
                    "num_predict": max_tokens, "seed": 7},
    }
    if fmt is not None:
        payload["format"] = fmt
    r = _post_with_retry(f"{SETTINGS.ollama_url}/api/chat", payload)
    if r.status_code != 200 and isinstance(fmt, dict):
        # Some schemas are too complex for the grammar engine: fall back to plain JSON mode.
        payload["format"] = "json"
        r = _post_with_retry(f"{SETTINGS.ollama_url}/api/chat", payload)
    if r.status_code != 200:
        raise LLMError(f"Ollama error {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["message"]["content"], data.get("prompt_eval_count", 0), data.get("eval_count", 0)


class LLMQuotaError(LLMError):
    """Every configured hosted model has used up its daily quota (free tiers refill gradually)."""


# Tried in order when a Groq model's DAILY quota is used up (each model has its own quota)
GROQ_FALLBACK_MODELS = [m.strip() for m in os.getenv(
    "GROQ_FALLBACK_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b").split(",") if m.strip()]
_GROQ_EXHAUSTED: dict[str, float] = {}       # model -> time until which its daily quota is used up
_GROQ_FALLBACK_NOTED: set[tuple[str, str]] = set()


def _retry_after(r: requests.Response) -> float:
    """Seconds Groq asks us to wait: the retry-after header, or 'try again in 3m57.1s' in the message."""
    try:
        return float(r.headers.get("retry-after", ""))
    except ValueError:
        pass
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", r.text)
    if m and any(m.groups()):
        h, mi, s = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mi * 60 + s
    return 10.0


def _groq_chat(messages: list[dict], model: str, temperature: float, max_tokens: int,
               fmt: Any) -> tuple[str, int, int]:
    """Call Groq; if the model's daily quota is used up, answer with the next fallback model instead."""
    if not SETTINGS.groq_key:
        raise LLMError("LLM_BACKEND=groq but GROQ_API_KEY is not set")
    now = time.time()
    for cand in [model] + [m for m in GROQ_FALLBACK_MODELS if m != model]:
        if _GROQ_EXHAUSTED.get(cand, 0) > now:
            continue
        result = _groq_call(messages, cand, temperature, max_tokens, fmt)
        if result is None:          # this model's daily quota is used up: try the next one
            continue
        if cand != model and (model, cand) not in _GROQ_FALLBACK_NOTED:
            _GROQ_FALLBACK_NOTED.add((model, cand))
            STATS.warnings.append(f"[{current_stage()}] Groq daily quota for {model} is used up; "
                                  f"{cand} answered instead")
        return result
    raise LLMQuotaError("the free daily quota of every configured Groq model is used up; it refills gradually")


def _groq_call(messages: list[dict], model: str, temperature: float, max_tokens: int,
               fmt: Any) -> tuple[str, int, int] | None:
    """One model. Returns None when the model's DAILY quota is used up (waiting would not help)."""
    payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature,
                               "max_tokens": max_tokens, "seed": 7}
    if model.startswith(GROQ_REASONING_PREFIXES):
        # Reasoning models spend completion tokens on hidden reasoning before the answer. Keep the effort low
        # and add headroom, or the small budgets used for JSON steps end with an empty or truncated answer.
        payload["reasoning_effort"] = os.getenv("GROQ_REASONING_EFFORT", "low")
        payload["max_tokens"] = max_tokens + 512
    elif model.startswith("qwen/"):
        payload["reasoning_effort"] = "none"     # answer directly; no <think> block in the content
    if fmt is not None:
        payload["response_format"] = {"type": "json_object"}
        if not any("json" in str(m.get("content", "")).lower() for m in messages):
            # Groq's JSON mode requires the word "json" somewhere in the messages
            payload["messages"] = [{"role": "system", "content": "Respond with a single JSON object."}, *messages]
    for attempt in range(6):
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, timeout=120,
                          headers={"Authorization": f"Bearer {SETTINGS.groq_key}"})
        if r.status_code == 429:
            wait = _retry_after(r)
            if "per day" in r.text or wait > 120:   # daily quota (tokens or requests per day)
                _GROQ_EXHAUSTED[model] = time.time() + max(wait, 120)
                return None
            time.sleep(min(60.0, max(1.0, wait)))    # per-minute limit: wait as long as Groq asks
            continue
        if r.status_code == 400 and "json_validate_failed" in r.text:
            # Groq rejected the model's JSON: return it so llm_json's repair-and-retry handles it like any
            # other invalid output, instead of failing the whole run.
            return str(r.json().get("error", {}).get("failed_generation") or ""), 0, 0
        if r.status_code != 200:
            raise LLMError(f"Groq error {r.status_code}: {r.text[:300]}")
        data = r.json()
        usage = data.get("usage", {})
        content = re.sub(r"<think>.*?</think>\s*", "", data["choices"][0]["message"]["content"] or "", flags=re.S)
        return content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    raise LLMError("Groq rate limit: retries exhausted")


def llm(prompt: str, system: str | None = None, temperature: float = 0.2, model: str | None = None,
        max_tokens: int = 1024, json_format: Any = None, history: list[dict] | None = None) -> str:
    """Single text-completion entry point used by every ForgeAI stage."""
    model = model or SETTINGS.model
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(history or [])
    messages.append({"role": "user", "content": prompt})

    key = hashlib.sha256(json.dumps(
        [SETTINGS.backend, model, messages, temperature, max_tokens, json_format is not None],
        sort_keys=True).encode()).hexdigest()
    t0 = time.time()
    cached = _cache().get(key) if SETTINGS.use_cache else None
    if cached is not None:
        rec = json.loads(cached)
        text, p_toks, c_toks = rec["text"], rec["p"], rec["c"]
    else:
        chat = _groq_chat if SETTINGS.backend == "groq" else _ollama_chat
        text, p_toks, c_toks = chat(messages, model, temperature, max_tokens, json_format)
        if SETTINGS.use_cache:
            _cache().put(key, json.dumps({"text": text, "p": p_toks, "c": c_toks}))
    seconds = time.time() - t0
    STATS.record(current_stage(), p_toks, c_toks, seconds, cached is not None)

    if p_toks and p_toks > SETTINGS.num_ctx - 64 and SETTINGS.backend == "ollama":
        STATS.warnings.append(f"[{current_stage()}] prompt filled the context window ({p_toks} tokens); "
                              "the model may have lost the beginning of the prompt")
    log_path = CALL_LOG["path"]
    if log_path is not None:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"stage": current_stage(), "model": model, "temperature": temperature,
                                 "system": system, "prompt": prompt, "response": text,
                                 "prompt_tokens": p_toks, "completion_tokens": c_toks,
                                 "seconds": round(seconds, 2), "cached": cached is not None},
                                ensure_ascii=False) + "\n")
    return text


def extract_json(text: str) -> str:
    """Pull the JSON object out of a model reply (code fences, chatter, <think> blocks)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in model output")
    return text[start:end + 1]


class LLMJSONError(LLMError):
    pass


def llm_json(prompt: str, schema: Type[T], system: str | None = None, temperature: float = 0.1,
             retries: int = 3, model: str | None = None, max_tokens: int = 1500) -> T:
    """Completion that must validate against `schema`. Invalid output is fed back for repair.

    Small models break JSON often, so: (1) the backend is put in JSON mode (syntactically valid
    JSON guaranteed), (2) we parse + validate against the Pydantic schema ourselves, (3) on failure
    the exact validation error is returned to the model and it gets another try, up to `retries`
    attempts in total. (Full schema-constrained decoding was tested and rejected: with free-form
    objects such as tool args the grammar garbled values on qwen3:4b.)
    """
    fmt: Any = "json"
    current = prompt
    errors: list[str] = []
    for attempt in range(retries):
        raw = llm(current, system=system, temperature=temperature, model=model,
                  max_tokens=max_tokens, json_format=fmt)
        try:
            return schema.model_validate(json.loads(extract_json(raw)))
        except (ValueError, ValidationError) as exc:  # JSONDecodeError is a ValueError
            err = str(exc)[:800]
            errors.append(err)
            current = (f"{prompt}\n\n---\nYour previous reply could not be used.\nPrevious reply:\n"
                       f"{raw[:1500]}\n\nProblem:\n{err}\n\nReply again with ONE corrected JSON object only.")
            temperature = min(temperature + 0.2, 0.7)
    raise LLMJSONError(f"{schema.__name__}: no valid JSON after {retries} attempts. Last error: {errors[-1]}")


# ---------------------------------------------------------------- embeddings
_EMB_CACHE: _Cache | None = None
_EMBED_FALLBACK_WARNED = False
EMBED_DIM_FALLBACK = 384


def _hashed_vector(text: str) -> np.ndarray:
    """Deterministic bag-of-words hashing vector: a last-resort, lexical-only embedding."""
    from .textutil import content_tokens  # local import to avoid a cycle
    vec = np.zeros(EMBED_DIM_FALLBACK, dtype=np.float32)
    for tok in content_tokens(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % EMBED_DIM_FALLBACK] += 1.0 if (h >> 9) % 2 else -1.0
    return vec


_FASTEMBED: Any = None


def _fastembed_vectors(batch: list[str]) -> list[np.ndarray]:
    """all-MiniLM-L6-v2 in-process via fastembed (ONNX on CPU): the hosted alternative to Ollama embeddings."""
    global _FASTEMBED
    if _FASTEMBED is None:
        from fastembed import TextEmbedding  # optional dependency, only needed with EMBED_BACKEND=fastembed
        _FASTEMBED = TextEmbedding(FASTEMBED_MODEL)
    return [np.asarray(v, dtype=np.float32) for v in _FASTEMBED.embed(batch)]


def _ollama_vectors(batch: list[str]) -> list[np.ndarray]:
    r = requests.post(f"{SETTINGS.ollama_url}/api/embed",
                      json={"model": SETTINGS.embed_model, "input": batch, "truncate": True}, timeout=300)
    r.raise_for_status()
    return [np.array(v, dtype=np.float32) for v in r.json()["embeddings"]]


def embed(texts: list[str]) -> np.ndarray:
    """L2-normalised embeddings for texts, cached per text in .cache/emb.sqlite."""
    global _EMB_CACHE, _EMBED_FALLBACK_WARNED
    if _EMB_CACHE is None:
        _EMB_CACHE = _Cache(CACHE_DIR / "emb.sqlite")
    keys = [hashlib.sha1(f"{SETTINGS.embed_id}|{t}".encode()).hexdigest() for t in texts]
    out: list[np.ndarray | None] = []
    todo: list[int] = []
    for i, k in enumerate(keys):
        hit = _EMB_CACHE.get(k)
        out.append(np.array(json.loads(hit), dtype=np.float32) if hit else None)
        if hit is None:
            todo.append(i)
    for b in range(0, len(todo), 64):
        idx = todo[b:b + 64]
        batch = [texts[i] for i in idx]
        try:
            vecs = _fastembed_vectors(batch) if SETTINGS.embed_backend == "fastembed" else _ollama_vectors(batch)
            for i, v in zip(idx, vecs):
                out[i] = v
                _EMB_CACHE.put(keys[i], json.dumps(v.round(6).tolist()))
        except Exception as exc:  # embeddings unavailable: degrade, but say so loudly
            if not _EMBED_FALLBACK_WARNED:
                STATS.warnings.append(f"embedding model unavailable ({exc}); using hashed lexical vectors")
                _EMBED_FALLBACK_WARNED = True
            for i in idx:
                out[i] = _hashed_vector(texts[i])
    mat = np.vstack(out) if out else np.zeros((0, EMBED_DIM_FALLBACK), dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def check_backend() -> list[str]:
    """Preflight: return a list of problems (empty list = good to go)."""
    problems: list[str] = []
    if SETTINGS.embed_backend == "fastembed":
        try:
            import fastembed  # noqa: F401
        except ImportError:
            problems.append("EMBED_BACKEND=fastembed but the fastembed package is not installed (lexical fallback "
                            "will be used)")
    if SETTINGS.backend == "groq":
        if not SETTINGS.groq_key:
            problems.append("GROQ_API_KEY is not set")
        if SETTINGS.embed_backend != "fastembed":
            try:
                requests.get(f"{SETTINGS.ollama_url}/api/tags", timeout=5)
            except Exception:
                problems.append("no Ollama for embeddings: set EMBED_BACKEND=fastembed (else lexical fallback)")
        return problems
    try:
        tags = requests.get(f"{SETTINGS.ollama_url}/api/tags", timeout=10).json()
        names = {m["name"] for m in tags.get("models", [])}
        for needed in {SETTINGS.model, SETTINGS.judge_model}:
            if needed not in names and f"{needed}:latest" not in names:
                problems.append(f"Ollama model '{needed}' not pulled (run: ollama pull {needed})")
        if (SETTINGS.embed_backend == "ollama" and SETTINGS.embed_model not in names
                and f"{SETTINGS.embed_model}:latest" not in names):
            problems.append(f"embedding model '{SETTINGS.embed_model}' not pulled (lexical fallback will be used)")
    except Exception as exc:
        problems.append(f"cannot reach Ollama at {SETTINGS.ollama_url}: {exc}")
    return problems
