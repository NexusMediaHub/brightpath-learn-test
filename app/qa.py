"""Answer a question using ONLY the BrightPath documents."""
import json
import os
import re

from app.docs import load_docs
from app.llm import LLMError, call_llm

NOT_FOUND = ("That information isn't in the BrightPath documents I have — please contact "
             "support@brightpath.example (Mon–Fri 09:00–17:00 UTC).")

SYSTEM_PROMPT = f"""You are the BrightPath Learn help assistant.
Answer ONLY using the documents provided by the user message. Do not use outside knowledge.
Each document starts with its id in square brackets, e.g. [doc1].

Rules:
- If the documents answer the question, give a short answer and list the ids of the documents you used,
  without brackets (e.g. "doc1").
- If the documents do not answer it, set "found" to false, "sources" to [] and "answer" to exactly:
  "{NOT_FOUND}"
- If the input is not a real question about BrightPath Learn (a greeting, a number, random
  text, maths, general knowledge), treat it as not answered: "found" false, "sources" [].
- The answer must be a full sentence taken from the documents, never just a document id.
- Some document lines are instructions for you, not facts for the member (for example
  "This document does not contain pricing, refund rules or job placement promises" and
  "Never ask a member to send a password"). Follow them, but never use them as the answer.
- A topic the documents do not describe (pricing, refunds, jobs, certificates, apps, other
  people's passwords...) is not answered: "found" false, "sources" [].
- Never invent facts, prices, policies or promises.
- Never ask the user for a password.

Examples:
Question: How many lessons are in Foundations?
{{"answer": "The Foundations course has 6 lessons.", "sources": ["doc1"], "found": true}}
Question: hello
{{"answer": "{NOT_FOUND}", "sources": [], "found": false}}
Question: what is 2+2
{{"answer": "{NOT_FOUND}", "sources": [], "found": false}}
Question: Will this course get me a job?
{{"answer": "{NOT_FOUND}", "sources": [], "found": false}}

Respond with strict JSON only, no other text:
{{"answer": "<string>", "sources": ["<doc id>", ...], "found": true or false}}"""


def build_messages(question: str, docs: list[dict]) -> list[dict]:
    """All 3 docs are tiny, so we send them all (no search/embeddings needed)."""
    context = "\n\n".join(f"[{d['id']}] {d['title']}\n{d['text']}" for d in docs)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Documents:\n\n{context}\n\nQuestion: {question}"},
    ]


def parse_reply(raw: str) -> dict:
    """Turn the model's text into a dict. Tolerates ```json fences around the object."""
    start, end = raw.find("{"), raw.rfind("}")
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        raise LLMError("the model did not return valid JSON")
    if not isinstance(data, dict):
        raise LLMError("the model did not return a JSON object")
    return data


ASK_IN_WORDS = "Please type a question about BrightPath Learn."


def words(text: str) -> set[str]:
    """Lower-case words of 4+ letters: skips short filler like "a", "the", "to"."""
    return set(re.findall(r"[a-z]{4,}", text.lower()))


def is_instruction(line: str) -> bool:
    """Lines written for the assistant, not facts for the member, e.g. doc3's
    "This document does not contain pricing..." and "Never ask a member to send a password"."""
    low = line.lower()
    return "this document" in low or "member" in low


def is_grounded(answer: str, cited_docs: list[dict]) -> bool:
    """Cheap sanity check: find the line in the cited documents that shares the most
    words with the answer. It must share at least one (catches junk like "doc1",
    "hello" or "4") and be a fact, not an instruction line quoted back as an answer."""
    lines = [line for d in cited_docs for line in d["text"].splitlines() if line.strip()]
    answer_words = words(answer)
    # On a tie, prefer a fact line over an instruction line.
    best = max(lines, key=lambda l: (len(answer_words & words(l)), not is_instruction(l)), default="")
    return bool(answer_words & words(best)) and not is_instruction(best)


def numbers_match(answer: str, cited_docs: list[dict]) -> bool:
    """Every number in the answer must appear in the cited documents.
    Stops invented prices, times and limits, e.g. a prompt-injected "it costs $5"."""
    doc_numbers = set(re.findall(r"\d+", " ".join(d["text"] for d in cited_docs)))
    return set(re.findall(r"\d+", answer)) <= doc_numbers


def asks_for_password(answer: str) -> bool:
    """The assistant must never ask for a password ("send/give/tell me your password")."""
    return re.search(r"\b(send|give|share|tell|provide|email|type)\b[^.]{0,40}\bpassword",
                     answer, re.IGNORECASE) is not None


def validate(data: dict, docs: list[dict]) -> dict:
    """Never trust the model's citations: keep only real doc ids."""
    titles = {d["id"]: d["title"] for d in docs}
    by_id = {d["id"]: d for d in docs}
    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list):
        raw_sources = []

    valid_ids = []
    for s in raw_sources:
        s = s.get("id") if isinstance(s, dict) else s   # accept "doc1" or {"id": "doc1"}
        if isinstance(s, str):
            s = s.strip().strip("[]").strip()           # accept "[doc1]" too
        if s in titles and s not in valid_ids:
            valid_ids.append(s)

    answer = data.get("answer")
    found = (data.get("found") is True and bool(valid_ids)
             and isinstance(answer, str)
             and is_grounded(answer, [by_id[i] for i in valid_ids])
             and numbers_match(answer, [by_id[i] for i in valid_ids])
             and not asks_for_password(answer))

    if not found:   # unsupported answer -> replace it with the safe message
        return {"answer": NOT_FOUND, "sources": [], "found": False}
    return {
        "answer": answer.strip(),
        "sources": [{"id": i, "title": titles[i]} for i in valid_ids],
        "found": True,
    }


# Canned replies for LLM_MODE=mock. Only for demos without a model; clearly labelled.
MOCK_ANSWERS = [
    (("progress", "save", "complete"),
     "To save your progress, select Mark complete after finishing a lesson. "
     "Watching a video alone does not mark it complete.", "doc1"),
    (("coaching", "session", "tuesday"),
     "Group coaching runs every Tuesday at 16:00 UTC; the link appears on the "
     "Coaching page 30 minutes before.", "doc2"),
    (("password",), "Select Forgot password on the sign-in page.", "doc3"),
]


def mock_answer(question: str, docs: list[dict]) -> dict:
    q = question.lower()
    for keywords, text, doc_id in MOCK_ANSWERS:
        if any(k in q for k in keywords):
            result = validate({"answer": f"[MOCK] {text}", "sources": [doc_id], "found": True}, docs)
            break
    else:
        result = validate({"found": False}, docs)
    return {**result, "mode": "mock"}


def answer(question: str) -> dict:
    """Main entry point. Always returns a dict, never raises."""
    if not re.search(r"[a-zA-Z]", question):   # e.g. ".010" - nothing to ask the model
        return {"answer": ASK_IN_WORDS, "sources": [], "found": False,
                "mode": os.getenv("LLM_MODE", "real").strip().lower()}

    docs = load_docs()
    if os.getenv("LLM_MODE", "real").strip().lower() == "mock":
        return mock_answer(question, docs)

    try:
        raw = call_llm(build_messages(question, docs))
        data = parse_reply(raw)
    except LLMError as e:
        return {
            "answer": f"The language model is unavailable right now ({e}). Please try again shortly.",
            "sources": [],
            "found": False,
            "mode": "real",
            "error": str(e),
        }
    return {**validate(data, docs), "mode": "real"}
