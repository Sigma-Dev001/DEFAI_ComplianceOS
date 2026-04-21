---
description: Run all three demo scenarios and print full responses
allowed-tools: Bash(*), Read
---
Ensure FastAPI server is running on port 8000.
POST the three scenarios from tests/scenarios.py to /check.
Print each full JSON response labelled:
  SCENARIO 1 — CLEAN (expected: PASS)
  SCENARIO 2 — STRUCTURING (expected: FLAG)
  SCENARIO 3 — SANCTIONS (expected: BLOCK)
Report pass/fail for each.
