---
name: demo-scenarios
description: Run the four demo scenarios against a live server and verify each response matches the /check contract. Use when Samuel asks to run the demo, check scenarios, verify a deploy, or smoke-test before commit.
---

# Demo scenarios

Four canonical transactions covering the decision space: PASS, FLAG (structuring), BLOCK (sanctions), BLOCK (OFAC SDN bypass). Authoritative list lives in `tests/scenarios.py`.

## Scenarios

| # | Name | Route | Payload signal | Expected | Notes |
|---|---|---|---|---|---|
| 1 | CLEAN | SG→UK | $2,500 USD, 1 tx / 24h | PASS | via MAS |
| 2 | STRUCTURING | AE→SG | $9,800 × 7 / 24h | FLAG | sub-$10k velocity |
| 3 | SANCTIONS | IR→UK | $50,000 USDT | BLOCK | IR in SANCTIONED_COUNTRIES |
| 4 | OFAC HIT | US→US | $1,000 USDT, `from_address=149w62rY42aZBox8fGcmqNsXUzSStKeq8C` | BLOCK, score=100 | Claude is NOT called |

## How to run

```bash
# if server is not already up
python3 main.py &
until curl -s http://localhost:8000/health > /dev/null; do sleep 1; done

# run the suite
python3 tests/scenarios.py           # clean output
python3 tests/scenarios.py --verbose # + raw JSON

# or one-shot via demo.sh (kills stale server, starts new, waits for health, runs)
./demo.sh
```

Exit code is 0 iff all four pass. Scenario 4 has `assert_score=100` — any other score fails even if decision=BLOCK.

## Contract assertions (from `REQUIRED_FIELDS`)

Every response must contain: `decision, score, confidence, confidence_label, reason, decisions, rule_references, recommended_action, trace_id, processing_ms`.

Additional checks:
- `trace_id == payload.transaction_id`
- `decision == expected`
- `score` is int in 0-100
- `confidence` is float (not bool) in 0.0-1.0
- `confidence_label` in `{low, medium, high}`
- `decisions` is a dict with keys `vara, mas, fca`
- `rule_references` is a list

## Interpreting failures

- **Request error / HTTP != 200** — server is down, DB is down, or the audit log failed (503). Check server logs; do not retry blindly.
- **Decision mismatch on 1/2/3** — usually a regression in `engine/decision.py` aggregation or a change to the sanctions override. Inspect per-regulator scores in the response.
- **Decision mismatch on 4** — OFAC bypass path is broken; Claude was called instead. Check `screening/ofac.py` and the SDN cache.
- **Contract fields missing** — `api/routes.py` response shaping regressed. Compare against the check-pipeline skill's response contract.
- **`confidence` is a string** — someone reverted the float-confidence migration. See commit df3f54c.
- **Score on scenario 4 != 100** — OFAC path is returning a scored decision instead of the hardcoded `score=100, confidence=1.0`.

## When to pause

If scenario 3 (SANCTIONS) returns FLAG instead of BLOCK, the sanctions-aware override in `engine/decision.py` is mis-wired — it should only downgrade BLOCK→FLAG when neither country is in `SANCTIONED_COUNTRIES`. Stop and fix before shipping.
