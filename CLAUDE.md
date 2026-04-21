# DEFAI_ComplianceOS

## What this is
A compliance middleware REST API. Fintechs call POST /check before settling
a transaction. Claude reasons against embedded regulatory documents and returns
PASS, FLAG, or BLOCK with structured JSON and a full audit trail.

## Model
claude-opus-4-7 — always use this, never change it

## Stack
- Python 3.12
- FastAPI (fully async)
- PostgreSQL 16 + pgvector
- SQLAlchemy 2.0 async + asyncpg
- Anthropic API — claude-opus-4-7
- sentence-transformers (local embeddings, no external embedding API)
- python-telegram-bot v21
- Docker Compose

## Database
postgresql://epoch_user:devpassword@localhost:5432/complianceos_db

## Decision logic
- Score 0-39   → PASS
- Score 40-65  → FLAG, recommended_action: "human review"
- Score 66-100 → BLOCK

## Response contract (every /check response must match this exactly)
{
  "decision": "PASS|FLAG|BLOCK",
  "score": 0-100,
  "confidence": "low|medium|high",
  "reason": "plain English explanation",
  "rule_references": ["FATF R.20", "MiCA Art.38"],
  "recommended_action": "string",
  "trace_id": "matches input transaction_id",
  "processing_ms": integer
}

## Key constraints
- Never hardcode API keys — always os.getenv()
- Every decision must be logged with full Claude reasoning chain to DB
- All DB calls must be async — no sync SQLAlchemy
- Parameterized queries only — never f-string SQL
- pgvector handles vector search — no ChromaDB
- One file per concern — do not merge modules

## Build order
1. Docker + DB + pgvector
2. PDF ingestion + embedding
3. Claude reasoning engine
4. Decision parser
5. FastAPI routes
6. Audit log
7. Telegram alerts
8. Demo scenarios passing
