import asyncio
import json
import sys

import httpx

BASE_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 60.0

REQUIRED_FIELDS = [
    "decision",
    "score",
    "confidence",
    "reason",
    "rule_references",
    "recommended_action",
    "trace_id",
    "processing_ms",
]

SCENARIOS = [
    {
        "name": "SCENARIO 1 — CLEAN",
        "expected": "PASS",
        "payload": {
            "transaction_id": "demo_001",
            "amount": 2500.0,
            "currency": "USD",
            "sender_country": "SG",
            "receiver_country": "UK",
            "jurisdiction": "MAS",
            "transfer_count_24h": 1,
            "avg_transfer_amount": 2500.0,
        },
    },
    {
        "name": "SCENARIO 2 — STRUCTURING",
        "expected": "FLAG",
        "payload": {
            "transaction_id": "demo_002",
            "amount": 9800.0,
            "currency": "USD",
            "sender_country": "AE",
            "receiver_country": "SG",
            "jurisdiction": "FATF",
            "transfer_count_24h": 7,
            "avg_transfer_amount": 9750.0,
        },
    },
    {
        "name": "SCENARIO 3 — SANCTIONS",
        "expected": "BLOCK",
        "payload": {
            "transaction_id": "demo_003",
            "amount": 50000.0,
            "currency": "USDT",
            "sender_country": "IR",
            "receiver_country": "UK",
            "jurisdiction": "FCA",
            "transfer_count_24h": 1,
            "avg_transfer_amount": 50000.0,
        },
    },
]


def _assertion_failures(body: dict, expected_decision: str, transaction_id: str) -> list[str]:
    failures: list[str] = []

    missing = [f for f in REQUIRED_FIELDS if f not in body]
    if missing:
        failures.append(f"missing contract fields: {missing}")
        return failures

    if body.get("trace_id") != transaction_id:
        failures.append(
            f"trace_id mismatch: got {body.get('trace_id')!r}, expected {transaction_id!r}"
        )

    if body.get("decision") != expected_decision:
        failures.append(
            f"decision mismatch: expected {expected_decision} got {body.get('decision')}"
        )

    score = body.get("score")
    if not isinstance(score, int) or score < 0 or score > 100:
        failures.append(f"score not an integer in 0-100: {score!r}")

    rules = body.get("rule_references")
    if not isinstance(rules, list) or len(rules) == 0:
        failures.append(f"rule_references is empty or not a list: {rules!r}")

    return failures


async def _run_scenario(client: httpx.AsyncClient, scenario: dict) -> bool:
    name = scenario["name"]
    expected = scenario["expected"]
    payload = scenario["payload"]

    print("=" * 60)
    print(f"{name} (expected: {expected})")
    print("=" * 60)

    try:
        resp = await client.post(
            f"{BASE_URL}/check", json=payload, timeout=REQUEST_TIMEOUT
        )
    except httpx.HTTPError as exc:
        print(f"Request failed: {exc!r}")
        print("Result: ✗ FAIL — request error")
        return False

    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}")
        print(resp.text)
        print(f"Result: ✗ FAIL — HTTP {resp.status_code}")
        return False

    try:
        body = resp.json()
    except ValueError:
        print(resp.text)
        print("Result: ✗ FAIL — response was not valid JSON")
        return False

    print(json.dumps(body, indent=2))

    failures = _assertion_failures(body, expected, payload["transaction_id"])
    if not failures:
        print("\nResult: ✓ PASS")
        return True

    decision_mismatch = next(
        (f for f in failures if f.startswith("decision mismatch")), None
    )
    if decision_mismatch:
        print(
            f"\nResult: ✗ FAIL — expected {expected} got {body.get('decision')}"
        )
    else:
        print(f"\nResult: ✗ FAIL — {'; '.join(failures)}")
    return False


async def run_scenarios() -> int:
    passed = 0
    async with httpx.AsyncClient() as client:
        for i, scenario in enumerate(SCENARIOS):
            if i > 0:
                print("\n" + "-" * 60 + "\n")
            ok = await _run_scenario(client, scenario)
            if ok:
                passed += 1

    print("\n" + "-" * 60)
    print(f"Results: {passed}/{len(SCENARIOS)} passed")
    return 0 if passed == len(SCENARIOS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_scenarios()))
