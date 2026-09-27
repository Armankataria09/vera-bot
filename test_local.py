import json
import os
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = os.getenv("VERA_BASE_URL", "http://127.0.0.1:8000")

def call(method, path, payload=None):
    url = BASE + path
    try:
        r = httpx.request(method, url, json=payload, timeout=20.0)
    except Exception as e:
        print(f"\n[FAIL] {method} {path}\n{type(e).__name__}: {e}")
        return None
    print(f"\n[{r.status_code}] {method} {path}")
    try:
        data = r.json()
        print(json.dumps(data, indent=2))
        return r, data
    except Exception:
        print(r.text)
        return r, None

print("=" * 70)
print("MAGICPIN VERA LOCAL END-TO-END TEST")
print("=" * 70)
print("Base:", BASE)
print("Gemini model:", os.getenv("GEMINI_MODEL", "NOT SET"))
print("Gemini key:", "LOADED" if os.getenv("GEMINI_API_KEY") else "MISSING")

# 1. Health
res = call("GET", "/v1/healthz")
if not res or res[0].status_code != 200:
    print("\nSTOP: health endpoint failed.")
    sys.exit(1)

# 2. Metadata
res = call("GET", "/v1/metadata")
if not res or res[0].status_code != 200:
    print("\nSTOP: metadata endpoint failed.")
    sys.exit(1)

# 3. Clean state
call("POST", "/v1/teardown")

now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

# 4. Category
category = {
    "scope": "category",
    "context_id": "cafe",
    "version": 1,
    "payload": {
        "slug": "cafe",
        "offer_catalog": [
            {"name": "20% off coffee", "details": "20% off selected coffees"}
        ],
        "voice": {"tone": "friendly", "language": "English"},
        "peer_stats": {"avg_rating": 4.3},
        "digest": {},
        "patient_content_library": [],
        "seasonal_beats": [],
        "trend_signals": []
    },
    "delivered_at": now
}
res = call("POST", "/v1/context", category)
if not res or res[0].status_code != 200:
    print("\nSTOP: category context failed.")
    sys.exit(1)

# 5. Merchant
merchant = {
    "scope": "merchant",
    "context_id": "merchant_test_001",
    "version": 1,
    "payload": {
        "merchant_id": "merchant_test_001",
        "category_slug": "cafe",
        "identity": {"name": "Bean Street Cafe"},
        "subscription": {"plan": "pro"},
        "performance": {"rating": 4.5, "orders": 120, "views": 820},
        "offers": [{"name": "20% off coffee"}],
        "conversation_history": [],
        "customer_aggregate": {},
        "signals": {}
    },
    "delivered_at": now
}
res = call("POST", "/v1/context", merchant)
if not res or res[0].status_code != 200:
    print("\nSTOP: merchant context failed.")
    sys.exit(1)

# 6. Trigger
trigger = {
    "scope": "trigger",
    "context_id": "trigger_test_001",
    "version": 1,
    "payload": {
        "id": "trigger_test_001",
        "scope": "merchant",
        "kind": "performance",
        "source": "system",
        "merchant_id": "merchant_test_001",
        "payload": {
            "metric": "views",
            "value": 820,
            "window_days": 30,
            "headline": "Your cafe received 820 views in the last 30 days"
        },
        "urgency": "normal",
        "suppression_key": "local_test_performance_001",
        "expires_at": "2027-12-31T23:59:59Z"
    },
    "delivered_at": now
}
res = call("POST", "/v1/context", trigger)
if not res or res[0].status_code != 200:
    print("\nSTOP: trigger context failed.")
    sys.exit(1)

# 7. Tick -> GPT-5.6 -> validation
tick = {
    "now": now,
    "available_triggers": ["trigger_test_001"]
}
res = call("POST", "/v1/tick", tick)
if not res or res[0].status_code != 200:
    print("\nSTOP: tick failed.")
    sys.exit(1)

actions = res[1].get("actions", []) if isinstance(res[1], dict) else []
if not actions:
    print("\nWARNING: tick returned zero actions.")
    print("This can happen if Claude failed and the fallback output failed validation.")
else:
    action = actions[0]
    print("\nSUCCESS: Vera produced an action.")
    print("Body:", action.get("body"))
    print("Send as:", action.get("send_as"))
    print("CTA:", action.get("cta"))

    # 8. Reply
    conversation_id = action.get("conversation_id")
    if conversation_id:
        reply = {
            "conversation_id": conversation_id,
            "merchant_id": "merchant_test_001",
            "from_role": "merchant",
            "message": "Let's do it",
            "received_at": now,
            "turn_number": 1
        }
        call("POST", "/v1/reply", reply)

# 9. Health after full flow
call("GET", "/v1/healthz")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
