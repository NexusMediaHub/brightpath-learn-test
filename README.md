# BrightPath Learn Q&A

A small question-answering tool. You ask a question; it answers **only** from the three
BrightPath Learn documents in `docs/`, shows which document(s) support the answer, and says
so plainly when the documents don't cover it.

## Setup

Requires Python 3.11+ and (for real answers) [Ollama](https://ollama.com).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
ollama pull llama3.2               # Ollama must be running (ollama serve / desktop app)
```

### Configuration (`.env`)

| Variable       | Default                     | Meaning                                                    |
|----------------|-----------------------------|------------------------------------------------------------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Any OpenAI-compatible endpoint                             |
| `LLM_MODEL`    | `llama3.2`                  | Model name                                                 |
| `LLM_API_KEY`  | *(blank)*                   | Sent as `Bearer` token if set; leave blank for Ollama      |
| `LLM_TIMEOUT`  | `30`                        | Seconds before giving up on the model                      |
| `LLM_MODE`     | `real`                      | `mock` = canned answers, no model; every reply has `"mode": "mock"` and `[MOCK]` |

No keys are hardcoded; `.env` is git-ignored.

## Run

**Web:** `uvicorn app.main:app --reload`, then open http://localhost:8000
(if a code change doesn't show up, stop and restart the server)

- `GET /` – the page
- `GET /documents` – the three documents (the page lists them)
- `POST /ask` – body `{"question": "..."}` (1–500 characters, otherwise 400) → `{answer, sources:[{id,title}], found, mode, error?}`
- `GET /health` – whether the LLM server is reachable and the model is installed

**CLI:** `python ask.py "How do I save my progress on a lesson?"`

## Tests

```bash
pytest                 # unit tests; the HTTP call is faked, no model needed
python run_tests.py    # the 3 required scenarios against the real model -> results/results.md
```

`run_tests.py` scenarios:
1. Supported: "How do I save my progress on a lesson?"
2. Unknown: "How much does BrightPath cost and can I get a refund?"
3. API failure: the supported question with `LLM_BASE_URL=http://localhost:9`

**First run is slow:** Ollama loads the model into memory on the first request (over a
minute on some machines), which can exceed `LLM_TIMEOUT=30`. The web app warms the model up
in a background thread at startup, so wait a moment after starting it. For the CLI, warm it
up with `ollama run llama3.2 "hi"`, or raise `LLM_TIMEOUT`.

## How to test failure

Any of these should give a friendly message (red banner in the web page), never a crash:

- Point at a dead port: `LLM_BASE_URL=http://localhost:9` in `.env` (or
  `LLM_BASE_URL=http://localhost:9 python ask.py "..."`; PowerShell: `$env:LLM_BASE_URL="http://localhost:9"`)
- Stop Ollama
- Use a model you haven't pulled: `LLM_MODEL=does-not-exist`
- Set `LLM_TIMEOUT=0.001` to force a timeout

## Design notes

- **Full context, no embeddings.** The three documents total ~1,500 characters, so every
  question sends all of them. Retrieval (embeddings, vector store) would add moving parts and a
  new way to miss the right document, for no benefit at this size.
- **Structured output.** The model must reply with JSON `{"answer","sources","found"}`.
  `temperature=0` and `response_format: json_object` make that more reliable.
- **Don't trust citations.** `qa.validate` drops any source id that isn't a real document. If
  the model claims `found=true` but cites nothing valid, the answer is replaced with the
  standard "not in the documents" message. Any `found=false` reply also gets that exact message.
- **Cheap grounding check.** Small models sometimes claim `found=true` with junk (e.g. the
  question "hello" answered "hello", citing doc1). `qa.is_grounded` requires the answer to share
  at least one 4+ letter word with the cited document(s); otherwise it becomes "not found".
  Input with no letters at all (e.g. `.010`) is rejected before calling the model.
- **Instruction lines are not answers.** doc3 contains lines meant for the assistant ("This
  document does not contain pricing...", "Never ask a member to send a password"). llama3.2
  kept quoting them as answers to unrelated questions (certificates, discounts). The prompt
  says not to, and `qa.is_instruction` enforces it: if the closest matching line in the cited
  document is an instruction line, the answer becomes "not found".
- **Errors are values, not exceptions.** `llm.py` turns every failure (connection refused,
  timeout, non-200, model missing, malformed body) into one `LLMError` with a clear reason;
  `qa.answer` catches it and returns `found=false` plus an `error` field. The API, CLI and page
  all just display what they get back.
- **The page** (`static/index.html`, `style.css`, `app.js`, no framework) has the ask box at the
  top, then the full text of the three documents. When an answer comes back, its source
  document turns blue in that list, so you can check the answer against the text yourself.
  Enter asks, Shift+Enter adds a line; the example questions ask straight away.
- **Mock mode** exists only so the UI can be demoed without a model. It is opt-in and labelled
  in every response.

## Security

Checked on 2026-11-12 (tools run from a separate environment, not project dependencies):

- **Secrets:** `detect-secrets` over every file, `.env` included: none found. No keys are
  hardcoded. `.env` and `.env.*` are git-ignored (only `.env.example` is tracked) and `.env`
  has never been committed. `.env.example` holds only local defaults with an empty API key.
- **Dependencies:** `pip-audit` found known CVEs in starlette 0.41.3, requests 2.32.3 and
  pytest 8.3.4. All upgraded; every dependency is pinned to an exact version in
  `requirements.txt`, and `pip-audit` now reports no known vulnerabilities.
- **Code:** `bandit` reports no real issues. Its only non-test notice (B113, "request without
  timeout", low confidence) is a false positive: both `requests` calls have a timeout
  (`LLM_TIMEOUT`, and 5 s for the health check). The other notices are `assert` in tests.
- **Input:** `/ask` uses a Pydantic model: the question is trimmed and must be 1–500
  characters. Anything else (empty, too long, wrong type, broken JSON) gets a plain 400 that
  does not echo the input back.
- **Output in the browser:** answers and sources are inserted with `textContent` only; there is
  no `innerHTML`, so a model reply containing HTML is shown as text, never run.
- **Error responses:** the user sees a short reason ("could not connect to the language model
  server"), never the LLM URL, model name, key, the upstream server's reply or a stack trace.
  Details are written to the server log. Any unexpected error returns a generic 500.
- **Prompt injection and passwords:** the question only ever goes in the user message, never
  the system prompt. Answers are then checked in code: numbers must appear in the cited
  document (stops an injected "it costs $5"), and an answer that asks for a password is
  replaced with the "not in the documents" message.
- **Tests:** `tests/test_security.py` covers all of the above.

Remaining limits:

- **No authentication:** anyone who can reach the server can use it.
- **No rate limiting:** a client can send unlimited questions, each one a model call.
- **Local only:** built to run on `localhost` with a local Ollama. Before exposing it, add
  auth, rate limiting and HTTPS, and run it behind a reverse proxy.
- `/health` shows the configured model name. The `/docs` API page is FastAPI's default and
  loads its assets from a CDN.
- The injection checks are heuristics; a model could still give a wrong answer that uses only
  words and numbers from the documents.

## Limitations

- Grounding relies on the prompt plus cheap checks on the answer text (word overlap,
  numbers, password requests). A model could still paraphrase a document wrongly while
  citing it correctly.
- Instruction lines are recognised by wording ("this document", "member"). New documents
  written in a different style would need that rule updated.
- Questions in other languages are answered in English when the model understands them.
- The word-overlap check is a heuristic: it stops obvious junk, not a subtly wrong answer
  that happens to reuse document words.
- Small local models (llama3.2 3B) sometimes ignore the JSON format; that is reported as an
  error rather than retried.
- Full-context only works while the docs are small. Many or long documents would need retrieval.
- Mock mode uses simple keyword matching and is not a real answerer.
- No auth, rate limiting, streaming, or conversation history.

## Project layout

```
app/docs.py      load docs -> [{id, title, text}]
app/llm.py       call_llm() + LLMError + health check
app/qa.py        prompt, JSON parsing, citation validation, answer()
app/main.py      FastAPI routes + model warm-up
static/          the page: index.html, style.css, app.js, img/ (photos + credits.json)
ask.py           CLI
run_tests.py     3 scenarios -> results/results.md
tests/test_qa.py        pytest: LLM client, answer validation, failures
tests/test_security.py  pytest: injection, passwords, input limits, no leaks
```

## Image credits

Photographs from Wikimedia Commons, shown in greyscale (details in `static/img/credits.json`):
"Schlagwortkatalog" by Dr. Marcus Gossler (CC BY-SA 3.0); "US WashingtonDC Reading Room Library
of Congress Panorama" by Thomas Wozniak (CC BY-SA 4.0); "Katalogový lístek" by Pavel Trnka
(CC BY-SA 4.0); "Manchester Central Library, March 2010" by Ricardo from Manchester (CC BY 2.0).

## Tools used

Python, FastAPI, uvicorn, requests, python-dotenv, pytest, Ollama (llama3.2).
Built with help from Claude Code (AI coding assistant); all code reviewed and explained by me.
