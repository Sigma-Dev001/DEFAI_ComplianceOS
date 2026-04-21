---
description: Run demo scenarios and verify responses match the contract
allowed-tools: Read, Bash(python*)
---
Run tests/scenarios.py against the live API on localhost:8000.
Verify each response contains all fields from the response contract in CLAUDE.md.
Report missing fields, wrong types, and wrong decisions.
Stop and fix before continuing if anything fails.
