"""
LangChain @tools — one tool per discrete operation
The chain (not an agent) calls these explicitly based on intent.
"""

import json
import re
import requests
from langchain_core.tools import tool
from config.settings import (
    CHATBOT_API_URL, PRESTA_REST_URL, PRESTA_API_KEY,
    STORE_CURRENCY
)


# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def _print_tool_payload(tool_name: str, payload_type: str, payload) -> None:
    """Print the outgoing payload for easier debugging."""
    if isinstance(payload, (dict, list)):
        formatted = json.dumps(payload, ensure_ascii=True, indent=2)
    else:
        formatted = str(payload)
    print(f"[{tool_name}] {payload_type} payload:\n{formatted}")

def _chatbot_post(payload: dict) -> dict:
    """POST to the custom Delidel chatbot module endpoint."""
    try:
        res = requests.post(CHATBOT_API_URL, data=payload, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"[API POST ERROR] {e}")
        return {}


def _chatbot_get(params: dict) -> dict:
    """GET to the custom Delidel chatbot module endpoint."""
    try:
        res = requests.get(
            CHATBOT_API_URL,
            params=params,
            headers={"x-api-key": PRESTA_API_KEY},
            timeout=30,
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"[API GET ERROR] {e}")
        return {}


def _presta_get(endpoint: str, params: dict = None) -> dict:
    """
    Native PrestaShop REST API call.
    Auth: HTTP Basic with API key as username, empty password.
    Always request JSON output.
    """
    url = f"{PRESTA_REST_URL}/{endpoint}"
    params = params or {}
    params["output_format"] = "JSON"
    try:
        res = requests.get(url, params=params, auth=(PRESTA_API_KEY, ""), timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"[PRESTA GET ERROR] {e}")
        return {}


def _presta_post(endpoint: str, xml_body: str) -> dict:
    """
    POST to PrestaShop REST — PrestaShop REST only accepts XML for writes.
    Returns parsed JSON of the created resource.
    """
    url = f"{PRESTA_REST_URL}/{endpoint}?output_format=JSON"
    headers = {"Content-Type": "application/xml"}
    try:
        res = requests.post(
            url, data=xml_body.encode("utf-8"),
            headers=headers, auth=(PRESTA_API_KEY, ""), timeout=30
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"[PRESTA POST ERROR] {e}")
        return {}


def clean_number(raw: str) -> str:
    return re.sub(r"^\+?(91|971)", "", str(raw))


# ══════════════════════════════════════════════════════════════════════
# TOOL 1 — Product Search  (price + stock)
# ══════════════════════════════════════════════════════════════════════

@tool
def search_products(product_name: str, sender_number: str) -> str:
    """
    Search for products by name. Returns a JSON string with:
    customer_name, and a list of products with name, price, stock.
    Use this when the user asks for price or availability.
    """
    params = {
        "action":       "getproductdetails",
        "product_name": product_name,
        "page":         1,
        "per_page":     10,
        "phoneNumber":  clean_number(sender_number),
    }
    _print_tool_payload("search_products", "GET", params)
    data = _chatbot_get(params)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 2 — Validate Cart
# ══════════════════════════════════════════════════════════════════════

@tool
def validate_cart(sender_number: str, product_json: list) -> str:
    """
    Validate a list of products and quantities against live inventory.
    product_json: list of {product_name, qty, pack_type (0=pack,1=ctn)}.
    Returns a JSON string with cart summary, totals, matched products.
    """
    payload = {
        "action":        "validate_cart",
        "sender_number": clean_number(sender_number),
        "product_json":  json.dumps(product_json),
    }
    _print_tool_payload("validate_cart", "POST", payload)
    data = _chatbot_post(payload)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 3 — Get Customer Info  (from PrestaShop by phone)
# ══════════════════════════════════════════════════════════════════════

@tool
def get_customer_by_phone(phone_number: str) -> str:
    """
    Fetch PrestaShop customer record using their phone number.
    Returns JSON with id_customer, firstname, lastname, id_default_group.
    """
    cleaned = clean_number(phone_number)
    # PrestaShop can filter on phone field in addresses
    params = {"filter[phone]": f"[%{cleaned}%]", "display": "full"}
    _print_tool_payload("get_customer_by_phone", "GET", params)
    data = _presta_get("addresses", params)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 4 — Get Customer Addresses
# ══════════════════════════════════════════════════════════════════════

@tool
def get_customer_addresses(customer_id: str) -> str:
    """
    Get all delivery addresses for a PrestaShop customer ID.
    Returns JSON list with id_address, alias, city, address1.
    """
    params = {"filter[id_customer]": customer_id, "display": "full"}
    _print_tool_payload("get_customer_addresses", "GET", params)
    data = _presta_get("addresses", params)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 5 — Create Cart in PrestaShop
# ══════════════════════════════════════════════════════════════════════

@tool
def create_presta_cart(
    customer_id: str,
    address_id: str,
    cart_rows: list,
    id_currency: str = "1",
    id_lang: str = "1",
) -> str:
    """
    Create a new cart in PrestaShop with the given products.
    cart_rows: list of {id_product, id_product_attribute, quantity}.
    Returns JSON with id_cart on success.

    PrestaShop REST /api/carts requires XML body.
    """
    rows_xml = "\n".join(
        f"""<cart_row>
              <id_product>{r['id_product']}</id_product>
              <id_product_attribute>{r.get('id_product_attribute', 0)}</id_product_attribute>
              <id_address_delivery>{address_id}</id_address_delivery>
              <quantity>{r['quantity']}</quantity>
            </cart_row>"""
        for r in cart_rows
    )

    xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<prestashop xmlns:xlink="http://www.w3.org/1999/xlink">
  <cart>
    <id_currency>{id_currency}</id_currency>
    <id_lang>{id_lang}</id_lang>
    <id_customer>{customer_id}</id_customer>
    <id_address_delivery>{address_id}</id_address_delivery>
    <id_address_invoice>{address_id}</id_address_invoice>
    <cart_rows>{rows_xml}</cart_rows>
  </cart>
</prestashop>"""

    _print_tool_payload("create_presta_cart", "XML", xml_body)
    data = _presta_post("carts", xml_body)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 6 — Place Order  (convert cart → order)
# ══════════════════════════════════════════════════════════════════════

@tool
def place_order(
    cart_id: str,
    customer_id: str,
    address_id: str,
    payment_module: str = "ps_checkpayment",
    payment_name: str   = "Cash on Delivery",
) -> str:
    """
    Convert a validated PrestaShop cart into a real order.
    Returns JSON with id_order and order reference on success.

    Uses PrestaShop REST /api/orders with XML body.
    Note: the cart must already exist (call create_presta_cart first).
    """
    xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<prestashop xmlns:xlink="http://www.w3.org/1999/xlink">
  <order>
    <id_address_delivery>{address_id}</id_address_delivery>
    <id_address_invoice>{address_id}</id_address_invoice>
    <id_cart>{cart_id}</id_cart>
    <id_currency>1</id_currency>
    <id_lang>1</id_lang>
    <id_customer>{customer_id}</id_customer>
    <id_carrier>1</id_carrier>
    <module>{payment_module}</module>
    <payment>{payment_name}</payment>
    <recyclable>0</recyclable>
    <gift>0</gift>
    <current_state>1</current_state>
  </order>
</prestashop>"""

    _print_tool_payload("place_order", "XML", xml_body)
    data = _presta_post("orders", xml_body)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 7 — Place Order via Custom Module  (your existing validate→order flow)
# ══════════════════════════════════════════════════════════════════════

@tool
def place_order_via_module(sender_number: str, cart_session_id: str) -> str:
    """
    Place a confirmed order using the custom Delidel chatbot module.
    Uses the session cart that was previously validated via validate_cart.
    Call this ONLY after the customer confirms with 'yes'.
    Returns JSON with order_id and status.
    """
    payload = {
        "action":           "place_order",
        "sender_number":    clean_number(sender_number),
        "cart_session_id":  cart_session_id,
    }
    _print_tool_payload("place_order_via_module", "POST", payload)
    data = _chatbot_post(payload)
    print("[PLACE ORDER RAW RESPONSE]", data)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 8 — Get Order Status (REST fallback)
# ══════════════════════════════════════════════════════════════════════

@tool
def get_order_status(order_id: str) -> str:
    """
    Fetch the current status of an existing order by order ID.
    Returns JSON with order reference, current_state, total_paid.
    """
    params = {"display": "full"}
    _print_tool_payload("get_order_status", "GET", params)
    data = _presta_get(f"orders/{order_id}", params)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 9 — Get Undelivered Orders
# ══════════════════════════════════════════════════════════════════════

@tool
def get_undelivered_orders(sender_number: str) -> str:
    """
    Fetch the undelivered orders for a customer.
    """
    payload = {
        "action": "getundeliveredorders",
        "phone_number": clean_number(sender_number),
    }
    _print_tool_payload("get_undelivered_orders", "POST", payload)
    data = _chatbot_post(payload)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 10 — Get Order Status via Module
# ══════════════════════════════════════════════════════════════════════

@tool
def get_order_status_via_module(order_id: str) -> str:
    """
    Fetch the current status of an existing order by order ID using the module.
    """
    payload = {
        "action": "getorderstatus",
        "order_id": order_id,
    }
    _print_tool_payload("get_order_status_via_module", "POST", payload)
    data = _chatbot_post(payload)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# TOOL 11 — Create Ticket
# ══════════════════════════════════════════════════════════════════════

@tool
def create_ticket(sender_number: str, customer_name: str, description: str, priority: str) -> str:
    """
    Create a support ticket for a customer complaint.
    """
    payload = {
        "action": "createticket",
        "phone_number": clean_number(sender_number),
        "name": customer_name,
        "description": description,
        "priority": priority,
    }
    _print_tool_payload("create_ticket", "POST", payload)
    data = _chatbot_post(payload)
    return json.dumps(data)


# ══════════════════════════════════════════════════════════════════════
# EXPORT ALL TOOLS (for reference — chain calls them directly)
# ══════════════════════════════════════════════════════════════════════

ALL_TOOLS = [
    search_products,
    validate_cart,
    get_customer_by_phone,
    get_customer_addresses,
    create_presta_cart,
    place_order,
    place_order_via_module,
    get_order_status,
    get_undelivered_orders,
    get_order_status_via_module,
    create_ticket,
]
