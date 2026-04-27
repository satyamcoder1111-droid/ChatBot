"""
Session management — stores full conversation state per customer.
State includes: chat history, cart contents, last product, order stage.
"""

import json
import re
from upstash_redis import Redis
from config.settings import REDIS_URL, REDIS_TOKEN

redis = Redis(url=REDIS_URL, token=REDIS_TOKEN)

SESSION_TTL = 86400   # 24 hours


# ─────────────────────────────────────────────────────────────────────
# KEY HELPERS
# ─────────────────────────────────────────────────────────────────────

def clean_number(raw: str) -> str:
    return re.sub(r"^\+?(91|971)", "", str(raw))


def _session_key(number: str) -> str:
    return f"session:v2:{clean_number(number)}"


# ─────────────────────────────────────────────────────────────────────
# SESSION SCHEMA
# {
#   "history":       [...],          # last N (user/assistant) turns
#   "cart":          [...],          # validated cart items
#   "cart_total":    0.0,            # AED total
#   "last_product":  "",             # last discussed product name
#   "stage":         "idle",         # idle | awaiting_qty | awaiting_confirm | ordered
#   "customer_name": "",
#   "customer_id":   "",
#   "address_id":    "",
# }
# ─────────────────────────────────────────────────────────────────────

DEFAULT_STATE: dict = {
    "history":       [],
    "cart":          [],
    "cart_total":    0.0,
    "previous_cart": [],
    "previous_cart_total": 0.0,
    "last_product":  "",
    "last_lookup_product": "",
    "stage":         "idle",
    "customer_name": "",
    "customer_id":   "",
    "address_id":    "",
    "last_order":    {},
    "pending_orders": [],
}


def get_session(number: str) -> dict:
    try:
        raw = redis.get(_session_key(number))
        if raw:
            data = json.loads(raw)
            # backfill any new keys that didn't exist when session was saved
            for k, v in DEFAULT_STATE.items():
                data.setdefault(k, v)
            return data
    except Exception as e:
        print(f"[SESSION GET ERROR] {e}")
    return dict(DEFAULT_STATE)


def save_session(number: str, state: dict) -> None:
    try:
        # keep last 10 history turns
        state["history"] = state.get("history", [])[-10:]
        redis.set(_session_key(number), json.dumps(state), ex=SESSION_TTL)
    except Exception as e:
        print(f"[SESSION SAVE ERROR] {e}")


def append_history(state: dict, role: str, content: str) -> dict:
    """Add a message to history; role = 'human' | 'assistant'."""
    state["history"].append({"role": role, "content": content})
    return state


def clear_cart(state: dict) -> dict:
    state["cart"]       = []
    state["cart_total"] = 0.0
    state["stage"]      = "idle"
    return state


def set_stage(state: dict, stage: str) -> dict:
    state["stage"] = stage
    return state
