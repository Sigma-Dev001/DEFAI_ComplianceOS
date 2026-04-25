import argparse
import asyncio
import json
import sys
import textwrap

import httpx

BASE_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 120.0

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
            "amount": 500.0,
            "currency": "USD",
            "sender_country": "SG",
            "receiver_country": "UK",
            "jurisdiction": "MAS",
            "transfer_count_24h": 1,
            "avg_transfer_amount": 500.0,
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
    {
        "name": "SCENARIO 4 — OFAC HIT",
        "display_name": "OFAC SDN (US→US)",
        "expected": "BLOCK",
        "assert_score": 100,
        "payload": {
            "transaction_id": "demo_004",
            "amount": 1000.0,
            "currency": "USDT",
            "sender_country": "US",
            "receiver_country": "US",
            "jurisdiction": "FCA",
            "transfer_count_24h": 1,
            "avg_transfer_amount": 1000.0,
            "from_address": "149w62rY42aZBox8fGcmqNsXUzSStKeq8C",
        },
    },
]

_USE_COLOR = sys.stdout.isatty()
_RESET = "\033[0m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_DIM = "\033[2m" if _USE_COLOR else ""
_GREEN = "\033[32m" if _USE_COLOR else ""
_YELLOW = "\033[33m" if _USE_COLOR else ""
_RED = "\033[31m" if _USE_COLOR else ""
_CYAN = "\033[36m" if _USE_COLOR else ""

_DECISION_COLOR = {
    "PASS": _GREEN,
    "FLAG": _YELLOW,
    "BLOCK": _RED,
}


def _color_decision(decision: str) -> str:
    color = _DECISION_COLOR.get(decision, "")
    return f"{color}{_BOLD}{decision}{_RESET}"


def _truncate_one_line(text: str, width: int = 96) -> str:
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= width:
        return collapsed
    return collapsed[: width - 1].rstrip() + "…"


def _print_header() -> None:
    bar = "═" * 64
    print(f"{_CYAN}{bar}{_RESET}")
    print(f"{_BOLD}  DEFAI ComplianceOS — Live Demo{_RESET}")
    print("  Powered by Claude Opus 4.7 + FATF/VARA/MAS/FCA")
    print(f"{_CYAN}{bar}{_RESET}")


def _print_scenario_header(scenario: dict) -> None:
    bar = "─" * 64
    print()
    print(f"{_CYAN}{bar}{_RESET}")
    print(f"  {_BOLD}{scenario['name']}{_RESET}")
    print(f"  {scenario['display_name']}")
    print(f"  Expected: {_color_decision(scenario['expected'])}")
    print(f"{_CYAN}{bar}{_RESET}")


def _print_clean_response(body: dict) -> None:
    decision = str(body.get("decision") or "—")
    score = body.get("score")
    confidence = body.get("confidence")
    confidence_label = body.get("confidence_label")
    reason = body.get("reason") or ""
    processing_ms = body.get("processing_ms")
    per_reg = body.get("decisions") or {}
    rule_refs = body.get("rule_references") or []

    print()
    print(f"  Decision    : {_color_decision(decision)}")
    if isinstance(score, int):
        print(f"  Score       : {score}/100")
    else:
        print(f"  Score       : {score}")
    if isinstance(confidence, (int, float)):
        print(f"  Confidence  : {confidence:.2f} ({confidence_label})")
    else:
        print(f"  Confidence  : {confidence} ({confidence_label})")
    reason_text = " ".join((reason or "").split())
    print(textwrap.fill(
        reason_text,
        width=78,
        initial_indent="  Reason      : ",
        subsequent_indent=" " * 16,
    ))
    if isinstance(processing_ms, int):
        print(f"  Processing  : {processing_ms:,} ms")
    else:
        print(f"  Processing  : {processing_ms}")

    if isinstance(per_reg, dict) and per_reg:
        print()
        print(f"  {_BOLD}Per-regulator:{_RESET}")
        for reg in ACTIVE_REGULATORS:
            entry = per_reg.get(reg) or {}
            reg_decision = str(entry.get("decision") or "—")
            reg_score = entry.get("score")
            score_str = f"score {reg_score}" if reg_score is not None else "no score"
            print(
                f"    {reg.upper():<4}  {_color_decision(reg_decision)}  ({score_str})"
            )

    if rule_refs:
        print()
        print(f"  {_BOLD}Rule references ({len(rule_refs)}):{_RESET}")
        for cite in rule_refs:
            if isinstance(cite, dict):
                jur = (cite.get("jurisdiction") or "").strip()
                rid = (cite.get("rule_id") or "").strip()
                line = f"{jur:<4}  {rid}" if jur else rid or "(citation)"
            else:
                line = str(cite)
            print(f"    • {line}")


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


def _print_summary(results: list[tuple[str, str, str, bool]]) -> None:
    print()
    print(_summary_hline("┌", "┬", "┐"))
    print(_summary_row("Scenario", "Expected", "Got", "Status"))
    print(_summary_hline("├", "┼", "┤"))
    for display_name, expected, got, ok in results:
        status = "✓" if ok else "✗"
        print(_summary_row(display_name, expected, got, status))
    print(_summary_hline("└", "┴", "┘"))
    passed = sum(1 for _, _, _, ok in results if ok)
    total = len(results)
    color = _GREEN if passed == total else _RED
    print(f"{color}{_BOLD}Results: {passed}/{total} passed{_RESET}")


def _assertion_failures(
    body: dict,
    expected_decision: str,
    transaction_id: str,
    assert_score: int | None = None,
) -> list[str]:
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
    elif assert_score is not None and score != assert_score:
        failures.append(f"score mismatch: expected {assert_score} got {score}")

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
    client: httpx.AsyncClient, scenario: dict, verbose: bool
) -> tuple[bool, str]:
    expected = scenario["expected"]
    payload = scenario["payload"]

    _print_scenario_header(scenario)

    try:
        resp = await client.post(
            f"{BASE_URL}/check", json=payload, timeout=REQUEST_TIMEOUT
        )
    except httpx.HTTPError as exc:
        print(f"  {_RED}Request failed:{_RESET} {exc!r}")
        print(f"  {_RED}{_BOLD}Result: ✗ FAIL{_RESET} — request error")
        return False, "ERR"

    if resp.status_code != 200:
        print(f"  {_RED}HTTP {resp.status_code}{_RESET}")
        print(f"  {resp.text}")
        print(f"  {_RED}{_BOLD}Result: ✗ FAIL{_RESET} — HTTP {resp.status_code}")
        return False, "ERR"

    try:
        body = resp.json()
    except ValueError:
        print(f"  {resp.text}")
        print(f"  {_RED}{_BOLD}Result: ✗ FAIL{_RESET} — response was not valid JSON")
        return False, "ERR"

    _print_clean_response(body)
    if verbose:
        print()
        print(f"  {_DIM}--- raw JSON ---{_RESET}")
        for line in json.dumps(body, indent=2).splitlines():
            print(f"  {line}")

    got = str(body.get("decision") or "ERR")
    failures = _assertion_failures(
        body,
        expected,
        payload["transaction_id"],
        assert_score=scenario.get("assert_score"),
    )

    if not failures:
        print()
        print(f"  {_GREEN}{_BOLD}Result: ✓ PASS{_RESET}")
        return True, got

    decision_mismatch = next(
        (f for f in failures if f.startswith("decision mismatch")), None
    )
    print()
    if decision_mismatch:
        print(
            f"  {_RED}{_BOLD}Result: ✗ FAIL{_RESET} — expected "
            f"{_color_decision(expected)} got {_color_decision(str(body.get('decision')))}"
        )
    else:
        print(f"  {_RED}{_BOLD}Result: ✗ FAIL{_RESET} — {'; '.join(failures)}")
    return False, got


async def run_scenarios(verbose: bool = False) -> int:
    _print_header()
    results: list[tuple[str, str, str, bool]] = []
    async with httpx.AsyncClient() as client:
        for scenario in SCENARIOS:
            ok, got = await _run_scenario(client, scenario, verbose)
            results.append(
                (scenario["display_name"], scenario["expected"], got, ok)
            )

    _print_summary(results)
    await asyncio.sleep(2)
    return 0 if all(ok for _, _, _, ok in results) else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the DEFAI ComplianceOS demo scenarios against a running server."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Also print the full raw JSON response for each scenario.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(run_scenarios(verbose=args.verbose)))
