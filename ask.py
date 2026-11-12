"""Command-line client: python ask.py "How do I save my progress?" """
import sys

from app.qa import answer


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")   # so "—" prints correctly on Windows
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        print('Usage: python ask.py "your question"')
        return 2

    result = answer(question)
    print(result["answer"])
    for s in result["sources"]:
        print(f"  - source: {s['title']} ({s['id']})")
    print(f"[found={result['found']} mode={result['mode']}]")
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
