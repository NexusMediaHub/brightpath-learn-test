"""Unit tests. requests.post is monkeypatched, so no model or network is needed."""
import json

import pytest
import requests

from app import llm, qa


class FakeResponse:
    """Just enough of requests.Response for call_llm."""

    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("not JSON")
        return self._body


def chat_reply(content: str) -> FakeResponse:
    """Wrap text the way an OpenAI-compatible server does."""
    return FakeResponse(body={"choices": [{"message": {"content": content}}]})


def fake_post(result):
    """Build a replacement for requests.post that returns or raises `result`."""
    def _post(*args, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result
    return _post


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    """Ignore whatever is in .env: tests always exercise the real code path."""
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setenv("LLM_BASE_URL", "http://fake-llm/v1")


# ---------- llm.call_llm ----------

def test_call_llm_returns_content(monkeypatch):
    monkeypatch.setattr(requests, "post", fake_post(chat_reply("hello")))
    assert llm.call_llm([]) == "hello"


@pytest.mark.parametrize("result, expected", [
    (requests.exceptions.ConnectionError(), "could not connect"),
    (requests.exceptions.Timeout(), "no reply"),
    (FakeResponse(500, text="boom"), "HTTP 500"),
    (FakeResponse(404, text='{"error":"model \\"x\\" not found"}'), "not found"),
    (FakeResponse(200, text="<html>not json</html>"), "malformed"),
    (FakeResponse(200, body={"unexpected": True}), "malformed"),
])
def test_call_llm_errors(monkeypatch, result, expected):
    monkeypatch.setattr(requests, "post", fake_post(result))
    with pytest.raises(llm.LLMError, match=expected):
        llm.call_llm([])


@pytest.mark.parametrize("value", ["abc", "0", "-5", ""])
def test_bad_timeout_value_falls_back_to_30(monkeypatch, value):
    monkeypatch.setenv("LLM_TIMEOUT", value)
    assert llm.settings()["timeout"] == 30.0


# ---------- qa.answer ----------

QUESTION = "How do I save my progress on a lesson?"


def test_valid_answer(monkeypatch):
    reply = {"answer": "Select Mark complete after the lesson.", "sources": ["doc1"], "found": True}
    monkeypatch.setattr(requests, "post", fake_post(chat_reply(json.dumps(reply))))
    result = qa.answer(QUESTION)
    assert result["found"] is True
    assert result["answer"] == "Select Mark complete after the lesson."
    assert result["sources"] == [{"id": "doc1", "title": "Getting started"}]
    assert result["mode"] == "real"
    assert "error" not in result


def test_hallucinated_source_is_stripped(monkeypatch):
    reply = {"answer": "Select Mark complete.", "sources": ["doc1", "doc99"], "found": True}
    monkeypatch.setattr(requests, "post", fake_post(chat_reply(json.dumps(reply))))
    result = qa.answer(QUESTION)
    assert [s["id"] for s in result["sources"]] == ["doc1"]
    assert result["found"] is True


def test_bracketed_source_id_is_accepted(monkeypatch):
    reply = {"answer": "Select Mark complete.", "sources": ["[doc1]"], "found": True}
    monkeypatch.setattr(requests, "post", fake_post(chat_reply(json.dumps(reply))))
    assert qa.answer(QUESTION)["sources"] == [{"id": "doc1", "title": "Getting started"}]


def test_only_hallucinated_sources_downgrades_to_not_found(monkeypatch):
    reply = {"answer": "It costs $10.", "sources": ["doc99"], "found": True}
    monkeypatch.setattr(requests, "post", fake_post(chat_reply(json.dumps(reply))))
    result = qa.answer("How much does it cost?")
    assert result["found"] is False
    assert result["sources"] == []
    assert result["answer"] == qa.NOT_FOUND


@pytest.mark.parametrize("junk", ["doc1", "hello", "4"])
def test_ungrounded_answer_downgrades_to_not_found(monkeypatch, junk):
    reply = {"answer": junk, "sources": ["doc1"], "found": True}
    monkeypatch.setattr(requests, "post", fake_post(chat_reply(json.dumps(reply))))
    result = qa.answer("hello")
    assert result["found"] is False and result["answer"] == qa.NOT_FOUND


@pytest.mark.parametrize("quoted", [
    "This document does not contain pricing, refund rules or job placement promises.",
    "Never ask a member to send a password.",
])
def test_quoted_instruction_line_downgrades_to_not_found(monkeypatch, quoted):
    reply = {"answer": quoted, "sources": ["doc3"], "found": True}
    monkeypatch.setattr(requests, "post", fake_post(chat_reply(json.dumps(reply))))
    result = qa.answer("Can I get a certificate?")
    assert result["found"] is False and result["answer"] == qa.NOT_FOUND


def test_password_reset_answer_is_kept(monkeypatch):
    reply = {"answer": "To reset a password, select Forgot password on the sign-in page.",
             "sources": ["doc3"], "found": True}
    monkeypatch.setattr(requests, "post", fake_post(chat_reply(json.dumps(reply))))
    assert qa.answer("I forgot my password")["found"] is True


def test_input_without_letters_skips_the_model(monkeypatch):
    monkeypatch.setattr(requests, "post", fake_post(AssertionError("model was called")))
    result = qa.answer(".010")
    assert result["answer"] == qa.ASK_IN_WORDS and result["found"] is False


def test_not_found_answer(monkeypatch):
    reply = {"answer": qa.NOT_FOUND, "sources": [], "found": False}
    monkeypatch.setattr(requests, "post", fake_post(chat_reply(json.dumps(reply))))
    result = qa.answer("Can I get a refund?")
    assert result["found"] is False and result["answer"] == qa.NOT_FOUND


@pytest.mark.parametrize("result, reason", [
    (requests.exceptions.ConnectionError(), "could not connect"),
    (requests.exceptions.Timeout(), "no reply"),
    (chat_reply("Sure! The answer is: save often."), "valid JSON"),
])
def test_failures_give_friendly_message(monkeypatch, result, reason):
    monkeypatch.setattr(requests, "post", fake_post(result))
    out = qa.answer(QUESTION)
    assert out["answer"].startswith("The language model is unavailable right now (")
    assert out["answer"].endswith("Please try again shortly.")
    assert reason in out["error"]
    assert out["found"] is False and out["sources"] == []


def test_mock_mode_is_labelled(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    out = qa.answer(QUESTION)
    assert out["mode"] == "mock" and out["answer"].startswith("[MOCK]")
