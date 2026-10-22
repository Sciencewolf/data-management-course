"""Generate the synthetic data set into data/*.json.

Source: synthetic, produced by this script from the hand-written catalog in
grocery/catalog.py with a fixed seed, so every run gives identical files.

    python -m grocery.generate
"""
import json
import random
from datetime import datetime, timedelta, timezone

from grocery.catalog import (ALLERGENS, BRANDS, DISHES, FIRST_NAMES, INGREDIENTS, LAST_NAMES,
                             PROTEIN_LABELS, SPECIAL_PRODUCTS, SUBSTITUTES)
from grocery.config import DATA_DIR

SEED = 42
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

PRICE_RANGE_HUF = {
    "grain": (390, 1490), "bakery": (490, 1290), "baking": (190, 590), "dairy": (390, 2990),
    "alternative": (590, 1890), "protein": (890, 1990), "meat": (1490, 5990), "fish": (1990, 7990),
    "shellfish": (2490, 8990), "legume": (290, 990), "nut": (990, 3490), "seed": (590, 2490),
    "spice": (290, 1290), "vegetable": (190, 990), "fruit": (290, 1490), "herb": (290, 690),
    "sauce": (490, 1990), "drink": (590, 3990), "stock": (290, 890), "oil": (790, 4990),
    "sweet": (390, 2490),
}
PACKAGES = {
    "grain": ["500 g", "1 kg"], "bakery": ["400 g", "500 g"], "baking": ["10 g", "100 g"],
    "dairy": ["200 g", "250 g", "1 l"], "alternative": ["400 ml", "1 l", "200 g"],
    "protein": ["200 g", "400 g"], "meat": ["400 g", "500 g", "1 kg"], "fish": ["200 g", "300 g"],
    "shellfish": ["250 g", "500 g"], "legume": ["400 g", "500 g"], "nut": ["100 g", "200 g"],
    "seed": ["150 g", "300 g"], "spice": ["30 g", "50 g"], "vegetable": ["500 g", "1 kg", "1 pc"],
    "fruit": ["500 g", "1 kg"], "herb": ["20 g", "1 bunch"], "sauce": ["150 ml", "250 ml"],
    "drink": ["330 ml", "750 ml"], "stock": ["500 ml", "10 cubes"], "oil": ["500 ml", "1 l"],
    "sweet": ["100 g", "250 g"],
}
AMOUNTS = {
    "spice": ["1 tsp", "2 tsp", "1 tbsp"], "herb": ["1 handful", "2 tbsp chopped"],
    "oil": ["1 tbsp", "2 tbsp", "3 tbsp"], "sauce": ["1 tbsp", "2 tbsp", "100 ml"],
    "stock": ["500 ml", "1 l"], "drink": ["100 ml", "200 ml"], "baking": ["1 tsp", "7 g"],
    "sweet": ["2 tbsp", "100 g"], "dairy": ["100 g", "200 ml", "250 g"], "fruit": ["1 pc", "2 pcs", "200 g"],
    "vegetable": ["1 pc", "2 pcs", "200 g", "400 g"], "nut": ["50 g", "100 g"], "seed": ["1 tbsp", "50 g"],
}
DEFAULT_AMOUNTS = ["200 g", "250 g", "400 g", "500 g"]
ALLERGY_WEIGHTS = {"MLK": 20, "GLU": 18, "NUT": 12, "PNT": 12, "EGG": 9, "SOY": 7, "CRU": 6,
                   "FSH": 5, "SES": 5, "CEL": 3, "MUS": 2, "SUL": 2, "MOL": 2, "LUP": 1}


def reachable_ingredients(ingredient_id):
    """The ingredient plus everything it is made of (used for diet tags only)."""
    seen, stack = set(), [ingredient_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(INGREDIENTS[current][3].split())
    return seen


def iso(dt):
    return dt.isoformat()


def build_ingredients():
    ingredients = [
        {"id": iid, "name": name, "category": cat,
         "allergens": codes.split(), "components": comps.split()}
        for iid, (name, cat, codes, comps) in INGREDIENTS.items()
    ]
    for ing in ingredients:
        for ref in ing["components"]:
            assert ref in INGREDIENTS, f"{ing['id']} -> unknown component {ref}"
    for a, b in SUBSTITUTES:
        assert a in INGREDIENTS and b in INGREDIENTS, (a, b)
    return ingredients


def build_products(rng):
    products, by_ingredient = [], {}
    for iid, (name, cat, _, _) in INGREDIENTS.items():
        brands = BRANDS[cat][: rng.randint(1, len(BRANDS[cat]))]
        for brand in brands:
            pid = f"P{len(products) + 1:04d}"
            package = rng.choice(PACKAGES[cat])
            products.append({"id": pid, "name": f"{brand} {name.title()} {package}", "brand": brand,
                             "category": cat, "package": package, "ingredient_ids": [iid]})
            by_ingredient.setdefault(iid, []).append(pid)
    for iid, label, contents in SPECIAL_PRODUCTS:
        pid = f"P{len(products) + 1:04d}"
        cat = INGREDIENTS[iid][1]
        products.append({"id": pid, "name": label, "brand": label.split(" ")[0], "category": cat,
                         "package": label.rsplit(" ", 2)[-2] + " " + label.rsplit(" ", 1)[-1],
                         "ingredient_ids": contents.split()})
        by_ingredient[iid].append(pid)
    for p in products:
        lo, hi = PRICE_RANGE_HUF[p["category"]]
        p["unit_price"] = round(rng.uniform(lo, hi) / 10) * 10 - 1  # 1490-style prices
        p["stock"] = 0 if rng.random() < 0.08 else rng.randint(3, 250)
        p["updated_at"] = iso(NOW - timedelta(hours=rng.randint(1, 72)))
    return products, by_ingredient


def diet_tags(ingredient_ids):
    everything = set().union(*(reachable_ingredients(i) for i in ingredient_ids))
    cats = {INGREDIENTS[i][1] for i in everything}
    tags = []
    if not cats & {"meat", "fish", "shellfish"}:
        tags.append("vegetarian")
        if "dairy" not in cats and "honey" not in everything:
            tags.append("vegan")
    return tags


def make_steps(rng, title, ingredient_names, minutes):
    texts = [
        f"Prepare the ingredients: {', '.join(ingredient_names[:4])}.",
        f"Cook or assemble the main components: {ingredient_names[0]} and {ingredient_names[1]}.",
        "Combine everything, season to taste and adjust the consistency.",
        f"Serve the {title.lower()} warm." if minutes > 10 else f"Serve the {title.lower()}.",
    ]
    if rng.random() < 0.5:  # two document shapes: plain strings, or structured steps
        return texts
    split = [max(1, minutes // 4)] * 4
    return [{"order": i + 1, "text": t, "minutes": m} for i, (t, m) in enumerate(zip(texts, split))]


def make_nutrition(rng):
    kcal = rng.randint(180, 950)
    shape = rng.random()
    if shape < 0.45:
        return {"per_serving": {"kcal": kcal, "protein_g": rng.randint(4, 55),
                                "fat_g": rng.randint(2, 60), "carbs_g": rng.randint(5, 120)}}
    if shape < 0.8:
        return {"per_100g": {"kcal": round(kcal / 3.5), "fibre_g": round(rng.uniform(0.5, 9), 1)},
                "salt_g": round(rng.uniform(0.1, 3.0), 2)}
    return None  # some recipes have no nutrition info at all


def build_recipes(rng, by_ingredient):
    recipes = []
    for cuisine, dishes in DISHES.items():
        for title, course, minutes, ingredient_ids, desc, proteins in dishes:
            base = ingredient_ids.split()
            variants = proteins.split() if proteins else [None]
            for variant in variants:
                if variant is None:
                    name, extra, with_text = title, [], ""
                elif variant.startswith("-:"):
                    name, extra, with_text = title.format(p=variant[2:]), [], ""
                else:
                    label = PROTEIN_LABELS.get(variant, INGREDIENTS[variant][0].title())
                    name, extra = title.format(p=label), [variant]
                    with_text = f" with {INGREDIENTS[variant][0]}"
                used = extra + [i for i in base if i not in extra]
                for i in used:
                    assert i in INGREDIENTS, f"{name}: unknown ingredient {i}"
                prep = max(5, minutes + rng.choice([-5, 0, 0, 0, 5, 10]))
                rid = f"R{len(recipes) + 1:04d}"
                products = [rng.choice(by_ingredient[i]) for i in used]
                doc = {
                    "_id": rid,
                    "title": name,
                    "cuisine": cuisine,
                    "course": course,
                    "preparation_minutes": prep,
                    "servings": rng.choice([2, 2, 4, 4, 4, 6]),
                    "description": desc.format(pw=with_text) + f" Ready in about {prep} minutes.",
                    "product_ids": products,
                    "ingredients": [{"ingredient_id": i, "product_id": p,
                                     "amount": "2 pcs" if i == "egg" else
                                               rng.choice(AMOUNTS.get(INGREDIENTS[i][1], DEFAULT_AMOUNTS))}
                                    for i, p in zip(used, products)],
                    "steps": make_steps(rng, name, [INGREDIENTS[i][0] for i in used], prep),
                    "tags": diet_tags(used),
                    "created_at": iso(NOW - timedelta(days=rng.randint(1, 700))),
                }
                nutrition = make_nutrition(rng)
                if nutrition:
                    doc["nutrition"] = nutrition
                if rng.random() < 0.3:
                    doc["equipment"] = rng.sample(["wok", "oven", "blender", "grill pan", "stock pot",
                                                   "baking tray", "food processor"], 2)
                recipes.append(doc)
    return recipes


def build_customers(rng, n=500):
    codes, weights = zip(*ALLERGY_WEIGHTS.items())
    customers = []
    for i in range(1, n + 1):
        r = rng.random()
        k = 0 if r < 0.55 else 1 if r < 0.82 else rng.randint(2, 4)
        allergies = set()
        while len(allergies) < k:
            allergies.add(rng.choices(codes, weights)[0])
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        customers.append({"id": f"C{i:04d}", "name": f"{first} {last}",
                          "email": f"customer{i:04d}@example.com",
                          "allergy_codes": sorted(allergies),
                          "created_at": iso(NOW - timedelta(days=rng.randint(30, 900)))})
    return customers


def build_orders(rng, customers, products, n=800):
    orders = []
    for i in range(1, n + 1):
        items = rng.sample(products, rng.randint(1, 6))
        orders.append({"id": f"O{i:05d}", "customer_id": rng.choice(customers)["id"],
                       "created_at": iso(NOW - timedelta(minutes=rng.randint(60, 180 * 24 * 60))),
                       "status": rng.choices(["delivered", "shipped", "cancelled"], [85, 10, 5])[0],
                       "items": [{"product_id": p["id"], "quantity": rng.randint(1, 4),
                                  "unit_price": p["unit_price"]} for p in items]})
    return orders


def build_carts(rng, customers, products, n=300):
    return [{"customer_id": c["id"],
             "items": {p["id"]: rng.randint(1, 3) for p in rng.sample(products, rng.randint(1, 8))}}
            for c in rng.sample(customers, n)]


def main():
    rng = random.Random(SEED)
    ingredients = build_ingredients()
    products, by_ingredient = build_products(rng)
    recipes = build_recipes(rng, by_ingredient)
    customers = build_customers(rng)
    orders = build_orders(rng, customers, products)
    carts = build_carts(rng, customers, products)
    files = {
        "allergens": [{"code": c, "name": n} for c, n in ALLERGENS.items()],
        "ingredients": ingredients,
        "substitutes": [{"ingredient_id": a, "substitute_id": b} for a, b in SUBSTITUTES],
        "products": products,
        "recipes": recipes,
        "customers": customers,
        "orders": orders,
        "carts": carts,
    }
    DATA_DIR.mkdir(exist_ok=True)
    for name, rows in files.items():
        (DATA_DIR / f"{name}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        print(f"{name:12s} {len(rows):5d} records -> data/{name}.json")


if __name__ == "__main__":
    main()
