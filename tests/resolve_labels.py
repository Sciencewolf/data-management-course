"""Map the hand-written relevant titles in labelled_requests.json to recipe ids.

Fails loudly if a label names a recipe that does not exist.

    python -m tests.resolve_labels
"""
import json

from grocery.config import DATA_DIR, TESTS_DIR


def load():
    labels = json.loads((TESTS_DIR / "labelled_requests.json").read_text())
    by_title = {r["title"]: r["_id"] for r in json.loads((DATA_DIR / "recipes.json").read_text())}
    missing = [t for req in labels["requests"] for t in req["relevant"] if t not in by_title]
    if missing:
        raise SystemExit(f"labels reference unknown recipes: {missing}")
    for req in labels["requests"]:
        req["relevant_ids"] = [by_title[t] for t in req["relevant"]]
    return labels["requests"]


if __name__ == "__main__":
    for req in load():
        print(req["id"], req["relevant_ids"], req["text"])
