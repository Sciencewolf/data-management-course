"""Shopping cart per customer in Redis.

Key cart:{customer_id} is a hash of product_id -> quantity. Every write resets
the TTL, so a cart expires after CART_TTL_SECONDS of inactivity. The field
_updated_at records the last change; the customer id in the key is the source id.

    python -m grocery.cart   # seeds the generated carts
"""
import json
from datetime import datetime, timezone

from grocery import stores
from grocery.config import CART_TTL_SECONDS, DATA_DIR

META = "_updated_at"


def key(customer_id):
    return f"cart:{customer_id}"


def _touch(r, customer_id, ttl):
    pipe = r.pipeline()
    pipe.hset(key(customer_id), META, datetime.now(timezone.utc).isoformat())
    pipe.expire(key(customer_id), ttl)
    pipe.execute()


def add(r, customer_id, product_id, quantity=1, ttl=CART_TTL_SECONDS):
    r.hincrby(key(customer_id), product_id, quantity)
    _touch(r, customer_id, ttl)


def remove(r, customer_id, product_id, ttl=CART_TTL_SECONDS):
    r.hdel(key(customer_id), product_id)
    _touch(r, customer_id, ttl)


def read(r, customer_id):
    """Items in the cart; reading does not extend the TTL."""
    return {pid: int(q) for pid, q in r.hgetall(key(customer_id)).items() if pid != META}


def main():
    r = stores.redis_client()
    for k in r.scan_iter("cart:*"):
        r.delete(k)
    carts = json.loads((DATA_DIR / "carts.json").read_text())
    for cart in carts:
        for pid, qty in cart["items"].items():
            r.hset(key(cart["customer_id"]), pid, qty)
        _touch(r, cart["customer_id"], CART_TTL_SECONDS)
    print(f"redis carts {sum(1 for _ in r.scan_iter('cart:*'))} keys, TTL {CART_TTL_SECONDS}s")


if __name__ == "__main__":
    main()
