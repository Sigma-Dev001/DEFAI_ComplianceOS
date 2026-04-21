# DEFAI ComplianceOS

> Explainable AML/CFT compliance middleware — POST a transaction, get PASS/FLAG/BLOCK with regulatory citations in under 2 seconds.

## The problem

A compliance officer at a mid-market crypto exchange reviews 10,000 transactions per day with a 3-person team. Industry false positive rates average 95% — meaning 9,500 alerts per day are noise. Each missed flag risks fines averaging $2M. Existing tools score risk but cannot explain why in regulatory language a compliance officer can cite to a regulator.

## The solution

ComplianceOS sits in front of settlement. It calls Claude Opus 4.7, which reasons against embedded FATF, MiCA, FCA, and MAS regulatory documents and returns a structured decision with the exact rule references that triggered it — in under 2 seconds.

## Architecture

```
  Fintech
     │
     ▼  POST /check
  ┌──────────────────┐
  │ FastAPI          │
  └────────┬─────────┘
           │
           ▼
   pgvector retrieval   (top-5 regulatory chunks, cosine similarity)
           │
           ▼
   Claude Opus 4.7      (async SDK, reasoning over 3 regulatory PDFs)
           │
           ▼
   decision engine      (parse + score-to-decision + sanctions override)
           │
           ├────────────▶  audit log       (Postgres, JSONB request + raw reasoning)
           │
           └────────────▶  Telegram alert  (FLAG / BLOCK only)
           │
           ▼
   JSON response contract
```

## Demo scenarios

| # | Input | Decision | Score |
|---|---|---|---|
| 1 | SG → UK, $2,500 USD, 1 transfer / 24h | **PASS** | 15 |
| 2 | AE → SG, 7 × $9,800 USD / 24h (structuring) | **FLAG** | 55 |
| 3 | IR → UK, $50,000 USDT (sanctions) | **BLOCK** | 95 |

Example `rule_references` from Scenario 3:

```json
[
  "FATF R.20",
  "FATF R.16",
  "OFAC SDN",
  "UK POCA 2002 s.330",
  "UK Money Laundering Regulations 2017",
  "FATF High-Risk Jurisdictions Call for Action"
]
```

## How to run

```bash
# 1.
cp .env.example .env    # add ANTHROPIC_API_KEY and TELEGRAM credentials

# 2.
docker compose up -d

# 3.
pip install -r requirements.txt

# 4.
python3 -m ingest.loader

# 5.
python3 main.py

# 6.
python3 tests/scenarios.py
```

## Tech stack

- Claude Opus 4.7 — AML/CFT reasoning engine
- FastAPI + Python 3.12 — async REST API
- PostgreSQL 16 + pgvector — vector store + audit log
- sentence-transformers all-MiniLM-L6-v2 — local embeddings
- python-telegram-bot v22 — real-time FLAG/BLOCK alerts

## Why Opus 4.7

The value isn't classification — a rules engine can classify. The value is the reasoning chain: Opus reads the actual regulatory text, identifies which clause applies, and explains why in language a compliance officer can use in a regulatory filing. That explanation is the audit trail.

## Judging criteria

- **Impact (30%)** — $61B annual AML compliance spend. 95% false positive rate is an industry-wide problem.
- **Demo (25%)** — Three live scenarios: PASS, FLAG, BLOCK. Telegram alert fires in real time. Full audit trail queryable via `GET /trace/{id}`.
- **Opus 4.7 use (25%)** — RAG over 3 regulatory PDFs. Chain-of-thought scoring. Jurisdiction-aware decision routing. Degraded fallback on API failure.
- **Depth (20%)** — Confidence calibration. Sanctioned country override. RULES regex hardened against model meta-text. Structured audit log with `claude_raw_output` preserved.
