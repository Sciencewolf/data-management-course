"""Safety (0 unsafe recipes) and relevance (recall@5, MRR) in both vector stores.

A returned recipe is checked against the live graph, not against its own
vector metadata: Neo4j traverses from the recipe's current MongoDB product_ids.

    python -m grocery.evaluate        # also writes results/evaluation.txt
"""
import json
import statistics

from grocery import stores
from grocery.compare_vectors import Report
from grocery.config import TESTS_DIR
from grocery.embeddings import embed
from grocery.queries import allergens_for_recipes
from grocery.search import pg_search, qdrant_search
from tests.resolve_labels import load as load_labels

TOP = 5
EF = 100


def live_allergens(db, session, recipe_ids):
    docs = db.recipes.find({"_id": {"$in": list(recipe_ids)}}, {"product_ids": 1})
    return allergens_for_recipes(session, [{"id": d["_id"], "product_ids": d["product_ids"]} for d in docs])


def main():
    out = Report()
    pg, qd, db, driver = stores.postgres(), stores.qdrant(), stores.mongo(), stores.neo4j()
    systems = {
        "pgvector": lambda q, **kw: pg_search(pg, q, ef_search=EF, iterative_scan="relaxed_order", **kw),
        "Qdrant": lambda q, **kw: qdrant_search(qd, q, hnsw_ef=EF, **kw),
    }

    cases = json.loads((TESTS_DIR / "safety_cases.json").read_text())["cases"]
    qvecs = embed(c["request"] for c in cases)
    out(f"Safety: {len(cases)} cases ({sum(len(c['allergy_codes']) > 1 for c in cases)} with several allergies), "
        f"top {TOP}, unsafe = live Neo4j allergens of the recipe intersect the allergy list")
    with driver.session() as session:
        for name, search in systems.items():
            unsafe_total, returned_total, short = 0, 0, []
            for case, q in zip(cases, qvecs):
                hits = search(q, k=TOP, exclude_allergens=case["allergy_codes"])
                live = live_allergens(db, session, [rid for rid, _ in hits])
                unsafe = [rid for rid, _ in hits if set(live[rid]) & set(case["allergy_codes"])]
                if unsafe:
                    out(f"  UNSAFE {name} {case['id']}: {unsafe}")
                unsafe_total += len(unsafe)
                returned_total += len(hits)
                if len(hits) < TOP:
                    short.append(f"{case['id']}={len(hits)}")
            out(f"  {name:9s} unsafe recipes returned: {unsafe_total} of {returned_total}"
                f"{'; fewer than 5 results: ' + ', '.join(short) if short else ''}")

    labels = load_labels()
    lvecs = embed(r["text"] for r in labels)
    out(f"\nRelevance: {len(labels)} labelled requests, no allergy filter")
    for name, search in systems.items():
        recalls, rrs, misses = [], [], []
        for req, q in zip(labels, lvecs):
            ranked = [rid for rid, _ in search(q, k=10)]
            relevant = set(req["relevant_ids"])
            recalls.append(len(relevant & set(ranked[:TOP])) / len(relevant))
            rank = next((i + 1 for i, rid in enumerate(ranked) if rid in relevant), None)
            rrs.append(1 / rank if rank else 0.0)
            if not relevant & set(ranked[:TOP]):
                misses.append(req["id"])
        out(f"  {name:9s} recall@5 {statistics.mean(recalls):.3f}  MRR@10 {statistics.mean(rrs):.3f}  "
            f"requests with no relevant recipe in top 5: {misses or 'none'}")
    driver.close()
    out.save("evaluation.txt")


if __name__ == "__main__":
    main()
