# DEFAI ComplianceOS

> **Existing tools tell you what to flag. ComplianceOS tells you why.**
>
> Clause-level citations from VARA, MAS, and FCA on every transaction decision —
> the exact rule text a compliance officer puts in a regulatory filing.

> [!NOTE]
> **Status: Proof of concept.** Built in 5 days for the Anthropic Built with Opus 4.7 Hackathon (April 2026). This is Chapter 1 of three — the compliance-reasoning foundation. Not yet a production MVP. The path from PoC → MVP → production is in [Roadmap](#roadmap) below.

> [!IMPORTANT]
> **Decision-support tooling. Not legal advice.** ComplianceOS surfaces the regulatory clauses an officer can review and cite — it does not replace a licensed compliance officer or counsel. Human-in-the-loop review is required before any regulatory filing.

**▶ [Watch the demo](https://youtu.be/TZbuB_EqJLA)**

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green)
![Claude](https://img.shields.io/badge/Claude-Opus%204.7-orange)
![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Try it

```bash
curl -X POST http://localhost:8000/check \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "demo_003",
    "amount": 50000,
    "currency": "USDT",
    "sender_country": "IR",
    "receiver_country": "UK",
    "jurisdiction": "FCA",
    "transfer_count_24h": 1
  }'
```

Returns a BLOCK decision with per-regulator scores (VARA/MAS/FCA) and
rule_references populated with verbatim regulatory quotes — see
The wedge below.

## Who it's for

Built for Series A–B digital asset funds operating across UAE, Singapore,
and UK. Your compliance stack was built for one regulator. DEFAI ComplianceOS
screens every transaction against VARA, MAS, and FCA simultaneously and
returns per-regulator decisions with clause-level citations in a single API
call: sub-second on OFAC SDN hits, 15–25s on full Opus 4.7 reasoning over
retrieved regulatory context.

## Why now — April 2026

VARA Phase 2 enforcement is live. MiCA's transition window closed in
December 2025 and EU crypto firms are now fully in scope. The FCA's
financial promotion regime for cryptoassets has been in force for over
two years and enforcement actions are accelerating. A fund operating
UAE ↔ Singapore ↔ UK in 2026 is reconciling three hardening regimes on
every transfer — and paying a six-figure annual seat fee per
jurisdiction for tools that score wallets but don't cite rules.

## What it does

- Per-regulator PASS/FLAG/BLOCK with clause-level citations (VARA, MAS, FCA, FATF)
- OFAC SDN wallet screening before Claude is called (sub-second bypass on hit)
- Full audit trail: `claude_raw_output`, content-hashed regulatory snapshot ID, system-prompt hash, override logging
- Async FastAPI, PostgreSQL audit log, fire-and-forget alert delivery off the request path
- `/audit`, `/trace/{id}`, `/health`, Swagger at `/docs`

**Latency:** OFAC SDN bypass returns in under a second. Full Opus 4.7 reasoning runs 15–25s including per-jurisdiction retrieval and structured citation generation.

## The wedge: clause-level citations

Every FLAG or BLOCK decision carries one or more citation objects. Each citation names a specific regulatory clause, quotes it verbatim, and maps a transaction field to the element of the rule it satisfies. Example from a Scenario 3 (Iran → UK, $50k USDT) run:

```json
{
  "jurisdiction": "FCA",
  "instrument": "Financial Crime Guide (FCG)",
  "rule_id": "FCG 7.2.3",
  "quote_excerpt": "Firms must ensure that their systems and controls are adequate to identify transactions with individuals or entities in jurisdictions subject to UK financial sanctions."
}
```

This is what a compliance officer would otherwise spend an hour drafting by hand against the rulebook PDF — and what they'd get fined for getting wrong.

## Architecture

![Architecture](docs/images/architecture.png)

Supported jurisdictions: **VARA, MAS, FCA, FATF**.

## Demo scenarios

| # | Input | Decision | Score |
|---|---|---|---|
| 1 | SG → UK, $500 USD, 1 transfer / 24h | **PASS** | low |
| 2 | AE → SG, 7 × $9,800 USD / 24h (structuring) | **FLAG** | mid |
| 3 | IR → UK, $50,000 USDT (sanctions) | **BLOCK** | high |
| 4 | US → US, $1,000 USDT, OFAC SDN wallet `149w62rY…StKeq8C` | **BLOCK** | 100 |

Scenario 4 bypasses Claude entirely — the OFAC SDN match returns
`decision=BLOCK, score=100, confidence=1.0` with the matched SDN entry name
in the `reason` field.

## How to run

```bash
# 1.
cp .env.example .env    # add ANTHROPIC_API_KEY (TELEGRAM_* vars are optional — leave blank to skip alerts)

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
- **Opus 4.7 use (25%)** — RAG over VARA/MAS/FCA/FATF regulatory PDFs. Per-regulator JSON reasoning with verbatim clause quotes from the source regulatory text. Content-hashed prompt + regulatory snapshot for audit-grade reproducibility. Degraded fallback on API failure.
- **Depth (20%)** — Float confidence calibration with derived label. Two hard overrides in the decision engine: (a) sanctioned-jurisdiction force-BLOCK (any transfer with sender or receiver in the sanctions set is forced to aggregate BLOCK with score floor 85 — same pattern as OFAC SDN wallet screening, at the country level); (b) jurisdiction-aware BLOCK→FLAG downgrade (Claude's per-regulator BLOCK is only honored when score≥85 OR a sanctioned jurisdiction is involved). Every override writes `override_applied=true` and a reason string into the audit row. OFAC SDN wallet pre-screen bypasses Claude entirely on hit. Content-hashed regulatory snapshot ID per decision. Structured audit log with `claude_raw_output` preserved verbatim.

## Roadmap

I'm building ComplianceOS as the first of three chapters. One product, three expansions, targeting the highest-value unsolved problems at the intersection of finance, blockchain, and AI.

**Chapter 1 — The Interoperability Barrier (this repo, PoC).**
Cross-border compliance middleware. I built a pre-transaction PASS / FLAG / BLOCK decision engine that calls Claude Opus 4.7 with retrieved chunks from the actual VARA, MAS, FCA, and FATF rulebooks — pgvector cosine retrieval, top-3 chunks per jurisdiction. Every decision returns verbatim regulatory citations grounded in the source PDFs, plus a SHA-256 hash of the system prompt and a content hash of the regulatory snapshot, so any decision is reconstructable months later. Priced $500–$5K/mo — a fraction of incumbent enterprise tooling that runs $50K+/year per jurisdiction.

**Toward MVP:** 20–30 beta users across Series A–B digital-asset funds and cross-border fintechs in UAE, Singapore, and UK. Webhook integrations for compliance-team workflow tools, MiCA added to the ingestion pipeline, SLA-backed latency tiers. Compliance-officer-in-the-loop surfaces — review queues, citation-defensibility scoring, and SAR-narrative scaffolding seeded directly from any `/trace/{id}` audit row, reusing the same Claude reasoning chain that produced the original decision — are the next product layer.

**Chapter 2 — Settlement Asymmetry & Agent Identity (Month 9 target).**
Every AI agent that transacts today is anonymous to the regulator. A Claude-powered agent initiating a cross-border transfer on someone's behalf has no verifiable identity, no licensure attribution, no audit-grade record of who authorized it. As agent-initiated commerce scales — and it's scaling fast — this becomes the structural bottleneck for institutional adoption.

I'm extending ComplianceOS into an ERC-8004 + x402 identity layer. Agents register an on-chain identity per ERC-8004, the decentralized agent-registry standard. When an agent calls `/check`, it presents a Verifiable Credential signed by its issuing principal — the firm or individual that licensed it. ComplianceOS verifies the signature, anchors the credential's hash into the audit row, and binds the regulatory clause to a named, accountable actor. The x402 payment-required flow handles on-chain attestation and payment for compliance checks. "KYC for AI agents," shipped as a premium module on top of ComplianceOS, not a standalone product.

**Chapter 3 — Enterprise B2B Payment Rails (after P1 + P2 traction).**
B2B payments still run on 1970s tech — 30-day invoice cycles, 3–5 day cross-border settlement, 3–5% fees, manual reconciliation. The compliance and identity foundations from Chapters 1 and 2 unlock something the incumbents structurally can't ship: an agentic treasury engine where compliance is checked at decision time, identity is verified at decision time, and settlement happens atomically on stablecoin rails (USDC, USDT, EURC) — same call, same second.

Target buyer: mid-market treasury teams at firms already operating across the UAE ↔ Singapore ↔ UK corridor where crypto-native and traditional finance overlap. AI agents managing treasury allocations, rebalancing across jurisdictions, auto-checking compliance per move, settling in seconds instead of days. Compliance-by-construction. Identity-by-construction. Settlement-by-default.

Beachheads across all three chapters: **UAE, Singapore, UK.** Nigeria is the origin, not the ceiling.

> *"Chapter 1 proves you can solve the compliance problem. Chapter 2 proves you can extend that into the agent economy. Chapter 3 is the infrastructure play that makes you a category leader."*

---

Built in 5 days by **Samuel Uzoamaka** — Lagos, Nigeria. [Watch the demo](https://youtu.be/TZbuB_EqJLA) · [GitHub](https://github.com/Sigma-Dev001/DEFAI_ComplianceOS)
