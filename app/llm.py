"""Minimal client for any OpenAI-compatible /chat/completions endpoint."""
import logging
import os
from urllib.parse import urlsplit, urlunsplit

import requests
from dotenv import load_dotenv

load_dotenv()  # read .env once; real environment variables still win
log = logging.getLogger(__name__)


class LLMError(Exception):
    """The language model could not give us a usable reply.
    The message is shown to users, so it never contains config values (URL, model name,
    key) or the server's raw reply. Details go to the server log instead."""


def read_timeout() -> float:
    """LLM_TIMEOUT in seconds; falls back to 30 if it is missing, not a number, or not above 0."""
    try:
        value = float(os.getenv("LLM_TIMEOUT", "30"))
    except ValueError:
        return 30.0
    return value if value > 0 else 30.0


def settings() -> dict:
    """Read config at call time, so callers can change env vars on the fly."""
    return {
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
        "model": os.getenv("LLM_MODEL", "llama3.2"),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "timeout": read_timeout(),
    }


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _safe_url(url: str) -> str:
    """The URL without any user:password, so it is safe to write to the log."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(netloc=parts.hostname + (f":{parts.port}" if parts.port else ""))) \
        if parts.hostname else url


def call_llm(messages: list[dict], timeout: float | None = None) -> str:
    """Send chat messages, return the assistant's text. Raises LLMError on any failure.
    `timeout` overrides LLM_TIMEOUT (used by the warm-up, which can take over a minute)."""
    cfg = settings()
    if timeout is not None:
        cfg["timeout"] = timeout
    url = f"{cfg['base_url']}/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0,                            # same question -> same answer
        "response_format": {"type": "json_object"},  # ask for JSON output
    }

    try:
        # nosec B113: bandit can't see through the variable; the timeout is always set.
        resp = requests.post(url, json=payload, headers=_headers(cfg["api_key"]),  # nosec B113
                             timeout=cfg["timeout"])
    # Timeout is checked first: a connect-timeout is both a Timeout and a ConnectionError.
    except requests.exceptions.Timeout:
        log.warning("LLM timeout after %ss at %s", cfg["timeout"], _safe_url(cfg["base_url"]))
        raise LLMError("no reply from the language model within the time limit")
    except requests.exceptions.ConnectionError:
        log.warning("LLM connection failed: %s", _safe_url(cfg["base_url"]))
        raise LLMError("could not connect to the language model server")

    if resp.status_code == 404 and "model" in resp.text.lower():
        log.warning("LLM model %r not found - try: ollama pull %s", cfg["model"], cfg["model"])
        raise LLMError("the configured model was not found on the server")
    if resp.status_code != 200:
        log.warning("LLM HTTP %s: %.200s", resp.status_code, resp.text)
        raise LLMError(f"the language model server returned HTTP {resp.status_code}")

    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        log.warning("LLM malformed response: %.200s", resp.text)
        raise LLMError("the language model server sent a malformed response")


def check_health() -> dict:
    """Quick check used by GET /health: is the server up and is our model there?"""
    cfg = settings()
    try:
        resp = requests.get(f"{cfg['base_url']}/models", headers=_headers(cfg["api_key"]),
                            timeout=5)
        resp.raise_for_status()
        ids = [m.get("id", "") for m in resp.json().get("data", [])]
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        return {"reachable": False, "model": cfg["model"], "model_available": False}
    # Ollama lists "llama3.2:latest" for "llama3.2", so match on the name before ":"
    available = any(i == cfg["model"] or i.split(":")[0] == cfg["model"] for i in ids)
    return {"reachable": True, "model": cfg["model"], "model_available": available}
