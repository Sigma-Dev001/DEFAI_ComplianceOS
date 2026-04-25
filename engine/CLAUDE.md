# Engine module rules

## claude.py
- Accepts: transaction dict + dict of regulatory chunks grouped by jurisdiction
- Calls: claude-opus-4-7 via Anthropic Python SDK (AsyncAnthropic), timeout 45s
- Returns: raw JSON string from Claude (parsing happens in decision.py)
- On API timeout or error: returns a FALLBACK_RESPONSE JSON string (all regulators score=50, confidence=0.30, summary="API unavailable")
- SYSTEM_PROMPT is content-hashed (SHA256, first 16 chars) and stored per audit row so a change to the prompt is detectable from the audit log

## Prompt contract
System prompt requires Claude to return JSON matching:

    {
      "decisions": {
        "vara": {"score": 0-100, "citations": [...]},
        "mas":  {"score": 0-100, "citations": [...]},
        "fca":  {"score": 0-100, "citations": [...]}
      },
      "confidence": 0.00-1.00,
      "summary_reason": "one to two sentence factual summary",
      "recommended_action": "string"
    }

Each citation must have all six fields: jurisdiction, instrument, rule_id, effective_date, quote_excerpt (verbatim, ≤60 words), mapping (transaction field → rule element).

FATF is supporting context only — cited inside VARA/MAS/FCA decisions, never as a top-level decision key.

## decision.py
- Accepts: raw Claude JSON string
- Extracts the JSON (tolerant of code fences and wrapping text)
- Drops citations missing any of the 6 required fields
- Per-regulator score → decision (0-39 PASS, 40-65 FLAG, 66-100 BLOCK)
- Override: downgrades BLOCK→FLAG when score<85 AND no sanctioned jurisdiction is involved (protects against Claude over-flagging)
- Aggregate decision is worst-case across regulators
- On parse failure: returns FLAG, confidence=0.30, reason="Parse error"

## retrieval.py
- Accepts: transaction dict
- Builds a query string from transaction fields
- Embeds with sentence-transformers all-MiniLM-L6-v2 (normalized)
- Returns: top-3 chunks per jurisdiction by cosine distance (pgvector)
