"""
Session management — stores conversation history + cart state in Redis.
Each session key: session:{cleaned_number}
"""
import json
from typing import Optional
from upstash_redis import Redis
from config import REDIS_URL, REDIS_TOKEN, SESSION_TTL, MAX_HISTORY


redis = Redis(url=REDIS_URL, token=REDIS_TOKEN)


# ─── Schema ────────────────────────────────────────────────────────────────
# session = {
#   "history": [{"role": "user"|"assistant", "content": str}],
#   "cart": [{"product_id": int, "name": str, "qty": float, "unit": str,
#             "price": float, "pack_type": 0|1}],
#   "customer": {"id": int, "name": str, "address_id": int},
#   "last_product": str,          # last product discussed
#   "awaiting_confirmation": bool # True when we showed cart & asked for Yes/No
# }

def _key(number: str) -> str:
    return f"session:{number}"


def get_session(number: str) -> dict:
    raw = redis.get(_key(number))
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {
        "history": [],
        "cart": [],
        "customer": {},
        "last_product": "",
        "awaiting_confirmation": False,
    }


def save_session(number: str, session: dict):
    # Trim history to MAX_HISTORY turns (each turn = 2 messages)
    if len(session["history"]) > MAX_HISTORY * 2:
        session["history"] = session["history"][-(MAX_HISTORY * 2):]
    redis.set(_key(number), json.dumps(session), ex=SESSION_TTL)


def clear_session(number: str):
    redis.delete(_key(number))


# ─── Helpers ───────────────────────────────────────────────────────────────
def append_history(session: dict, role: str, content: str):
    session["history"].append({"role": role, "content": content})


def set_cart(session: dict, items: list):
    session["cart"] = items


def clear_cart(session: dict):
    session["cart"] = []


def set_awaiting(session: dict, value: bool):
    session["awaiting_confirmation"] = value


def update_customer(session: dict, customer_data: dict):
    session["customer"].update(customer_data)


def set_last_product(session: dict, product: str):
    if product:
        session["last_product"] = product
