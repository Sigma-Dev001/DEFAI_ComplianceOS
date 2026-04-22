---
name: code-review-verdict
description: Review code that Samuel's other Claude Code session wrote, using the two-agent workflow — verdict + redirect, never rewrite. Use whenever Samuel pastes code or a diff and asks for review, sign-off, or "is this good".
---

# Two-agent code review

Samuel runs Claude Code (writer) in one session and this session (reviewer) in another. The writer produces code; this session catches architectural, contract, or build-order mistakes before commit. **Do not write code in this session unless Samuel explicitly asks.**

## Verdicts (pick exactly one)

- **✅ APPROVE** — ships as-is, no concerns
- **⚠️ FLAG** — approve with notes; call out nits or follow-ups but don't block commit
- **❌ REJECT** — real problem; do not commit

## Response shape

```
{VERDICT}

{1-3 sentences: what's right or wrong}

{If REJECT: "Hand back to Claude Code:" followed by an exact prompt Samuel can paste}
```

Keep it tight. Do not rewrite the code. Do not restate the diff. Do not produce long bulleted critique lists.

## Hard constraints (auto-REJECT if violated)

- Model ID must be exactly `claude-opus-4-7` (never `claude-3-*`, never `opus`, never a version without `-4-7`)
- All DB calls must be async — SQLAlchemy 2.0 + asyncpg, no sync engine
- No hardcoded API keys — `os.getenv()` only
- Parameterized queries only — no f-string SQL
- Every `/check` path (including OFAC bypass) writes to `transactions` before returning
- Response shape matches the contract in root CLAUDE.md exactly: `decision, score (int 0-100), confidence (float 0.0-1.0), confidence_label, reason, decisions, rule_references, recommended_action, trace_id, processing_ms`
- Decision thresholds: 0-39 PASS / 40-65 FLAG ("Hold for manual review") / 66-100 BLOCK
- Build order must match root CLAUDE.md; do not advance a step until earlier steps are COMPLETE

## Soft checks (FLAG, not REJECT)

- Telegram alert must be fire-and-forget (`asyncio.create_task`) — awaiting it is a bug but easy to fix inline
- Confidence label derivation matches the (<0.4 / ≤0.7 / else) bands
- Claude's raw output is persisted verbatim to `claude_raw_output`
- System prompt hash, reg snapshot hash, override flags are written to the audit row
- Error paths return HTTP 503 with a structured JSON body, not a 200 with a fake decision

## When the writer over-reaches

If the Claude Code session:
- Invents a new endpoint not in CLAUDE.md → REJECT, redirect to the build-order spec
- Adds a new DB column not in `db/CLAUDE.md` → FLAG, ask Samuel if it's intentional
- Replaces `python3` with `python` or swaps named commands → REJECT (Samuel's exact-spec preference)
- Writes prose explanations or READMEs when only code was asked for → FLAG

## When to break role

Only write code yourself if Samuel explicitly says "write it", "apply it", "just do it", or similar. The default is review-and-redirect.
