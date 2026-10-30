# =============================================================================
# llm.py  -  One place to talk to the language model (chat + embeddings)
# -----------------------------------------------------------------------------
# We use the OpenAI Python SDK in "OpenAI-compatible" mode. Gemini, Grok, OpenAI
# and many others accept the same request format, so switching provider only
# means changing LLM_BASE_URL / LLM_API_KEY / model names in .env.
#
#   chat:       the model reads the conversation and either answers or asks to
#               call one of our tools (function calling)
#   embeddings: turn a text into a list of numbers (a vector) that captures its
#               meaning; similar meanings -> close vectors (used by pgvector)
#
# Free-tier limits (error 429 = "too many requests / quota used up"):
#   - per MINUTE (e.g. ~15 chat requests/min): waiting a few seconds fixes it
#   - per DAY (e.g. ~1000 requests/day): only tomorrow, another model, or
#     another API key fixes it
# So for every chat request we try, in order:
#   each API key (LLM_API_KEY can hold several keys separated by commas)
#     x each model (LLM_CHAT_MODEL, then LLM_FALLBACK_MODELS)
#   and if everything was rate-limited, wait once and try the list again.
# If it still fails, LLMError says exactly what each model answered.
# =============================================================================

import os
import re
import time
from functools import lru_cache

from openai import APIStatusError, APITimeoutError, APIConnectionError, OpenAI, RateLimitError

from .config import ROOT_DIR  # noqa: F401  (importing config loads the .env file)

API_KEYS = [k.strip() for k in os.getenv("LLM_API_KEY", "").split(",") if k.strip()]
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "gemini-flash-lite-latest")
EMBED_MODEL = os.getenv("LLM_EMBED_MODEL", "gemini-embedding-001")
# Extra chat models to try, in order, if the main one is unavailable or rate-limited
# (on the free tier each model has its own quota). Comma-separated in .env.
FALLBACK_MODELS = [m.strip() for m in (os.getenv("LLM_FALLBACK_MODELS")
                                       or os.getenv("GEMINI_FALLBACK_MODELS", "")).split(",") if m.strip()]
RATE_LIMIT_WAIT = 12          # seconds to wait before the second round (per-minute limits)


class LLMError(RuntimeError):
    """Every key/model failed. `rate_limited` = all failures were quota (429)."""

    def __init__(self, message: str, rate_limited: bool):
        super().__init__(message)
        self.rate_limited = rate_limited


_clients: dict[str, OpenAI] = {}


def client(key: str | None = None) -> OpenAI:
    """One reusable API client per key."""
    if not API_KEYS:
        raise LLMError("LLM_API_KEY is missing in .env", rate_limited=False)
    key = key or API_KEYS[0]
    if key not in _clients:
        # timeout + no SDK retries: we handle retries ourselves, so errors are clear and fast
        _clients[key] = OpenAI(api_key=key, base_url=LLM_BASE_URL, timeout=60, max_retries=0)
    return _clients[key]


def _short_reason(e: Exception) -> str:
    """Turn an SDK error into a short, readable reason (keeps Google's quota name)."""
    if isinstance(e, RateLimitError):
        text = str(getattr(e, "body", "") or e)
        per_day = re.search(r"PerDay", text, re.IGNORECASE)
        per_min = re.search(r"PerMinute", text, re.IGNORECASE)
        scope = "per-day quota" if per_day else "per-minute limit" if per_min else "quota"
        return f"429 rate limit ({scope})"
    if isinstance(e, APITimeoutError):
        return "timeout"
    if isinstance(e, APIConnectionError):
        return "no connection to the AI provider"
    if isinstance(e, APIStatusError):
        return f"{e.status_code} {str(getattr(e, 'body', '') or e)[:120]}"
    return str(e)[:150]


def chat_completion(**kwargs):
    """Call the chat model; on errors try the other keys/models (see top of file)."""
    if not API_KEYS:
        raise LLMError("LLM_API_KEY is missing in .env", rate_limited=False)
    models = [CHAT_MODEL, *[m for m in FALLBACK_MODELS if m != CHAT_MODEL]]
    failures: dict[str, str] = {}

    for round_no in range(2):
        any_rate_limited = False
        for k_index, key in enumerate(API_KEYS):
            for model in models:
                try:
                    return client(key).chat.completions.create(model=model, **kwargs)
                except (APIStatusError, APITimeoutError, APIConnectionError) as e:
                    label = f"{model} (key {k_index + 1})" if len(API_KEYS) > 1 else model
                    failures[label] = _short_reason(e)
                    if isinstance(e, RateLimitError):
                        any_rate_limited = True
                    if isinstance(e, APIStatusError) and e.status_code in (401, 403):
                        break                      # bad key: no point trying other models with it
        if not any_rate_limited or round_no == 1:
            break
        time.sleep(RATE_LIMIT_WAIT)                # per-minute limits reset quickly - try once more

    summary = "; ".join(f"{m}: {r}" for m, r in failures.items())
    quota = (any(r.startswith("429") for r in failures.values())
             and not any(r.startswith(("401", "403")) for r in failures.values()))
    raise LLMError(f"All AI models failed -> {summary}", rate_limited=quota)


@lru_cache(maxsize=512)
def _embed_one(text: str) -> tuple[float, ...]:
    """Embeddings of single questions are cached: the same question costs no quota twice."""
    return tuple(_embed_batch([text])[0])


def _embed_batch(texts: list[str]) -> list[list[float]]:
    last = None
    for attempt in range(3):                       # free tier: retry briefly on "429 quota"
        for key in API_KEYS:
            try:
                resp = client(key).embeddings.create(model=EMBED_MODEL, input=texts)
                return [d.embedding for d in resp.data]
            except RateLimitError as e:
                last = e
        time.sleep(4 * (attempt + 1))
    raise LLMError(f"Embedding model failed -> {_short_reason(last)}", rate_limited=True)


def embed(texts: list[str]) -> list[list[float]]:
    """Return one embedding vector per input text (sent in batches)."""
    if len(texts) == 1:
        return [list(_embed_one(texts[0]))]
    vectors = []
    for i in range(0, len(texts), 20):
        vectors.extend(_embed_batch(texts[i:i + 20]))
    return vectors


def to_pgvector(vec: list[float]) -> str:
    """pgvector reads vectors written like '[0.12,-0.5,...]'."""
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"