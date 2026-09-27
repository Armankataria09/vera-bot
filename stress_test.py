import concurrent.futures
import json
import time

import httpx

BASE = "http://127.0.0.1:8000"


def request(method, path, payload=None):
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.request(method, BASE + path, json=payload)
            return r.status_code, r.text[:500]
    except Exception as e:
        return None, repr(e)


def main():
    tests = []

    # 20 health checks
    for _ in range(20):
        tests.append(("GET", "/v1/healthz", None))

    # 10 metadata checks
    for _ in range(10):
        tests.append(("GET", "/v1/metadata", None))

    # 10 repeated ticks. Because the test trigger is already suppressed,
    # these should return quickly without creating duplicate outreach.
    tick = {
        "now": "2026-09-27T17:30:00Z",
        "available_triggers": ["trg_research_digest_dentists"],
    }
    for _ in range(10):
        tests.append(("POST", "/v1/tick", tick))

    # 10 deterministic reply checks.
    reply = {
        "conversation_id": "stress_reply_001",
        "merchant_id": "merchant_test_001",
        "customer_id": None,
        "from_role": "user",
        "message": "No, not interested right now",
        "received_at": "2026-09-27T17:35:00Z",
        "turn_number": 1,
    }
    for _ in range(10):
        tests.append(("POST", "/v1/reply", reply))

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda t: request(*t), tests))
    elapsed = time.perf_counter() - started

    failures = []
    for i, ((method, path, _), (status, body)) in enumerate(zip(tests, results), 1):
        if status != 200:
            failures.append({"test": i, "method": method, "path": path, "status": status, "body": body})

    print(f"Stress tests: {len(tests)}")
    print(f"Successful HTTP 200 responses: {len(tests) - len(failures)}")
    print(f"Failures: {len(failures)}")
    print(f"Elapsed: {elapsed:.2f}s")

    if failures:
        print("FAIL")
        print(json.dumps(failures, indent=2))
        raise SystemExit(1)

    print("PASS")


if __name__ == "__main__":
    main()
