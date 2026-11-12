"""Run the 3 required scenarios against the configured LLM and write results/results.md."""
import os
from datetime import datetime, timezone
from pathlib import Path

from app.qa import answer

SUPPORTED = "How do I save my progress on a lesson?"
UNKNOWN = "How much does BrightPath cost and can I get a refund?"
DEAD_URL = "http://localhost:9"   # nothing listens on port 9, so the call must fail

RESULTS = Path(__file__).resolve().parent / "results" / "results.md"


def run(name: str, question: str) -> dict:
    result = answer(question)
    return {
        "name": name,
        "question": question,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": os.getenv("LLM_MODEL", "llama3.2"),
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        **result,
    }


def to_markdown(r: dict) -> str:
    sources = ", ".join(f"{s['title']} ({s['id']})" for s in r["sources"]) or "none"
    lines = [
        f"## {r['name']}",
        "",
        f"- **Question:** {r['question']}",
        f"- **Answer:** {r['answer']}",
        f"- **Sources:** {sources}",
        f"- **Found:** {r['found']}",
        f"- **Mode:** {r['mode']}",
        f"- **Model:** {r['model']} @ {r['base_url']}",
        f"- **Timestamp:** {r['timestamp']}",
    ]
    if "error" in r:
        lines.append(f"- **Error:** {r['error']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    results = [
        run("1. Supported question", SUPPORTED),
        run("2. Unknown question", UNKNOWN),
    ]

    # 3. Force a real call to a dead endpoint, then restore the environment.
    saved = {k: os.environ.get(k) for k in ("LLM_BASE_URL", "LLM_MODE")}
    os.environ["LLM_BASE_URL"] = DEAD_URL
    os.environ["LLM_MODE"] = "real"
    try:
        results.append(run("3. API failure", SUPPORTED))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text("# BrightPath Q&A - scenario results\n\n"
                       + "\n".join(to_markdown(r) for r in results), encoding="utf-8")
    for r in results:
        print(f"{r['name']}: found={r['found']} mode={r['mode']} error={r.get('error', '-')}")
    print(f"Wrote {RESULTS}")


if __name__ == "__main__":
    main()
