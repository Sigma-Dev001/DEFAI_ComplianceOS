---
name: audit-trail-check
description: Verify the audit trail integrity for a given decision — every /check must produce a complete, regulator-defensible row in the transactions table. Use when Samuel asks to inspect a decision, debug a wrong verdict, or verify "did this get logged".
---

# Audit trail integrity

Every `/check` response — Claude-path or OFAC-bypass — must be backed by a row in `transactions`. A decision without an audit row is a compliance hole; the endpoint returns 503 instead of letting one through.

## How to pull a trace

```bash
# most recent decision for a transaction_id
curl -s http://localhost:8000/trace/demo_002 | python3 -m json.tool

# last 20 decisions, shortened
curl -s http://localhost:8000/audit | python3 -m json.tool

# direct DB (read-only check)
docker compose exec db psql -U epoch_user -d complianceos_db \
  -c "SELECT transaction_id, decision, score, confidence, reg_snapshot_id, override_applied, processing_ms, created_at FROM transactions ORDER BY created_at DESC LIMIT 10;"
```

## What every row must carry

Populated columns (see `db/models.py::Transaction`):

| Column | Purpose | Integrity check |
|---|---|---|
| `transaction_id` | fintech-supplied trace_id | matches `request_payload.transaction_id` |
| `request_payload` | full inbound JSON | JSONB — never truncated |
| `claude_raw_output` | verbatim Claude response | Text — unparsed; `"[OFAC SDN bypass — Claude not called]"` on bypass |
| `decision` / `score` / `confidence` | aggregated verdict | decision matches thresholds against score; confidence is float 0.0-1.0 |
| `reason` / `recommended_action` | human-facing explanation | non-empty |
| `rule_references` | flat deduped citations | JSONB list; each citation has 6 keys populated OR list is empty (OFAC bypass) |
| `decisions` | per-regulator breakdown | JSONB with `vara, mas, fca` keys (or the three all showing BLOCK on OFAC bypass) |
| `reg_snapshot_id` | content hash of retrieved chunks | 16-char hex; null on OFAC bypass (Claude wasn't called) |
| `system_prompt_hash` | 16-char hash of SYSTEM_PROMPT | matches `engine.claude.SYSTEM_PROMPT_HASH` — proves which prompt version scored this |
| `override_applied` / `override_reason` | sanctions-aware BLOCK→FLAG downgrade | true + reason if decision.py downgraded any regulator |
| `processing_ms` | wall-clock ms | integer; for Claude path should be 15,000-25,000 |
| `created_at` | server timestamp | auto-set by `server_default=func.now()` |

## Red flags in a trace

- `claude_raw_output` is empty → Claude path failed silently; should have returned FALLBACK_RESPONSE string
- `system_prompt_hash` is NULL → row was written before the prompt-versioning fix; post-9f18a45 rows must have it
- `reg_snapshot_id` is NULL on a Claude-path decision → retrieval returned nothing OR `document_hash` missing on chunks
- `override_applied=true` but `override_reason` is NULL → decision.py bug, they must co-occur
- `confidence` is a string (`"low"`/`"medium"`/`"high"`) → legacy row from before the float-confidence migration
- `rule_references` items missing any of the 6 keys → citation normalization regressed (`_normalize_citation` filters these, so a bad row means the filter was bypassed)
- `decision=PASS` but `score > 39`, or `decision=BLOCK` but `score < 66` → aggregation logic is broken OR sanctions override was skipped/mis-applied
- `processing_ms < 5000` on a Claude-path decision (not OFAC) → Claude never actually ran; check for FALLBACK_RESPONSE

## When an audit row is missing

`/check` returns 503 `{"error": "Audit log unavailable"}` only when the DB write failed. If a client got a 200 but no row exists:
- The audit write happened AFTER the response was built (ordering bug — should never happen in current routes.py, but check if someone refactored)
- Alert path wrote a row and then deleted it (alerts must never touch the transactions table)
- Multiple workers and the trace was written with a different transaction_id

## Cross-reference for prompt changes

If `system_prompt_hash` on historical rows no longer matches the current `SYSTEM_PROMPT_HASH`, the prompt was edited after those decisions were made. That's expected — it is evidence that old decisions were scored under an older prompt, which is exactly why the hash is logged. Do not "fix" this by rehashing.
