# DEFAI ComplianceOS — Demo Video Script

**Target length:** 2:55–3:00
**Cadence:** ~140 wpm, conversational
**Voiceover:** Samuel, first-person

Em-dashes are half-beat pauses. Paragraph breaks are full-beat pauses — breathe and let it land.

---

## 0:00 — Opening

[SCREEN: title card "DEFAI ComplianceOS" on dark background, then fades to a terminal prompt]

VO: "I'm Samuel — a student from Nigeria. For the past year I've been watching fintechs across Africa and the Gulf try to move money across borders. It is brutal. One missed flag on the wrong transfer, and a team can lose its license. So I built this."

---

## 0:22 — The wedge

[SCREEN: split view — left side a Chainalysis-style wallet report with "risk score: 87"; right side a blank Word doc titled "VARA mapping.docx"; then cross-fades to a compliance officer's cursor scrolling through a VARA Rulebook PDF]

VO: "Here's what bothered me. Existing tools will tell you a wallet has a risk score of 87. They will not tell you which clause of VARA, or MAS, or FCA that score actually maps to. So somewhere, a compliance officer is still sitting there, reading the rulebook by hand, trying to turn a number into a filing. That mapping — that's the wedge. That's what I built."

---

## 0:50 — Scenario 1: Clean (PASS)

[SCREEN: terminal running `python3 tests/scenarios.py --verbose`, scrolled to "SCENARIO 1 — CLEAN / Clean (SG→UK)" output block — Decision: PASS, Score: 20/100, Confidence 0.90 (high), Processing 22,605 ms; VARA PASS 15, MAS PASS 20, FCA PASS 15]

VO: "Let me show you. Four scenarios against the live endpoint. First one's clean — two-and-a-half thousand dollars, Singapore to the UK. Comes back PASS, score 20. Takes about 22 seconds, because Claude Opus is actually reading the regulatory text for each of the three jurisdictions before it decides. No regulator flagged it. Fine — move on."

---

## 1:15 — Scenario 2: Structuring (FLAG)

[SCREEN: terminal scrolls to "SCENARIO 2 — STRUCTURING / Structuring (AE→SG)" — Decision: FLAG, Score 55/100, Confidence 0.82 (high); per-regulator VARA FLAG 55, MAS FLAG 55, FCA FLAG 50; then verbose JSON scrolls to the rule_references block highlighting VARA Part III Section G, MAS Paragraph 13.8, FATF Recommendation 16, FCA FCG Glossary — Occasional Transaction / Linked Transactions]

VO: "Second one is more interesting. UAE to Singapore — seven transfers, ninety-eight hundred dollars each, all inside twenty-four hours. Classic sub-threshold structuring. Comes back FLAG, score 55. And this is where the per-regulator breakdown matters. VARA, MAS, and FCA each scored it independently — with FATF as supporting context. Four clause-level citations right there. That's the mapping a compliance officer would have spent an hour writing by hand."

---

## 1:50 — Scenario 3: Sanctions (BLOCK — money shot)

[SCREEN: terminal scrolls to "SCENARIO 3 — SANCTIONS / Sanctions (IR→UK)" — Decision: BLOCK, Score 88/100, Confidence 0.95, Processing 27,106 ms; VARA BLOCK 85, MAS BLOCK 82, FCA BLOCK 88; then verbose JSON zooms to a single FCA citation showing the verbatim quote_excerpt, effective_date, and mapping fields]

VO: "Third. Fifty thousand USDT, Iran to the UK. BLOCK — score 88. And this is the one I'm most proud of. Every citation carries the verbatim regulatory quote, the effective date, and a one-sentence mapping from a transaction field to the rule element it satisfies. That text right there is what ends up in a regulatory filing."

---

## 2:20 — Scenario 4: OFAC (BLOCK, deterministic)

[SCREEN: terminal scrolls to "SCENARIO 4 — OFAC HIT / OFAC SDN (US→US)" — Decision: BLOCK, Score 100/100, Confidence 1.00, Processing: 3 ms; reason line: "Wallet address 149w62rY42aZBox8fGcmqNsXUzSStKeq8C matches OFAC SDN entry: Ali KHORASHADIZADEH"]

VO: "Last one — a wallet that's on the OFAC SDN list. Three milliseconds. Claude was never called. Sub-second blocking where the answer is deterministic — full reasoning where it isn't."

---

## 2:35 — Audit trail

[SCREEN: browser tab open on `http://localhost:8000/trace/demo_003` — pretty-printed JSON; cursor highlights `claude_raw_output`, then `system_prompt_hash`, then `reg_snapshot_id`, then `override_applied` / `override_reason`]

VO: "Every decision writes a full audit trail. Claude's raw output verbatim. A hash of the system prompt. A content hash of the regulatory documents in play. Override logging. Every decision is legally reconstructable — months later."

---

## 2:52 — Telegram

[SCREEN: Telegram Desktop window — three messages visible in order: "⚠️ COMPLIANCE ALERT — FLAG" for demo_002, "🚨 COMPLIANCE ALERT — BLOCK" for demo_003, "🚨 COMPLIANCE ALERT — BLOCK" for demo_004]

VO: "And every FLAG or BLOCK fires a Telegram alert — off the request path, never blocking the response. Three alerts from the run you just watched."

---

## 3:00 — Closing

[SCREEN: closing title card — "ComplianceOS" with the closing line]

VO: "Existing tools tell you what to flag. ComplianceOS tells you why."

---

## Numbers quoted (all captured from live run on 2026-04-22)

| Scenario | Decision | Score | Confidence | Processing |
|---|---|---|---|---|
| 1 — Clean (SG→UK) | PASS | 20 | 0.90 (high) | 22,605 ms |
| 2 — Structuring (AE→SG) | FLAG | 55 | 0.82 (high) | 22,491 ms |
| 3 — Sanctions (IR→UK) | BLOCK | 88 | 0.95 (high) | 27,106 ms |
| 4 — OFAC SDN (US→US) | BLOCK | 100 | 1.00 (high) | 3 ms (warm cache) |

Scenario 4 first-ever call was 52,236 ms because the OFAC SDN XML hadn't been downloaded yet; after that the cache is warm for 24 hours. The demo recording should be done with a warm cache so the 3 ms number is the one on screen.

## Production notes

- Run `python3 tests/scenarios.py` once against the running server to warm the OFAC SDN cache, then re-run for the recording.
- Use Telegram **Desktop**, not the phone app. Window-only capture.
- The `/trace/demo_003` browser tab should be the Opus-reasoned BLOCK (scenario 3), not the OFAC bypass — the OFAC trace has `claude_raw_output = "[OFAC SDN bypass — Claude not called]"` and empty citations, which undersells the audit trail.
- Numbers will drift slightly between runs. Re-capture the table above from the actual recording session and update the VO if any score moves by more than 5 points or any decision flips.
