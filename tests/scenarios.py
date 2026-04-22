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
    "confidence_label",
    "reason",
    "decisions",
    "rule_references",
    "recommended_action",
    "trace_id",
    "processing_ms",
]

ACTIVE_REGULATORS = ("vara", "mas", "fca")

SCENARIOS = [
    {
        "name": "SCENARIO 1 — CLEAN",
        "display_name": "Clean (SG→UK)",
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
        "display_name": "Structuring (AE→SG)",
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
        "display_name": "Sanctions (IR→UK)",
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

_SUMMARY_COLS = (21, 10, 7, 12)


def _summary_cell(value: str, width: int) -> str:
    return " " + value + " " * (width - 1 - len(value))


def _summary_hline(left: str, mid: str, right: str) -> str:
    return left + mid.join("─" * w for w in _SUMMARY_COLS) + right


def _summary_row(c1: str, c2: str, c3: str, c4: str) -> str:
    cells = [
        _summary_cell(c1, _SUMMARY_COLS[0]),
        _summary_cell(c2, _SUMMARY_COLS[1]),
        _summary_cell(c3, _SUMMARY_COLS[2]),
        _summary_cell(c4, _SUMMARY_COLS[3]),
    ]
    return "│" + "│".join(cells) + "│"


def _print_header() -> None:
    print("=" * 60)
    print("DEFAI ComplianceOS — Live Demo")
    print("Powered by Claude Opus 4.7 + FATF/MiCA/FCA/MAS")
    print("=" * 60)


def _print_summary(results: list[tuple[str, str, str, bool]]) -> None:
    print(_summary_hline("┌", "┬", "┐"))
    print(_summary_row("Scenario", "Expected", "Got", "Status"))
    print(_summary_hline("├", "┼", "┤"))
    for display_name, expected, got, ok in results:
        status = "✓" if ok else "✗"
        print(_summary_row(display_name, expected, got, status))
    print(_summary_hline("└", "┴", "┘"))
    passed = sum(1 for _, _, _, ok in results if ok)
    print(f"Results: {passed}/{len(results)} passed")


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

    confidence = body.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        failures.append(
            f"confidence must be a numeric float, got {type(confidence).__name__}: {confidence!r}"
        )
    elif confidence < 0.0 or confidence > 1.0:
        failures.append(f"confidence must be in 0.0-1.0, got {confidence!r}")

    label = body.get("confidence_label")
    if label not in ("low", "medium", "high"):
        failures.append(f"confidence_label must be low/medium/high, got {label!r}")

    decisions = body.get("decisions")
    if not isinstance(decisions, dict):
        failures.append(f"decisions must be a dict, got {type(decisions).__name__}")
    else:
        for reg in ACTIVE_REGULATORS:
            if reg not in decisions:
                failures.append(f"decisions missing {reg!r} key")

    rules = body.get("rule_references")
    if not isinstance(rules, list):
        failures.append(f"rule_references must be a list, got {type(rules).__name__}")

    return failures


async def _run_scenario(
    client: httpx.AsyncClient, scenario: dict
) -> tuple[bool, str]:
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
        return False, "ERR"

    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}")
        print(resp.text)
        print(f"Result: ✗ FAIL — HTTP {resp.status_code}")
        return False, "ERR"

    try:
        body = resp.json()
    except ValueError:
        print(resp.text)
        print("Result: ✗ FAIL — response was not valid JSON")
        return False, "ERR"

    print(json.dumps(body, indent=2))

    got = str(body.get("decision") or "ERR")
    failures = _assertion_failures(body, expected, payload["transaction_id"])
    if not failures:
        print("\nResult: ✓ PASS")
        return True, got

    decision_mismatch = next(
        (f for f in failures if f.startswith("decision mismatch")), None
    )
    if decision_mismatch:
        print(
            f"\nResult: ✗ FAIL — expected {expected} got {body.get('decision')}"
        )
    else:
        print(f"\nResult: ✗ FAIL — {'; '.join(failures)}")
    return False, got


async def run_scenarios() -> int:
    _print_header()
    results: list[tuple[str, str, str, bool]] = []
    async with httpx.AsyncClient() as client:
        for i, scenario in enumerate(SCENARIOS):
            if i > 0:
                print("\n" + "-" * 60 + "\n")
            ok, got = await _run_scenario(client, scenario)
            results.append(
                (scenario["display_name"], scenario["expected"], got, ok)
            )

    print("\n" + "-" * 60)
    _print_summary(results)
    return 0 if all(ok for _, _, _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_scenarios()))
