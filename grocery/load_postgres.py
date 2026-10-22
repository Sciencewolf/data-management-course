"""Create the PostgreSQL schema and load the business data.

    python -m grocery.load_postgres
"""
import json

from grocery import stores
from grocery.config import DATA_DIR, ROOT


def read(name):
    return json.loads((DATA_DIR / f"{name}.json").read_text())


def main():
    with stores.postgres(vector=False) as conn:
        conn.execute((ROOT / "sql" / "postgres_schema.sql").read_text())
    with stores.postgres() as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany("INSERT INTO allergens VALUES (%(code)s, %(name)s)", read("allergens"))
        ingredients = read("ingredients")
        cur.executemany("INSERT INTO ingredients VALUES (%(id)s, %(name)s, %(category)s)", ingredients)
        cur.executemany("INSERT INTO ingredient_allergens VALUES (%s, %s)",
                        [(i["id"], a) for i in ingredients for a in i["allergens"]])
        cur.executemany("INSERT INTO ingredient_components VALUES (%s, %s)",
                        [(i["id"], c) for i in ingredients for c in i["components"]])
        cur.executemany("INSERT INTO ingredient_substitutes VALUES (%(ingredient_id)s, %(substitute_id)s)",
                        read("substitutes"))

        products = read("products")
        cur.executemany("INSERT INTO products VALUES (%(id)s, %(name)s, %(brand)s, %(category)s, %(package)s)",
                        products)
        cur.executemany("INSERT INTO product_ingredients VALUES (%s, %s)",
                        [(p["id"], i) for p in products for i in p["ingredient_ids"]])
        cur.executemany("INSERT INTO stock VALUES (%(id)s, %(stock)s, %(updated_at)s)", products)
        cur.executemany("INSERT INTO prices VALUES (%(id)s, %(unit_price)s, 'HUF', %(updated_at)s)", products)

        customers = read("customers")
        cur.executemany("INSERT INTO customers VALUES (%(id)s, %(name)s, %(email)s, %(created_at)s)", customers)
        cur.executemany("INSERT INTO customer_allergies VALUES (%s, %s)",
                        [(c["id"], a) for c in customers for a in c["allergy_codes"]])

        orders = read("orders")
        cur.executemany("INSERT INTO orders VALUES (%(id)s, %(customer_id)s, %(status)s, %(created_at)s)", orders)
        cur.executemany("INSERT INTO order_items VALUES (%s, %s, %s, %s)",
                        [(o["id"], i["product_id"], i["quantity"], i["unit_price"])
                         for o in orders for i in o["items"]])

        for table in ["allergens", "ingredients", "ingredient_allergens", "ingredient_components",
                      "ingredient_substitutes", "products", "product_ingredients", "stock", "prices",
                      "customers", "customer_allergies", "orders", "order_items"]:
            cur.execute(f"SELECT count(*) FROM {table}")
            print(f"postgres {table:24s} {cur.fetchone()[0]:5d} rows")


if __name__ == "__main__":
    main()
