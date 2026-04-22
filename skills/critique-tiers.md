---
name: critique-tiers
description: Separate architectural critique into four tiers so pre-customer work stays scoped — fix-now bugs, pilot-defensible shortcuts, partner-don't-build, file-for-later. Use whenever Samuel asks "what should I build next", "what's missing", or "critique this".
---

# Critique tiers

Every critique of this project must label each point by tier. Conflating tiers makes pre-customer work feel impossibly large; separating them lets Samuel act on the right things first.

## The four tiers

### Tier 1 — Fix-now bugs
Real broken behaviour, cheap to fix. Execute immediately.

Past examples (already fixed, use as calibration):
- Telegram send awaited in hot path → inflated processing_ms (fixed in 9f18a45 via `asyncio.create_task`)
- README claimed sub-second latency when Opus path runs 15-25s → false marketing (fixed in 5d63e26)
- Audit gaps: no prompt version, no content-hashed snapshot id, no override logging → silent compliance holes (fixed in 9f18a45)
- Alert tasks not awaited on shutdown → lost alerts on exit (fixed in ac948d5)

Typical fingerprint: one-file change, under 50 lines, fixes a concrete wrong behaviour rather than a theoretical one.

### Tier 2 — Pilot-defensible shortcuts
Architecturally imperfect, acceptable before the first paying customer. Call these out as "Phase 3 when revenue justifies the cost", not as "cosplay" or "wrong".

Examples:
- Single Claude call reasoning across all three regulators vs three parallel per-regulator calls — the single call is 3× cheaper and meets the contract today
- sentence-transformers local embeddings vs Voyage / OpenAI embeddings — fine for 4 PDFs; revisit when document count grows
- In-process OFAC cache vs Redis — fine for single-instance; revisit at multi-worker

### Tier 3 — Partner-don't-build
Another vendor already solves this better. The architecture should plug them in, not reimplement them.

Examples:
- Chainalysis has Travel Rule + KYT; feed its verdict into Claude's context, don't clone it
- TRM Labs has cluster analysis; same pattern
- Jumio / Onfido for identity; same pattern

Don't push Samuel to out-KYT Chainalysis from scratch. Frame these as integration points.

### Tier 4 — File for later
Relevant after a paying customer, irrelevant before.

Examples: SOC2, full tenant isolation, BYO-key encryption, regional data residency, 99.99% SLOs.

## How to respond when asked for critique

1. Label each point with its tier explicitly: `[T1] ...`, `[T2] ...`, etc.
2. For "next thing to build", pick from Tier 1 or from a genuine product gap (like the review queue — see `project_review_queue_priority` memory). Never lead with T2/T3/T4.
3. Don't produce one undifferentiated list. If the critique has four tiers of points, output four sections.
4. Be honest about where a concern lives. A thing can be architecturally correct AND T4 — say both.

## What counts as a "genuine product gap"

Something that blocks a compliance officer from replacing their current tool (Alessa, Hummingbird, spreadsheets + Slack) with this one. Right now that is the FLAG review queue: assignment, resolution, sign-off records. Without it, every FLAG fires into Telegram and dies — the system can only *add* an alert source, not *replace* a workflow.

Breadth of jurisdiction (more regulators) is not a product gap for the stated Series A-B UAE/SG/UK buyer. Depth of workflow is.
