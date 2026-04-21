# Engine module rules

## claude.py
- Accepts: transaction dict + list of regulatory chunk strings
- Calls: claude-opus-4-7 via Anthropic Python SDK (async)
- Returns: raw string response from Claude
- On API timeout or error: return score=50, confidence="low", reason="API unavailable"
- Never parse the response here — that is decision.py's job

## Prompt structure
System: You are a compliance analyst. Reason about AML/CFT risk.
        Always respond with exactly:
        SCORE: [0-100]
        CONFIDENCE: [low/medium/high]
        REASON: [plain English explanation]
        RULES: [comma-separated citations e.g. FATF R.20, MiCA Art.38]

User:   Transaction: {transaction_json}
        Relevant regulations:
        {chunk_1}
        {chunk_2}
        Score this transaction's compliance risk.

## decision.py
- Accepts: raw Claude string output
- Parses: SCORE, CONFIDENCE, REASON, RULES using regex
- Maps score to PASS/FLAG/BLOCK per thresholds in root CLAUDE.md
- Returns: full response contract dict
- On parse failure: FLAG, confidence=low, reason="Parse error"

## retrieval.py
- Accepts: transaction dict
- Constructs query string from transaction fields
- Embeds with sentence-transformers
- Returns: top 5 regulatory chunks from pgvector by cosine similarity
