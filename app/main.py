"""FastAPI web app: the page, POST /ask, GET /documents, GET /health."""
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints

from app.docs import load_docs
from app.llm import LLMError, call_llm, check_health
from app.qa import answer

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_QUESTION = 500
log = logging.getLogger(__name__)


def warm_up() -> None:
    """Ollama loads the model on its first request, which can take over a minute.
    Do that once in the background at startup, so the first real question is fast."""
    try:
        call_llm([{"role": "user", "content": 'Reply with {"ok": true}'}], timeout=180)
    except LLMError:
        pass   # model not available yet; /ask will report it properly


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("LLM_MODE", "real").strip().lower() == "real":
        threading.Thread(target=warm_up, daemon=True).start()
    yield


app = FastAPI(title="BrightPath Learn Q&A", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AskRequest(BaseModel):
    # Whitespace is trimmed first, so "   " counts as empty.
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                               max_length=MAX_QUESTION)]


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, exc: RequestValidationError):
    """Empty, too long, wrong type or broken JSON: one plain 400 message.
    (FastAPI's default is a 422 that echoes the input back.)"""
    return JSONResponse(status_code=400, content={
        "detail": f'Please send JSON like {{"question": "..."}} with 1 to {MAX_QUESTION} characters.'})


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    """Anything unexpected: log the details, show the user nothing internal."""
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server."})


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/ask")
def ask(req: AskRequest):
    return answer(req.question)


@app.get("/documents")
def documents():
    """The page shows the documents the answers come from."""
    return load_docs()


@app.get("/health")
def health():
    mode = os.getenv("LLM_MODE", "real").strip().lower()
    return {"mode": mode, **check_health()}
