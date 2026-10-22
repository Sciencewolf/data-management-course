"""pgvector vs Qdrant on the 20 fixed queries. Every number in the report comes from here.

    python -m grocery.compare_vectors        # also writes results/vector_comparison.txt
"""
import json
import statistics

from grocery import stores
from grocery.config import QDRANT_COLLECTION, RESULTS_DIR, TESTS_DIR
from grocery.embeddings import embed
from grocery.search import pg_plan_uses_hnsw, pg_search, qdrant_search, timed

K = 10
FILTER_CUISINE = "korean"
PG_EF_SEARCH = 40          # pgvector default
QDRANT_HNSW_EF = 40        # set equal to pgvector for a fair comparison


class Report:
    def __init__(self):
        self.lines = []

    def __call__(self, line=""):
        print(line)
        self.lines.append(line)

    def save(self, name):
        RESULTS_DIR.mkdir(exist_ok=True)
        (RESULTS_DIR / name).write_text("\n".join(self.lines) + "\n")


def ann_recall(approx, exact):
    return len({r for r, _ in approx} & {r for r, _ in exact}) / K


def run_system(name, search, qvecs, **filter_kwargs):
    recalls, counts, latencies, tops = [], [], [], []
    for q in qvecs:
        exact = search(q, k=K, exact=True, **filter_kwargs)
        approx, ms = timed(search, q, k=K, exact=False, **filter_kwargs)
        # recall is measured against what the exact search can return (fewer than K when the filter is tight)
        recalls.append(len({r for r, _ in approx} & {r for r, _ in exact}) / max(1, min(K, len(exact))))
        counts.append(len(approx))
        latencies.append(ms)
        tops.append(approx)
    return {"name": name, "recall": statistics.mean(recalls), "min_recall": min(recalls),
            "returned": statistics.mean(counts), "min_returned": min(counts),
            "p50_ms": statistics.median(latencies), "max_ms": max(latencies), "tops": tops}


def describe(out, r):
    out(f"  {r['name']:38s} ANN recall@10 mean {r['recall']:.3f} (min {r['min_recall']:.2f}) | "
        f"results returned mean {r['returned']:.1f} (min {r['min_returned']}) | "
        f"latency p50 {r['p50_ms']:.2f} ms (max {r['max_ms']:.2f})")


def main():
    out = Report()
    queries = json.loads((TESTS_DIR / "ann_queries.json").read_text())["queries"]
    qvecs = embed(queries)
    pg, qd = stores.postgres(), stores.qdrant()

    total = pg.execute("SELECT count(*) FROM recipe_vectors").fetchone()[0]
    kept = pg.execute("SELECT count(*) FROM recipe_vectors WHERE cuisine = %s", (FILTER_CUISINE,)).fetchone()[0]
    ext = pg.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
    info = qd.get_collection(QDRANT_COLLECTION)
    hnsw = info.config.hnsw_config
    out(f"Corpus: {total} recipe vectors, all-MiniLM-L6-v2, normalised, cosine distance, {len(queries)} fixed queries")
    out(f"pgvector {ext}: HNSW m=16 ef_construction=64, hnsw.ef_search={PG_EF_SEARCH}")
    out(f"Qdrant: HNSW m={hnsw.m} ef_construct={hnsw.ef_construct} full_scan_threshold={hnsw.full_scan_threshold} KB, "
        f"hnsw_ef={QDRANT_HNSW_EF}, {info.indexed_vectors_count}/{info.points_count} vectors indexed, "
        f"payload indexes: {sorted(info.payload_schema)}")
    out(f"pgvector plan uses the HNSW index: unfiltered={pg_plan_uses_hnsw(pg, qvecs[0])}, "
        f"exact run={pg_plan_uses_hnsw(pg, qvecs[0], exact=True)}")

    def pg_fn(ef, iterative):
        return lambda q, **kw: pg_search(pg, q, ef_search=ef, iterative_scan=iterative, **kw)

    def qd_fn(ef):
        return lambda q, **kw: qdrant_search(qd, q, hnsw_ef=ef, **kw)

    out("\n1) No filter: HNSW top-10 vs the same system's exact top-10")
    pg_r = run_system(f"pgvector (ef_search={PG_EF_SEARCH})", pg_fn(PG_EF_SEARCH, "off"), qvecs)
    qd_r = run_system(f"Qdrant (hnsw_ef={QDRANT_HNSW_EF})", qd_fn(QDRANT_HNSW_EF), qvecs)
    describe(out, pg_r)
    describe(out, qd_r)
    shared = [len({r for r, _ in a} & {r for r, _ in b}) for a, b in zip(pg_r["tops"], qd_r["tops"])]
    out(f"  shared ids between pgvector and Qdrant HNSW top-10: mean {statistics.mean(shared):.1f} / 10, "
        f"min {min(shared)}, per query {shared}")

    out(f"\n2) Filter cuisine = '{FILTER_CUISINE}' keeps {kept}/{total} rows ({kept / total:.1%})")
    for ef, iterative in [(PG_EF_SEARCH, "off"), (PG_EF_SEARCH, "relaxed_order"), (200, "off")]:
        r = run_system(f"pgvector ef_search={ef} iterative={iterative}", pg_fn(ef, iterative), qvecs,
                       cuisine=FILTER_CUISINE)
        describe(out, r)
    r = run_system(f"Qdrant hnsw_ef={QDRANT_HNSW_EF} + payload index", qd_fn(QDRANT_HNSW_EF), qvecs,
                   cuisine=FILTER_CUISINE)
    describe(out, r)
    out.save("vector_comparison.txt")


if __name__ == "__main__":
    main()
