# DEFAI ComplianceOS — Demo Video Script

**Target length:** 2:30–3:00
**Cadence:** ~145 wpm
**Voiceover:** Samuel, first-person, conversational

---

## 0:00 — Opening

[00:00] [SCREEN: plain title card — "DEFAI ComplianceOS" on dark background]
VO: "Hi, I'm Samuel. I'm a Nigerian student, and for the last year I've been watching African and Gulf fintechs try to move money across borders."

[00:08] [SCREEN: title card fades to a terminal prompt, cursor blinking]
VO: "One missed flag on a cross-jurisdictional transfer can cost a fintech its license. So I built this."

---

## 0:20 — Problem frame

[00:20] [SCREEN: split view — left side shows a Chainalysis-style wallet report with "risk score: 87"; right side shows a blank Word doc titled "VARA mapping.docx"]
VO: "Here's the gap. Existing tools tell you a wallet has a risk score of 87. They do not tell you which clause of VARA, MAS, or FCA that score maps to."

[00:33] [SCREEN: the blank Word doc fills with a compliance officer's cursor scrolling through a PDF of the VARA Rulebook]
VO: "Today, a compliance officer does that mapping by hand — reading the rulebook, finding the clause, writing the justification. That's the wedge. That's what I automated."

---

## 0:45 — Scenario 1: Clean (PASS)

[00:45] [SCREEN: terminal running `python3 tests/scenarios.py --verbose`, scrolled to "SCENARIO 1 — CLEAN / Clean (SG→UK)"]
VO: "Four live scenarios, hitting the real API. First one: two-and-a-half thousand US dollars, Singapore to the UK, one transfer in twenty-four hours."

[00:56] [SCREEN: the scenario 1 output block — Decision: PASS, Score: 20/100, Confidence 0.90 (high), Processing 22,605 ms; VARA PASS 15, MAS PASS 20, FCA PASS 15]
VO: "PASS. Score twenty out of a hundred. Twenty-two seconds, because Claude Opus reads the actual regulatory text for each of VARA, MAS, and FCA before it decides. No regulator flagged it."

---

## 1:13 — Scenario 2: Structuring (FLAG)

[01:13] [SCREEN: terminal scrolls to "SCENARIO 2 — STRUCTURING / Structuring (AE→SG)"]
VO: "Second one. UAE to Singapore. Seven transfers, each ninety-eight hundred dollars, in twenty-four hours. Classic sub-threshold structuring."

[01:24] [SCREEN: scenario 2 output — Decision: FLAG, Score 55/100, Confidence 0.82 (high); per-regulator VARA FLAG 55, MAS FLAG 55, FCA FLAG 50]
VO: "FLAG. Fifty-five. Three regulators scored it independently — VARA, MAS, FCA — plus FATF as supporting context. Four clause-level citations in total."

[01:38] [SCREEN: the verbose JSON scrolls to the rule_references block, highlighting VARA Part III Section G, MAS Paragraph 13.8, FATF Recommendation 16, and FCA FCG Glossary — Occasional Transaction / Linked Transactions]
VO: "VARA Part III Section G. MAS Paragraph 13.8. FATF Recommendation 16. FCA's linked-transactions clause. That's the mapping a human would have spent an hour writing."

---

## 1:55 — Scenario 3: Sanctions (BLOCK)

[01:55] [SCREEN: terminal scrolls to "SCENARIO 3 — SANCTIONS / Sanctions (IR→UK)"]
VO: "Third. Fifty thousand USDT, Iran to the UK."

[02:01] [SCREEN: scenario 3 output — Decision: BLOCK, Score 88/100, Confidence 0.95, Processing 27,106 ms; VARA BLOCK 85, MAS BLOCK 82, FCA BLOCK 88]
VO: "BLOCK. Eighty-eight."

[02:07] [SCREEN: verbose JSON highlights the FCA citation for FCG 3.2.15 — the verbatim quote_excerpt and mapping fields are visible]
VO: "This is the money shot. Every citation carries the verbatim regulatory quote, the effective date, and a one-sentence mapping from a transaction field to the rule element it satisfies. That text is what ends up in a regulatory filing."

---

## 2:23 — Scenario 4: OFAC (BLOCK, deterministic)

[02:23] [SCREEN: terminal scrolls to "SCENARIO 4 — OFAC HIT / OFAC SDN (US→US)"]
VO: "Fourth. A wallet address that's on the OFAC SDN list."

[02:28] [SCREEN: scenario 4 output — Decision: BLOCK, Score 100/100, Confidence 1.00, Processing: 3 ms; reason line: "Wallet address 149w62rY42aZBox8fGcmqNsXUzSStKeq8C matches OFAC SDN entry: Ali KHORASHADIZADEH"]
VO: "Three milliseconds. Claude was never called. Sub-second blocking where the answer is deterministic, full reasoning where it isn't."

---

## 2:38 — Audit trail

[02:38] [SCREEN: browser tab open on `http://localhost:8000/trace/demo_003` — pretty-printed JSON; cursor highlights `claude_raw_output`, then `system_prompt_hash`, then `reg_snapshot_id`, then `override_applied` / `override_reason`]
VO: "Every decision writes a trace. Claude's raw output verbatim. A hash of the system prompt. A content hash of the regulatory documents in play. Override logging. Every decision is legally reconstructable."

---

## 2:55 — Telegram

[02:55] [SCREEN: Telegram Desktop window — three messages visible in order: "⚠️ COMPLIANCE ALERT — FLAG" for demo_002, "🚨 COMPLIANCE ALERT — BLOCK" for demo_003, "🚨 COMPLIANCE ALERT — BLOCK" for demo_004]
VO: "FLAG and BLOCK decisions fire a Telegram alert off the request path. Three alerts from the run you just watched."

---

## 3:03 — Closing

[03:03] [SCREEN: closing title card — "ComplianceOS" with the line below]
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
