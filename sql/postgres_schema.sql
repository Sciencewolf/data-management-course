-- PostgreSQL: system of record for business entities (products, stock, prices,
-- customers with allergies, orders) and for the product -> ingredient -> allergen
-- reference data that Neo4j copies. recipe_vectors is a derived copy of MongoDB recipes.
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS recipe_vectors, order_items, orders, customer_allergies, customers,
    prices, stock, product_ingredients, products, ingredient_substitutes,
    ingredient_components, ingredient_allergens, ingredients, allergens CASCADE;

CREATE TABLE allergens (
    code        char(3) PRIMARY KEY,
    name        text NOT NULL
);

CREATE TABLE ingredients (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    category    text NOT NULL
);

CREATE TABLE ingredient_allergens (
    ingredient_id text    REFERENCES ingredients(id),
    allergen_code char(3) REFERENCES allergens(code),
    PRIMARY KEY (ingredient_id, allergen_code)
);

-- composite ingredients: pesto is made of basil, pine nuts, parmesan, olive oil
CREATE TABLE ingredient_components (
    parent_id    text REFERENCES ingredients(id),
    component_id text REFERENCES ingredients(id),
    PRIMARY KEY (parent_id, component_id),
    CHECK (parent_id <> component_id)
);

CREATE TABLE ingredient_substitutes (
    ingredient_id text REFERENCES ingredients(id),
    substitute_id text REFERENCES ingredients(id),
    PRIMARY KEY (ingredient_id, substitute_id)
);

CREATE TABLE products (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    brand       text NOT NULL,
    category    text NOT NULL,
    package     text NOT NULL
);

CREATE TABLE product_ingredients (
    product_id    text REFERENCES products(id),
    ingredient_id text REFERENCES ingredients(id),
    PRIMARY KEY (product_id, ingredient_id)
);

CREATE TABLE stock (
    product_id  text PRIMARY KEY REFERENCES products(id),
    quantity    integer NOT NULL CHECK (quantity >= 0),
    updated_at  timestamptz NOT NULL
);

CREATE TABLE prices (
    product_id  text PRIMARY KEY REFERENCES products(id),
    unit_price  numeric(10, 2) NOT NULL CHECK (unit_price > 0),
    currency    char(3) NOT NULL DEFAULT 'HUF',
    updated_at  timestamptz NOT NULL
);

CREATE TABLE customers (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    email       text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL
);

CREATE TABLE customer_allergies (
    customer_id   text    REFERENCES customers(id),
    allergen_code char(3) REFERENCES allergens(code),
    PRIMARY KEY (customer_id, allergen_code)
);

CREATE TABLE orders (
    id          text PRIMARY KEY,
    customer_id text NOT NULL REFERENCES customers(id),
    status      text NOT NULL CHECK (status IN ('delivered', 'shipped', 'cancelled')),
    created_at  timestamptz NOT NULL
);

CREATE TABLE order_items (
    order_id    text    REFERENCES orders(id),
    product_id  text    REFERENCES products(id),
    quantity    integer NOT NULL CHECK (quantity > 0),
    unit_price  numeric(10, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
CREATE INDEX ON orders (customer_id);

-- Derived from MongoDB recipes; allergen_codes come from the Neo4j traversal.
CREATE TABLE recipe_vectors (
    recipe_id           text PRIMARY KEY,          -- source id: MongoDB recipes._id
    title               text NOT NULL,
    cuisine             text NOT NULL,
    preparation_minutes integer NOT NULL,
    allergen_codes      text[] NOT NULL,
    product_ids         text[] NOT NULL,
    embedding           vector(384) NOT NULL,      -- all-MiniLM-L6-v2, normalised
    refreshed_at        timestamptz NOT NULL
);
CREATE INDEX recipe_vectors_hnsw ON recipe_vectors
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
-- No btree on cuisine on purpose: with it the planner answers filtered queries
-- exactly and the HNSW post-filtering behaviour could not be measured.
