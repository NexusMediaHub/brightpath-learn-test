"""Load the BrightPath documents from the docs/ folder."""
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


def load_docs(folder: Path = DOCS_DIR) -> list[dict]:
    """Return [{id, title, text}] for every .md file, sorted by filename.

    id    = the part of the filename before the first "_" (e.g. "doc1")
    title = the first "# " heading in the file
    text  = everything after that heading
    """
    docs = []
    for path in sorted(folder.glob("*.md")):
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        title = lines[0].lstrip("# ").strip()
        text = "\n".join(lines[1:]).strip()
        docs.append({"id": path.stem.split("_")[0], "title": title, "text": text})
    return docs
