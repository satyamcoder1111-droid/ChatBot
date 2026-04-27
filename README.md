# Delidel WhatsApp Bot — Production LangChain Edition

## Architecture

```
delidel_bot/
├── app.py                      # Flask entrypoint
├── requirements.txt
├── config/
│   ├── settings.py             # All env vars / constants
│   └── session.py              # Redis session management
├── tools/
│   └── presta_tools.py         # @tool decorated PrestaShop API calls
├── chains/
│   ├── prompts.py              # All ChatPromptTemplates
│   └── orchestrator.py         # Chain dispatcher (no agents)
└── templates/
    └── index.html              # WhatsApp-style test UI
```

## Flow

```
User Message
    │
    ▼
[Greeting/Multi-order shortcut] ──────────────────────┐
    │ (if not shortcut)                                │
    ▼                                                  │
[Intent Chain] → ChatGroq → JSON intent               │
    │                                                  │
    ▼                                                  │
[Dispatcher]                                           │
    ├── greeting          → handle_greeting            │
    ├── price_check       → search_products @tool      │
    ├── stock_check       → search_products @tool      │
    ├── price_stock       → search_products @tool      │
    ├── direct_order      → ORDER PARSER CHAIN         │
    │                       → validate_cart @tool      │
    │                       → Cart Summary LLM         │
    ├── multi_order       → ORDER PARSER CHAIN         │
    │                       → validate_cart @tool      │
    │                       → Cart Summary LLM         │
    ├── confirm_order     → place_order_via_module @tool│
    │                       → Order Confirm LLM        │
    ├── cancel_order      → clear cart                 │
    ├── order_status      → get_order_status @tool     │
    └── general           → General Reply LLM ─────────┘
                                    │
                                    ▼
                             Save to Redis
                                    │
                                    ▼
                             Reply to Customer
```

## PrestaShop APIs Required

| Tool | Endpoint | Method | Purpose |
|------|----------|--------|---------|
| `search_products` | `/module/ogachatbotapi/ogachatbotapi?action=getproductdetails` | GET | Price + stock lookup |
| `validate_cart` | `/module/ogachatbotapi/ogachatbotapi` action=validate_cart | POST | Validate cart + get total |
| `place_order_via_module` | `/module/ogachatbotapi/ogachatbotapi` action=place_order | POST | Place order from session cart |
| `get_customer_by_phone` | `/api/addresses?filter[phone]=...` | GET | Link phone → customer |
| `get_customer_addresses` | `/api/addresses?filter[id_customer]=...` | GET | Get delivery address |
| `create_presta_cart` | `/api/carts` | POST (XML) | Create cart directly in PS |
| `place_order` | `/api/orders` | POST (XML) | Convert cart → order in PS |
| `get_order_status` | `/api/orders/{id}` | GET | Check order status |

> **Primary flow**: `validate_cart` → user confirms → `place_order_via_module`  
> **Fallback flow**: `create_presta_cart` → `place_order` (native PS REST)

## Environment Variables

```bash
GROQ_API_KEY=gsk_...
PRESTA_BASE_URL=https://stguae.delidel.in
PRESTA_API_KEY=JNtNqBDMW8...
OGA_CRM_BASE_URL=https://crm.ogaapps.in
OGA_CRM_BEARER_TOKEN=sk_live_...
OGA_CRM_INSTANCE_NAME="Delidel Support"
REDIS_URL=https://true-giraffe-...upstash.io
REDIS_TOKEN=gQAAAA...
VERIFY_TOKEN=EAALSHl...
PHONE_NUMBER_ID=877429722112368
ALLOWED_NUMBERS=9354906215,9759145356,7988149282
```

## Install & Run

```bash
pip install -r requirements.txt
python app.py
# or production:
gunicorn app:app --bind 0.0.0.0:10000 --workers 2
```

## What You Need to Add to Your Module

Your PrestaShop module's `ogachatbotapi.php` needs to handle:

```php
// action=place_order
case 'place_order':
    $sender    = Tools::getValue('sender_number');
    $sessionId = Tools::getValue('cart_session_id');
    // 1. Load the validated cart from your session/cache by $sessionId
    // 2. Create order from cart (use OrderCore or your existing logic)
    // 3. Return: {"status": true, "order_id": 123, "reference": "DELI-001"}
    break;
```
