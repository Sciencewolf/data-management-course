# data-management-course
Data Management Course project: **Recipe and grocery service with allergens** (project 5).

The service suggests recipes that are safe for a customer's allergies and whose ingredients
are in stock. It uses PostgreSQL, MongoDB, Redis and Neo4j, and runs the vector search
twice, in pgvector and in Qdrant.

- Data model of all five stores: [docs/data_model.md](docs/data_model.md)
- Measurement plan and baseline results: [docs/measurement_plan.md](docs/measurement_plan.md)

## First-time setup

Needs Docker Desktop and Python 3.12+. Run every command from the project folder.

```bash
docker compose up -d
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m grocery.setup_all          # generate data, load all five stores (~1 min)
```

MongoDB is pinned to 8.2.12 because 8.0 does not start on Linux kernels 6.19 and newer
(SERVER-121912), which recent Docker Desktop versions use.

## Every time you start

1. Open **Docker Desktop**, then start the databases:

   ```bash
   docker compose up -d
   ```

2. Shopping carts in Redis expire after 30 minutes on purpose. Refill them before a demo:

   ```bash
   .venv/bin/python -m grocery.cart
   ```

3. If anything looks wrong, rebuild everything from scratch with `.venv/bin/python -m grocery.setup_all`.
   Running `load_postgres` on its own also empties the pgvector table, so prefer `setup_all`.

## Using it

### Recommend safe recipes (the main demo)

```bash
.venv/bin/python -m grocery.search "quick vegetarian dinner" --customer C0007
```

C0007 is allergic to EGG, GLU, MLK and NUT. The output shows the top 5 recipes from
**pgvector** (one SQL statement) and from **Qdrant** (three steps), with prices.
Try other requests and customers, e.g. C0002 (CRU, GLU, PNT, SOY):

```bash
.venv/bin/python -m grocery.search "spicy Thai curry" --customer C0002
```

### Required queries and measurements

| Command | What it shows |
|---|---|
| `.venv/bin/python -m grocery.queries` | PostgreSQL: can the recipe be bought now, total price; Neo4j: its allergens and safe substitutes; MongoDB: recipes under 30 min using a product |
| `.venv/bin/python -m grocery.compare_vectors` | pgvector vs Qdrant: ANN recall@10, shared ids, the 5 % filter test, latency |
| `.venv/bin/python -m grocery.evaluate` | safety (0 unsafe recipes) and recall@5 / MRR |

`compare_vectors` and `evaluate` also save their output in `results/`.

## Showing each store

Local development credentials are in `docker-compose.yml` / `.env.example`.

### Neo4j graph: http://localhost:7474

Log in with user `neo4j` and the password from `docker-compose.yml`. Allergens hidden inside the pesto products:

```cypher
MATCH path = (p:Product)-[:CONTAINS*1..]->(:Ingredient)-[:HAS_ALLERGEN]->(:Allergen)
WHERE p.name CONTAINS 'Pesto'
RETURN path
```

Why oat drink is not a safe milk substitute for a gluten allergy:

```cypher
MATCH path = (:Ingredient {source_id: 'milk'})-[:CAN_BE_REPLACED_BY]->(s)
OPTIONAL MATCH hidden = (s)-[:CONTAINS*0..]->()-[:HAS_ALLERGEN]->()
RETURN path, hidden
```

### Qdrant dashboard: http://localhost:6333/dashboard

Collections → `recipes` shows the 224 points with their metadata (cuisine, allergen codes, product ids).

### MongoDB

The `$jsonSchema` validator rejects a recipe without `product_ids`:

```bash
docker compose exec mongo mongosh grocery --eval 'db.recipes.insertOne({_id:"R9999",title:"Broken",cuisine:"x",course:"main",preparation_minutes:10,steps:["Mix."]})'
```

### Redis

List some cart keys (run `grocery.cart` first if they expired):

```bash
docker compose exec redis redis-cli --scan --pattern 'cart:*' --count 1000 | head -3
```

Then, with one of the printed keys (e.g. `cart:C0123`), show its contents and remaining seconds:

```bash
docker compose exec redis redis-cli HGETALL cart:C0123
```

```bash
docker compose exec redis redis-cli TTL cart:C0123
```

### PostgreSQL

Opens a database console; `\dt` lists the tables, `\q` quits:

```bash
docker compose exec postgres psql -U grocery
```

## Suggested 10-minute presentation (week 7)

1. **The goal (1 min):** safe recipes, ingredients in stock.
2. **Data model (3 min):** walk through [docs/data_model.md](docs/data_model.md), one reason per store; show the Neo4j pesto graph live.
3. **Vector search in both systems (3 min):** run `grocery.search`; pgvector answers in one SQL statement, Qdrant needs three steps.
4. **Measurement plan (3 min):** walk through [docs/measurement_plan.md](docs/measurement_plan.md); run `grocery.compare_vectors` and point at the pgvector line that returns only 2 results with the filter.

## Layout

| Path | What |
|---|---|
| `grocery/catalog.py` | hand-written reference data: allergens, ingredients, substitutes, dish templates |
| `grocery/generate.py` | synthetic data generator (seed 42) → `data/*.json` |
| `grocery/load_*.py`, `grocery/cart.py` | loaders for each store; `cart.py` is also the Redis cart API |
| `grocery/queries.py` | required queries for PostgreSQL, MongoDB and Neo4j |
| `grocery/search.py` | vector search in pgvector and Qdrant, and the joined single-SQL query |
| `grocery/compare_vectors.py`, `grocery/evaluate.py` | measurements; output also saved in `results/` |
| `sql/postgres_schema.sql` | PostgreSQL DDL including the pgvector table |
| `tests/cases/` | test cases and labels, written before tuning |
