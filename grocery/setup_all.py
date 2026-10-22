"""Generate the data and load all five stores in dependency order.

PostgreSQL first (system of record), then MongoDB (recipes), then the derived
copies: Neo4j from PostgreSQL, vectors from MongoDB + Neo4j, Redis carts.

    python -m grocery.setup_all
"""
from grocery import cart, generate, load_mongo, load_neo4j, load_postgres, load_vectors


def main():
    for step in (generate, load_postgres, load_mongo, load_neo4j, load_vectors, cart):
        print(f"\n== {step.__name__} ==")
        step.main()


if __name__ == "__main__":
    main()
