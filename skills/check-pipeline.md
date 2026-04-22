---
name: check-pipeline
description: Trace or review the full POST /check request flow end-to-end across OFAC screening, pgvector retrieval, Claude reasoning, decision parsing, audit log, and Telegram alert. Use when reviewing changes to api/routes.py, debugging a wrong decision, or explaining how a transaction becomes a verdict.
---

# /check pipeline

The complete request flow from fintech HTTP call to response. Every stage below is authoritative — if the code diverges from this, the code is wrong.

## Ordered stages

### 1. Request validation — `api/routes.py::CheckRequest`
- Pydantic with `extra="forbid"` — reject unknown fields
- Required: `transaction_id, amount, currency, sender_country, receiver_country, jurisdiction`
- Optional on-chain: `tx_hash, chain, from_address, to_address, contract_address, token_symbol`
- `avg_transfer_amount` defaults to `amount` via `@model_validator(mode="after")`

### 2. OFAC SDN pre-screen — `screening/ofac.py::screen_wallet`
- Screens `from_address` AND `to_address` against treasury.gov SDN XML (24h cache, asyncio.Lock-guarded)
- Only digital currency address IDs are loaded (tag `idType` starts with "Digital Currency Address")
- On hit: return `{decision: BLOCK, score: 100, confidence: 1.0, confidence_label: high}` — **bypass Claude entirely**
- The bypass path still must write the audit row and fire the Telegram alert

### 3. pgvector retrieval — `engine/retrieval.py::retrieve`
- Build query string from: amount, currency, sender_country, receiver_country, jurisdiction, transfer_count_24h, avg_transfer_amount
- Embed with `sentence-transformers all-MiniLM-L6-v2`, `normalize_embeddings=True`
- For each distinct `jurisdiction` in `regulatory_chunks`, fetch top-3 by `embedding.cosine_distance(query_vec)`
- Return `dict[str, list[dict]]` — each chunk carries `content, source_document, jurisdiction, document_hash, ingested_at`
- On failure: log and proceed with `{}` — Claude is still called

### 4. Claude reasoning — `engine/claude.py::call_claude`
- Model: `claude-opus-4-7` (never change; enforced by CLAUDE.md)
- `AsyncAnthropic`, `max_tokens=4096`, `timeout=45s`
- System prompt demands per-regulator (VARA/MAS/FCA) JSON with 6-key citations (jurisdiction, instrument, rule_id, effective_date, quote_excerpt, mapping)
- FATF is supporting context only — no top-level FATF decision
- On any exception or missing API key: return `FALLBACK_RESPONSE` (score=50 per reg, confidence=0.30)
- `SYSTEM_PROMPT_HASH` (first 16 chars of sha256) is persisted to every audit row

### 5. Decision parse + aggregation — `engine/decision.py::parse_claude_output`
- Extract JSON from fenced, unfenced, or wrapped output (three fallback regexes)
- Per regulator: clamp score to 0-100, map via thresholds (≤39 PASS, ≤65 FLAG, else BLOCK)
- **Sanctions-aware override**: if `raw_decision == BLOCK` and `score < 85` and neither country in `SANCTIONED_COUNTRIES` (`IR KP SY CU SD MM BY`), downgrade that regulator to FLAG and record `override_reason`
- Aggregate: any BLOCK → BLOCK; else any FLAG → FLAG; else PASS. `score = max(per-reg scores)`
- Citations: normalize (all 6 keys must be non-empty), dedupe by `(jurisdiction, rule_id)`, flatten into `rule_references`
- Confidence is a float 0.00-1.00; derive `confidence_label` via (<0.4 low, ≤0.7 medium, else high)
- `reg_snapshot_id` = 16-char sha256 of sorted `(jurisdiction, document_hash)` tuples from retrieved chunks
- On unparseable output: return FLAG, score=50, confidence=0.30, reason="Parse error — manual review required"

### 6. Audit write — `api/routes.py` (inline)
- `db.add(Transaction(...))` then `await db.commit()`
- Row captures: request_payload (JSONB), claude_raw_output (Text — verbatim, unparsed), decision, score, confidence, reason, rule_references (JSONB), recommended_action, decisions (per-reg JSONB), reg_snapshot_id, system_prompt_hash, override_applied, override_reason, processing_ms
- On DB failure: rollback + return HTTP 503 `{"error": "Audit log unavailable"}` — **never return a decision without an audit row**

### 7. Response shaping — `api/routes.py`
- Strip internal fields before returning: `reg_snapshot_id`, `override_applied`, `override_reason`
- Recompute `processing_ms` from `time.monotonic()` just before return (so it includes DB write)
- Response contract (root CLAUDE.md, mandatory):
  `decision, score, confidence (float), confidence_label, reason, decisions, rule_references, recommended_action, trace_id, processing_ms`

### 8. Fire-and-forget alert — `alerts/telegram.py::send_alert` via `_fire_and_forget_alert`
- Only FLAG or BLOCK trigger alerts
- `asyncio.create_task(_runner())` — **must not be awaited in the request path** (this was previously a bug; see commit 9f18a45)
- On missing TELEGRAM_BOT_TOKEN/CHAT_ID: log and skip silently
- Alert body shows: header emoji, trace_id, score + confidence label, decision line, reason, regulations (jurisdiction + rule_id)

## Hard constraints (enforce on every review)
- Model ID is exactly `claude-opus-4-7`
- No hardcoded secrets — `os.getenv()` only
- All DB calls async (SQLAlchemy 2.0 + asyncpg)
- Parameterized queries only (no f-string SQL)
- Every decision path writes to `transactions` before returning (including OFAC bypass)
- Alert path is fire-and-forget (never awaited in the hot path)

## Common failure modes
- Awaiting the Telegram alert → inflates processing_ms and blocks the response
- Writing the audit row after the alert → alert fires for decisions that never got logged
- Returning `confidence` as a string label instead of float → breaks the contract
- Skipping the OFAC audit write on bypass → silent compliance gap
- Regex-parsing Claude output without the JSON-extract fallbacks → FLAG(parse error) spikes on benign markdown fencing
