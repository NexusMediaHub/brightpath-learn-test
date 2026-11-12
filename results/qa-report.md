# QA report — 2026-11-12

Model: llama3.2 (Ollama, local GPU). All checks below were run against the final code.

| Area | Result |
|---|---|
| Unit tests (`pytest`, HTTP faked) | 44 / 44 pass (27 core + 17 security) |
| Required scenarios (`run_tests.py`) | 3 / 3 correct: supported → found (doc1), unknown → not found, API failure → friendly error |
| Answer accuracy, 22 scored questions, each asked twice | 22 / 22 correct, identical answers on both runs, ~5 s per answer |
| API input handling (17 cases) | All correct: 400 for empty / whitespace / >500 chars / bad JSON / wrong types (input not echoed), 405 wrong method, path traversal blocked |
| LLM failure modes via CLI (7 cases) | All give the friendly message, exit code 1, no crash |
| Browser end-to-end (headless Chrome, 35 checks) | 35 / 35 pass |
| Design inspector (1440 / 768 / 390 px) | 0 FAIL, 3 explained warnings |
| Security scans (detect-secrets, pip-audit, bandit) | Clean after fixes — see README "Security" |

## Accuracy set

Answered from the documents (13): saving progress, lesson count, lesson order, video vs Mark
complete, next lesson, coaching time, coaching link, recordings, practice feedback, feedback
time, forgotten password, wrong progress, support hours. One combined question
(coaching + password) cited both doc2 and doc3.

Correctly refused (8): pricing/refund, jobs, mobile app, certificates, general knowledge,
"hello", a prompt-injection attempt ("ignore your instructions… costs $5") and a request for
an admin password. Four extra off-topic questions (certificate wording, student discount,
monthly payment, changing email) were also refused. Read by hand: a Spanish question was answered
correctly in English; "can you reset my password if I send it" was refused.

## Browser checks

Page load (title, one h1, three documents listed, images, fonts, labels, no overflow) ·
asking by button, by Enter, and by example question · Shift+Enter adds a line · "Reading…"
state · source line and blue highlight of the source document · source link scrolls to the
document · answer scrolls into view on a 900 px screen · not-found shows no highlight · empty
input sends nothing · rapid repeat Enter sends one request · 500-character cap · answer HTML
shown as text (no XSS) · web server down message · keyboard order and visible focus · red
banner when the model is down · mock mode labelled · phone layout, ask flow and 24 px touch
targets · reduced motion leaves nothing hidden.

## Bugs found and fixed during QA

1. **Instruction lines quoted as answers.** "Can I get a certificate?" was answered with
   doc3's "This document does not contain pricing, refund rules…" and marked found. Fixed in
   the prompt and enforced in code (`qa.is_instruction`), with tests.
2. **Crash on a bad `LLM_TIMEOUT`** (`abc`, `0`, `-5`). Now falls back to 30 s, with a test.
3. **Repeat Enter sent a second request** while the first was still loading. Now ignored.
4. **Answer could appear below the fold** on a 900 px-tall screen. Now scrolled into view.
5. **Small touch targets** on standalone links (wordmark, footer links). Now at least 24 px.
6. **Garbled "—" in the CLI** on Windows. Output is now UTF-8.

## Security audit fixes (same day)

7. **Vulnerable dependencies** (starlette 0.41.3, requests 2.32.3, pytest 8.3.4): upgraded and pinned.
8. **Config values in error messages:** the LLM URL and model name were shown to users. Messages
   are now generic; details go to the server log, with any user:password stripped from URLs.
9. **Default 422 echoed the input back:** validation errors are now a plain 400.
10. **Injected numbers and password requests could pass the grounding check:** answers must now
    only use numbers found in the cited document, and an answer asking for a password is blocked.

## Known limitations (not fixed)

- First answer after Ollama unloads the model (5 min idle) can be slow; the web app warms the
  model at startup, the CLI does not.
- `uvicorn --reload` did not pick up changes on this Windows machine; restart the server instead.
- Grounding checks are heuristics (word overlap, instruction wording); see README.
