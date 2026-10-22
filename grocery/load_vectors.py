"""Embed MongoDB recipes and write the same vectors to pgvector and Qdrant.

Metadata: cuisine, preparation_minutes, allergen_codes (from the Neo4j traversal),
product_ids, the source recipe id and refreshed_at.

    python -m grocery.load_vectors
"""
import time
import uuid
from datetime import datetime, timezone

from qdrant_client import models

from grocery import stores
from grocery.config import EMBEDDING_DIM, QDRANT_COLLECTION
from grocery.embeddings import embed, recipe_text
from grocery.queries import allergens_for_recipes

HNSW_M, HNSW_EF_CONSTRUCT = 16, 64  # same build parameters in both systems


def point_id(recipe_id):
    """Qdrant ids must be integers or UUIDs; derive a stable UUID from the text id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"recipe:{recipe_id}"))


def build_rows(recipes):
    with stores.neo4j() as driver, driver.session() as s:
        allergens = allergens_for_recipes(s, [{"id": r["_id"], "product_ids": r["product_ids"]} for r in recipes])
    vectors = embed(recipe_text(r) for r in recipes)
    now = datetime.now(timezone.utc)
    return [{"recipe_id": r["_id"], "title": r["title"], "cuisine": r["cuisine"],
             "preparation_minutes": r["preparation_minutes"], "allergen_codes": allergens[r["_id"]],
             "product_ids": r["product_ids"], "embedding": v, "refreshed_at": now}
            for r, v in zip(recipes, vectors)]


def write_pgvector(rows):
    with stores.postgres() as pg, pg.transaction(), pg.cursor() as cur:
        cur.executemany(
            """INSERT INTO recipe_vectors (recipe_id, title, cuisine, preparation_minutes, allergen_codes,
                                          product_ids, embedding, refreshed_at)
               VALUES (%(recipe_id)s, %(title)s, %(cuisine)s, %(preparation_minutes)s, %(allergen_codes)s,
                       %(product_ids)s, %(embedding)s, %(refreshed_at)s)
               ON CONFLICT (recipe_id) DO UPDATE SET
                 title = EXCLUDED.title, cuisine = EXCLUDED.cuisine,
                 preparation_minutes = EXCLUDED.preparation_minutes, allergen_codes = EXCLUDED.allergen_codes,
                 product_ids = EXCLUDED.product_ids, embedding = EXCLUDED.embedding,
                 refreshed_at = EXCLUDED.refreshed_at""", rows)


def create_qdrant_collection(client):
    if client.collection_exists(QDRANT_COLLECTION):
        client.delete_collection(QDRANT_COLLECTION)
    client.create_collection(
        QDRANT_COLLECTION,
        vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE),
        # The collection is small (~350 KB of vectors). With the default thresholds
        # Qdrant would never build HNSW and every search would be an exact scan.
        hnsw_config=models.HnswConfigDiff(m=HNSW_M, ef_construct=HNSW_EF_CONSTRUCT, full_scan_threshold=10),
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=10, default_segment_number=1),
    )
    for field, schema in [("cuisine", models.PayloadSchemaType.KEYWORD),
                          ("allergen_codes", models.PayloadSchemaType.KEYWORD),
                          ("preparation_minutes", models.PayloadSchemaType.INTEGER)]:
        client.create_payload_index(QDRANT_COLLECTION, field, field_schema=schema)


def write_qdrant(client, rows):
    client.upsert(QDRANT_COLLECTION, wait=True, points=[
        models.PointStruct(id=point_id(r["recipe_id"]), vector=r["embedding"].tolist(),
                           payload={**{k: v for k, v in r.items() if k != "embedding"},
                                    "refreshed_at": r["refreshed_at"].isoformat()})
        for r in rows])


def wait_until_indexed(client, expected, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = client.get_collection(QDRANT_COLLECTION)
        if info.status == models.CollectionStatus.GREEN and (info.indexed_vectors_count or 0) >= expected:
            return info
        time.sleep(0.5)
    return client.get_collection(QDRANT_COLLECTION)


def main():
    recipes = list(stores.mongo().recipes.find({}, {"title": 1, "description": 1, "cuisine": 1,
                                                    "preparation_minutes": 1, "product_ids": 1}).sort("_id"))
    rows = build_rows(recipes)
    with stores.postgres() as pg:
        pg.execute("TRUNCATE recipe_vectors")
    write_pgvector(rows)
    client = stores.qdrant()
    create_qdrant_collection(client)
    write_qdrant(client, rows)
    info = wait_until_indexed(client, len(rows))
    with stores.postgres() as pg:
        n, ext = pg.execute("SELECT (SELECT count(*) FROM recipe_vectors), "
                            "(SELECT extversion FROM pg_extension WHERE extname = 'vector')").fetchone()
    print(f"pgvector {ext}: {n} recipe vectors, HNSW m={HNSW_M} ef_construction={HNSW_EF_CONSTRUCT}")
    print(f"qdrant: {info.points_count} points, {info.indexed_vectors_count} in HNSW, status {info.status.value}")


if __name__ == "__main__":
    main()
