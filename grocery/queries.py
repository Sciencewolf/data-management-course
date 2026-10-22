"""The required queries for PostgreSQL, MongoDB and Neo4j.

    python -m grocery.queries     # runs each one on an example recipe
"""
from grocery import stores

# PostgreSQL: can every product of a recipe be bought now, and at what total price?
RECIPE_AVAILABILITY_SQL = """
WITH wanted AS (SELECT DISTINCT unnest(%(product_ids)s::text[]) AS product_id)
SELECT bool_and(coalesce(s.quantity, 0) > 0)                         AS can_buy_now,
       sum(p.unit_price)                                              AS total_price,
       array_agg(w.product_id) FILTER (WHERE coalesce(s.quantity, 0) = 0) AS out_of_stock
FROM wanted w
LEFT JOIN stock  s USING (product_id)
LEFT JOIN prices p USING (product_id)
"""

# Neo4j: every allergen reachable from the recipe's products, through any depth
# of composite ingredients (product -> pesto -> parmesan -> MLK).
RECIPE_ALLERGENS_CYPHER = """
MATCH (p:Product) WHERE p.source_id IN $product_ids
MATCH (p)-[:CONTAINS*1..]->(:Ingredient)-[:HAS_ALLERGEN]->(a:Allergen)
RETURN collect(DISTINCT a.code) AS allergen_codes
"""

# Neo4j: for each ingredient that brings in one of the customer's allergens,
# the substitutes that reach none of those codes.
SAFE_SUBSTITUTES_CYPHER = """
MATCH (p:Product)-[:CONTAINS]->(i:Ingredient) WHERE p.source_id IN $product_ids
MATCH (i)-[:CONTAINS*0..]->(:Ingredient)-[:HAS_ALLERGEN]->(a:Allergen)
WHERE a.code IN $allergy_codes
WITH p, i, collect(DISTINCT a.code) AS allergens
OPTIONAL MATCH (i)-[:CAN_BE_REPLACED_BY]->(s:Ingredient)
WHERE NOT EXISTS {
    MATCH (s)-[:CONTAINS*0..]->(:Ingredient)-[:HAS_ALLERGEN]->(b:Allergen)
    WHERE b.code IN $allergy_codes
}
RETURN p.source_id AS product_id, i.source_id AS ingredient_id, allergens,
       collect(s.source_id) AS safe_substitutes
ORDER BY product_id, ingredient_id
"""

# Neo4j, batched: allergens of many recipes at once (used to build vector metadata).
RECIPES_ALLERGENS_CYPHER = """
UNWIND $recipes AS r
OPTIONAL MATCH (p:Product)-[:CONTAINS*1..]->(:Ingredient)-[:HAS_ALLERGEN]->(a:Allergen)
WHERE p.source_id IN r.product_ids
RETURN r.id AS recipe_id, collect(DISTINCT a.code) AS allergen_codes
"""


def recipe_availability(pg, product_ids):
    with pg.cursor() as cur:
        cur.execute(RECIPE_AVAILABILITY_SQL, {"product_ids": product_ids})
        can_buy, total, missing = cur.fetchone()
    return {"can_buy_now": can_buy, "total_price": total, "out_of_stock": missing or []}


def quick_recipes_with_product(db, product_id, max_minutes=30):
    """MongoDB: recipes under max_minutes that use the given product."""
    return list(db.recipes.find({"preparation_minutes": {"$lt": max_minutes}, "product_ids": product_id},
                                {"title": 1, "preparation_minutes": 1}).sort("preparation_minutes", 1))


def recipe_allergens(session, product_ids):
    return sorted(session.run(RECIPE_ALLERGENS_CYPHER, product_ids=product_ids).single()["allergen_codes"])


def safe_substitutes(session, product_ids, allergy_codes):
    return session.run(SAFE_SUBSTITUTES_CYPHER, product_ids=product_ids, allergy_codes=allergy_codes).data()


def allergens_for_recipes(session, recipes):
    """recipes: [{"id": ..., "product_ids": [...]}] -> {recipe_id: [codes]}"""
    rows = session.run(RECIPES_ALLERGENS_CYPHER, recipes=recipes).data()
    return {r["recipe_id"]: sorted(r["allergen_codes"]) for r in rows}


def main():
    db, pg, driver = stores.mongo(), stores.postgres(vector=False), stores.neo4j()
    recipe = db.recipes.find_one({"title": "Classic Pesto Pasta"})
    print(f"Recipe {recipe['_id']} {recipe['title']}: products {recipe['product_ids']}")
    print("PostgreSQL availability:", recipe_availability(pg, recipe["product_ids"]))
    with driver.session() as s:
        print("Neo4j allergens:", recipe_allergens(s, recipe["product_ids"]))
        for row in safe_substitutes(s, recipe["product_ids"], ["GLU", "MLK"]):
            print("Neo4j for GLU+MLK:", row)
    pid = recipe["product_ids"][-1]
    quick = quick_recipes_with_product(db, pid)
    print(f"MongoDB recipes under 30 min using {pid}: {[(r['_id'], r['title'], r['preparation_minutes']) for r in quick]}")
    driver.close()


if __name__ == "__main__":
    main()
