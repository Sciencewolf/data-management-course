"""Copy the product -> ingredient -> allergen graph from PostgreSQL into Neo4j.

The graph is derived: every node keeps its PostgreSQL source id and refreshed_at.

    python -m grocery.load_neo4j
"""
from datetime import datetime, timezone

from grocery import stores

CONSTRAINTS = [
    "CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.source_id IS UNIQUE",
    "CREATE CONSTRAINT ingredient_id IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.source_id IS UNIQUE",
    "CREATE CONSTRAINT allergen_code IF NOT EXISTS FOR (a:Allergen) REQUIRE a.code IS UNIQUE",
]


def fetch(cur, sql):
    cur.execute(sql)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def main():
    with stores.postgres(vector=False) as conn, conn.cursor() as cur:
        allergens = fetch(cur, "SELECT code, name FROM allergens")
        ingredients = fetch(cur, "SELECT id, name, category FROM ingredients")
        products = fetch(cur, "SELECT id, name FROM products")
        has_allergen = fetch(cur, "SELECT ingredient_id AS src, allergen_code AS dst FROM ingredient_allergens")
        components = fetch(cur, "SELECT parent_id AS src, component_id AS dst FROM ingredient_components")
        substitutes = fetch(cur, "SELECT ingredient_id AS src, substitute_id AS dst FROM ingredient_substitutes")
        contains = fetch(cur, "SELECT product_id AS src, ingredient_id AS dst FROM product_ingredients")

    now = datetime.now(timezone.utc).isoformat()
    driver = stores.neo4j()
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        for c in CONSTRAINTS:
            s.run(c)
        s.run("UNWIND $rows AS r MERGE (a:Allergen {code: r.code}) SET a.name = r.name, a.refreshed_at = $now",
              rows=allergens, now=now)
        s.run("UNWIND $rows AS r MERGE (i:Ingredient {source_id: r.id}) "
              "SET i.name = r.name, i.category = r.category, i.refreshed_at = $now", rows=ingredients, now=now)
        s.run("UNWIND $rows AS r MERGE (p:Product {source_id: r.id}) SET p.name = r.name, p.refreshed_at = $now",
              rows=products, now=now)
        s.run("UNWIND $rows AS r MATCH (p:Product {source_id: r.src}), (i:Ingredient {source_id: r.dst}) "
              "MERGE (p)-[:CONTAINS]->(i)", rows=contains)
        s.run("UNWIND $rows AS r MATCH (a:Ingredient {source_id: r.src}), (b:Ingredient {source_id: r.dst}) "
              "MERGE (a)-[:CONTAINS]->(b)", rows=components)
        s.run("UNWIND $rows AS r MATCH (i:Ingredient {source_id: r.src}), (a:Allergen {code: r.dst}) "
              "MERGE (i)-[:HAS_ALLERGEN]->(a)", rows=has_allergen)
        s.run("UNWIND $rows AS r MATCH (a:Ingredient {source_id: r.src}), (b:Ingredient {source_id: r.dst}) "
              "MERGE (a)-[:CAN_BE_REPLACED_BY]->(b)", rows=substitutes)
        counts = s.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label").data()
        rels = s.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY type").data()
    driver.close()
    for row in counts:
        print(f"neo4j :{row['label']:12s} {row['n']:5d} nodes")
    for row in rels:
        print(f"neo4j [:{row['type']}] {row['n']:5d} relationships")


if __name__ == "__main__":
    main()
