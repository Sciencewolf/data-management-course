"""Vector search over recipes in pgvector and Qdrant with the same filters.

    python -m grocery.search "quick vegetarian dinner" --customer C0007
"""
import argparse
import time

from qdrant_client import models

from grocery import stores
from grocery.config import QDRANT_COLLECTION
from grocery.embeddings import embed


# ---------- pgvector ----------

def pg_search(pg, qvec, k=10, exclude_allergens=(), cuisine=None, exact=False, ef_search=40,
              iterative_scan="off"):
    """Top-k recipe ids by cosine distance. exact=True disables the HNSW index (sequential scan)."""
    where, params = ["NOT (allergen_codes && %(excl)s::text[])"], {"q": qvec, "k": k, "excl": list(exclude_allergens)}
    if cuisine:
        where.append("cuisine = %(cuisine)s")
        params["cuisine"] = cuisine
    sql = (f"SELECT recipe_id, 1 - (embedding <=> %(q)s) AS score FROM recipe_vectors "
           f"WHERE {' AND '.join(where)} ORDER BY embedding <=> %(q)s LIMIT %(k)s")
    with pg.transaction(), pg.cursor() as cur:
        cur.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")
        cur.execute(f"SET LOCAL hnsw.iterative_scan = {iterative_scan}")
        if exact:
            cur.execute("SET LOCAL enable_indexscan = off")
        else:  # the table is small; without this the planner prefers a sequential scan
            cur.execute("SET LOCAL enable_seqscan = off")
        cur.execute(sql, params)
        return [(rid, float(score)) for rid, score in cur.fetchall()]


def pg_plan_uses_hnsw(pg, qvec, cuisine=None, exact=False):
    with pg.transaction(), pg.cursor() as cur:
        cur.execute("SET LOCAL enable_indexscan = off" if exact else "SET LOCAL enable_seqscan = off")
        cur.execute("EXPLAIN SELECT recipe_id FROM recipe_vectors WHERE (%(c)s::text IS NULL OR cuisine = %(c)s) "
                    "ORDER BY embedding <=> %(q)s LIMIT 10", {"q": qvec, "c": cuisine})
        return any("recipe_vectors_hnsw" in row[0] for row in cur.fetchall())


# One SQL statement: similar recipes that are safe for this customer's allergies,
# whose products are all in stock now, with the total price, joined with business tables.
PG_RECOMMEND_SQL = """
WITH allergies AS (
    SELECT coalesce(array_agg(allergen_code::text), '{}') AS codes
    FROM customer_allergies WHERE customer_id = %(customer)s
), candidates AS (
    SELECT v.recipe_id, v.title, v.product_ids, v.embedding <=> %(q)s AS distance
    FROM recipe_vectors v, allergies a
    WHERE NOT (v.allergen_codes && a.codes)
    ORDER BY v.embedding <=> %(q)s
    LIMIT %(candidates)s
)
SELECT c.recipe_id, c.title, round((1 - c.distance)::numeric, 3) AS score, sum(pr.unit_price) AS total_price
FROM candidates c
CROSS JOIN LATERAL unnest(c.product_ids) AS pid(product_id)
JOIN stock  s  ON s.product_id  = pid.product_id
JOIN prices pr ON pr.product_id = pid.product_id
GROUP BY c.recipe_id, c.title, c.distance, c.product_ids
HAVING bool_and(s.quantity > 0) AND count(*) = cardinality(c.product_ids)
ORDER BY c.distance
LIMIT %(k)s
"""


def pg_recommend(pg, customer_id, qvec, k=5, candidates=50, ef_search=100):
    with pg.transaction(), pg.cursor() as cur:
        cur.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")
        cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
        cur.execute(PG_RECOMMEND_SQL, {"customer": customer_id, "q": qvec, "k": k, "candidates": candidates})
        return cur.fetchall()


# ---------- Qdrant ----------

def qdrant_filter(exclude_allergens=(), cuisine=None):
    must = [models.FieldCondition(key="cuisine", match=models.MatchValue(value=cuisine))] if cuisine else []
    must_not = ([models.FieldCondition(key="allergen_codes", match=models.MatchAny(any=list(exclude_allergens)))]
                if exclude_allergens else [])
    return models.Filter(must=must, must_not=must_not) if (must or must_not) else None


def qdrant_search(client, qvec, k=10, exclude_allergens=(), cuisine=None, exact=False, hnsw_ef=40):
    res = client.query_points(
        QDRANT_COLLECTION, query=qvec.tolist(), limit=k, with_payload=["recipe_id"],
        query_filter=qdrant_filter(exclude_allergens, cuisine),
        search_params=models.SearchParams(hnsw_ef=hnsw_ef, exact=exact))
    return [(p.payload["recipe_id"], p.score) for p in res.points]


def qdrant_recommend(client, pg, customer_id, qvec, k=5, candidates=50, hnsw_ef=100):
    """Same question as PG_RECOMMEND_SQL, but in three steps: allergies from PostgreSQL,
    filtered vector search in Qdrant, then stock and price from PostgreSQL."""
    codes = [r[0] for r in pg.execute("SELECT allergen_code::text FROM customer_allergies WHERE customer_id = %s",
                                      (customer_id,)).fetchall()]
    hits = qdrant_search(client, qvec, k=candidates, exclude_allergens=codes, hnsw_ef=hnsw_ef)
    if not hits:
        return []
    rows = pg.execute("""
        SELECT v.recipe_id, v.title, sum(pr.unit_price), bool_and(s.quantity > 0) AND count(*) = cardinality(v.product_ids)
        FROM recipe_vectors v
        CROSS JOIN LATERAL unnest(v.product_ids) AS pid(product_id)
        JOIN stock s ON s.product_id = pid.product_id JOIN prices pr ON pr.product_id = pid.product_id
        WHERE v.recipe_id = ANY(%s) GROUP BY v.recipe_id, v.title, v.product_ids""",
                      ([rid for rid, _ in hits],)).fetchall()
    info = {rid: (title, price, ok) for rid, title, price, ok in rows}
    out = [(rid, info[rid][0], round(score, 3), info[rid][1]) for rid, score in hits if info[rid][2]]
    return out[:k]


def timed(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - start) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--customer", default="C0007")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()
    qvec = embed([args.text])[0]
    pg, client = stores.postgres(), stores.qdrant()
    codes = [r[0] for r in pg.execute("SELECT allergen_code::text FROM customer_allergies WHERE customer_id = %s",
                                      (args.customer,)).fetchall()]
    print(f'Request "{args.text}" for customer {args.customer}, allergies {codes or "none"}\n')
    rows, ms = timed(pg_recommend, pg, args.customer, qvec, args.k)
    print(f"pgvector, one SQL statement ({ms:.1f} ms):")
    for rid, title, score, price in rows:
        print(f"  {rid}  {score:.3f}  {price:>9} HUF  {title}")
    rows, ms = timed(qdrant_recommend, client, pg, args.customer, qvec, args.k)
    print(f"\nQdrant + PostgreSQL, three steps ({ms:.1f} ms):")
    for rid, title, score, price in rows:
        print(f"  {rid}  {score:.3f}  {price:>9} HUF  {title}")


if __name__ == "__main__":
    main()
