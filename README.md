# DEFAI ComplianceOS

> We automate cross-jurisdictional compliance screening for digital asset
> transactions — so your team doesn't manually reconcile VARA, MAS, and FCA
> requirements every time value moves between networks.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green)
![Claude](https://img.shields.io/badge/Claude-Opus%204.7-orange)
![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Who it's for

Built for Series A–B digital asset funds operating across UAE, Singapore,
and UK. Your compliance stack was built for one regulator. DEFAI ComplianceOS
screens every transaction against VARA, MAS, and FCA simultaneously and
returns per-regulator decisions with clause-level citations in under 2 seconds.

## What it does

- Per-regulator PASS/FLAG/BLOCK with clause-level citations (VARA, MAS, FCA, FATF)
- OFAC SDN wallet screening before Claude is called
- Full audit trail: `claude_raw_output` + regulatory snapshot ID per decision
- Sub-2s latency, async FastAPI, PostgreSQL audit log
- `/audit`, `/trace/{id}`, `/health`, Swagger at `/docs`

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
   OFAC SDN screen      (from_address / to_address — bypass Claude on hit)
           │
           ▼
   pgvector retrieval   (top-3 chunks per jurisdiction, cosine similarity)
           │
           ▼
   Claude Opus 4.7      (async SDK, per-regulator JSON reasoning)
           │
           ▼
   decision engine      (per-regulator score, worst-case aggregate,
                         sanctions override, structured citations)
           │
           ├────────────▶  audit log       (Postgres, JSONB request + raw reasoning)
           │
           └────────────▶  Telegram alert  (FLAG / BLOCK only)
           │
           ▼
   JSON response contract
```

Supported jurisdictions: **VARA, MAS, FCA, FATF**.

## Demo scenarios

| # | Input | Decision | Score |
|---|---|---|---|
| 1 | SG → UK, $2,500 USD, 1 transfer / 24h | **PASS** | low |
| 2 | AE → SG, 7 × $9,800 USD / 24h (structuring) | **FLAG** | mid |
| 3 | IR → UK, $50,000 USDT (sanctions) | **BLOCK** | high |
| 4 | US → US, $1,000 USDT, OFAC SDN wallet `149w62rY…StKeq8C` | **BLOCK** | 100 |

Scenario 4 bypasses Claude entirely — the OFAC SDN match returns
`decision=BLOCK, score=100, confidence=1.0` with the matched SDN entry name
in the `reason` field.

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

## Endpoints

- `POST /check` — score a transaction against VARA, MAS, and FCA; returns per-regulator decisions + aggregate PASS/FLAG/BLOCK with clause-level citations
- `GET /audit` — last 20 decisions (trace_id, decision, score, confidence, reason, rule_references, processing_ms, created_at)
- `GET /trace/{transaction_id}` — full audit row including Claude's raw reasoning and regulatory snapshot ID
- `GET /health` — liveness probe + regulatory_docs_loaded + transactions_processed
- `GET /docs` — Swagger UI

## Tech stack

- Claude Opus 4.7 — AML/CFT reasoning engine
- FastAPI + Python 3.12 — async REST API
- PostgreSQL 16 + pgvector — vector store + audit log
- sentence-transformers all-MiniLM-L6-v2 — local embeddings
- python-telegram-bot v22 — real-time FLAG/BLOCK alerts
- OFAC SDN XML — daily-refreshed crypto wallet screening

## Why Opus 4.7

The value isn't classification — a rules engine can classify. The value is
the reasoning chain: Opus reads the actual regulatory text, identifies
which clause applies per regulator, and explains why in language a
compliance officer can use in a regulatory filing. That explanation is the
audit trail.

## Judging criteria

- **Impact (30%)** — Series A–B digital asset funds operating across UAE/SG/UK pay six-figure annual fees per jurisdiction for siloed compliance tooling. This system returns per-regulator decisions in one call.
- **Demo (25%)** — Four live scenarios: PASS, FLAG, BLOCK, OFAC-BLOCK. Telegram alert fires in real time. Full audit trail queryable via `GET /trace/{id}`.
- **Opus 4.7 use (25%)** — RAG over VARA/MAS/FCA/FATF regulatory PDFs. Per-regulator JSON reasoning with verbatim clause quotes and transaction-field-to-rule-element mapping. Degraded fallback on API failure.
- **Depth (20%)** — Float confidence calibration with derived label. Sanctioned-country override. OFAC SDN pre-screen. Regulatory snapshot hash per decision. Structured audit log with `claude_raw_output` preserved.
