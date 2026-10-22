"""Load recipes into MongoDB (their system of record) with $jsonSchema validation.

    python -m grocery.load_mongo
"""
import json
from datetime import datetime

from pymongo import ASCENDING
from pymongo.errors import WriteError

from grocery import stores
from grocery.config import DATA_DIR

STEP_AS_TEXT = {"bsonType": "string", "minLength": 3}
STEP_AS_OBJECT = {
    "bsonType": "object",
    "required": ["order", "text"],
    "properties": {"order": {"bsonType": "int", "minimum": 1}, "text": {"bsonType": "string"},
                   "minutes": {"bsonType": "int", "minimum": 0}},
}

RECIPE_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "title", "cuisine", "course", "preparation_minutes", "product_ids", "steps"],
        "properties": {
            "_id": {"bsonType": "string", "pattern": "^R[0-9]{4}$"},
            "title": {"bsonType": "string", "minLength": 3},
            "cuisine": {"bsonType": "string"},
            "course": {"enum": ["breakfast", "lunch", "main", "soup", "salad", "side", "snack", "dessert"]},
            "preparation_minutes": {"bsonType": "int", "minimum": 1, "maximum": 600},
            "servings": {"bsonType": "int", "minimum": 1},
            "description": {"bsonType": "string"},
            "product_ids": {"bsonType": "array", "minItems": 1,
                            "items": {"bsonType": "string", "pattern": "^P[0-9]{4}$"}},
            # steps are either plain strings or {order, text, minutes} objects
            "steps": {"bsonType": "array", "minItems": 1, "items": {"oneOf": [STEP_AS_TEXT, STEP_AS_OBJECT]}},
            "nutrition": {"bsonType": "object"},
            "tags": {"bsonType": "array", "items": {"enum": ["vegetarian", "vegan"]}},
        },
    }
}


def main():
    db = stores.mongo()
    db.drop_collection("recipes")
    db.create_collection("recipes", validator=RECIPE_SCHEMA, validationAction="error",
                         validationLevel="strict")
    recipes = json.loads((DATA_DIR / "recipes.json").read_text())
    for r in recipes:
        r["created_at"] = datetime.fromisoformat(r["created_at"])
        r["updated_at"] = r["created_at"]
    db.recipes.insert_many(recipes)
    db.recipes.create_index([("product_ids", ASCENDING), ("preparation_minutes", ASCENDING)])
    db.recipes.create_index("cuisine")
    print(f"mongo recipes {db.recipes.count_documents({})} documents")

    try:  # the validator must reject a recipe without product_ids
        db.recipes.insert_one({"_id": "R9999", "title": "Broken", "cuisine": "x", "course": "main",
                               "preparation_minutes": 10, "steps": ["Mix."]})
        print("mongo validation: NOT ENFORCED (unexpected)")
    except WriteError as e:
        print(f"mongo validation: rejected invalid recipe (code {e.code})")


if __name__ == "__main__":
    main()
