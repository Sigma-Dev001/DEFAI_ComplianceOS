import json
import os

from anthropic import AsyncAnthropic

MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096
TIMEOUT_SECONDS = 45.0

SYSTEM_PROMPT = (
    "You are a compliance analyst specializing in AML/CFT risk assessment. "
    "You will be given a transaction and regulatory context grouped by regulator.\n\n"
    "For EACH regulator (VARA, MAS, FCA), score the transaction against that "
    "regulator's own rules on a 0-100 scale:\n"
    "- 0-39 = PASS (no material concerns under this regulator)\n"
    "- 40-65 = FLAG (requires human review under this regulator)\n"
    "- 66-100 = BLOCK (must be blocked under this regulator)\n\n"
    "Respond with ONLY valid JSON, no markdown fences, no prose outside the JSON. "
    "The JSON shape MUST be:\n"
    "{\n"
    '  "decisions": {\n'
    '    "vara": {"score": 0, "citations": [<citation>, ...]},\n'
    '    "mas":  {"score": 0, "citations": [<citation>, ...]},\n'
    '    "fca":  {"score": 0, "citations": [<citation>, ...]}\n'
    "  },\n"
    '  "confidence": 0.00,\n'
    '  "summary_reason": "one to two sentence overall summary",\n'
    '  "recommended_action": "string"\n'
    "}\n\n"
    "Each <citation> object MUST have all five keys populated:\n"
    '  {"jurisdiction": "VARA", "instrument": "Compliance and Risk Management Rulebook", '
    '"rule_id": "Part II Rule 1.2", "effective_date": "2023-02-07", '
    '"quote_excerpt": "<=60 word direct quote from the clause"}\n\n'
    "confidence MUST be a float between 0.00 and 1.00 expressing your overall "
    "certainty. FATF chunks are provided as supporting context — cite them when "
    "relevant but do NOT produce a top-level FATF decision.\n\n"
    "Scoring anchors (non-negotiable):\n"
    "- Transaction involving OFAC/UN sanctioned country (IR, KP, SY, CU, SD, MM, "
    "BY): every regulator must score 80+, decision BLOCK.\n"
    "- Sub-threshold high-velocity structuring between FATF-compliant "
    "jurisdictions (e.g. AE to SG): score 45-65, decision FLAG. The human "
    "reviewer escalates to BLOCK, not you.\n"
    "- Clean single transfer between regulated jurisdictions: score 10-30, PASS."
)

FALLBACK_RESPONSE = json.dumps(
    {
        "decisions": {
            "vara": {"score": 50, "citations": []},
            "mas": {"score": 50, "citations": []},
            "fca": {"score": 50, "citations": []},
        },
        "confidence": 0.30,
        "summary_reason": "API unavailable — defaulting to manual review",
        "recommended_action": "Hold for manual review",
    }
)


def _build_user_prompt(transaction: dict, chunks_by_jur: dict[str, list[dict]]) -> str:
    transaction_json = json.dumps(transaction, indent=2, default=str)

    blocks: list[str] = []
    for jur in sorted(chunks_by_jur.keys()):
        chunks = chunks_by_jur.get(jur) or []
        if not chunks:
            continue
        numbered = "\n\n".join(
            f"[{i + 1}] ({c.get('source_document', 'unknown')}) {c.get('content', '')}"
            for i, c in enumerate(chunks)
        )
        blocks.append(f"=== {jur} ===\n{numbered}")

    regs = "\n\n".join(blocks) if blocks else "(no regulatory context retrieved)"

    return (
        f"Transaction:\n{transaction_json}\n\n"
        f"Regulatory context (grouped by regulator):\n{regs}\n\n"
        "Return the JSON object now."
    )


async def call_claude(
    transaction: dict, chunks_by_jur: dict[str, list[dict]]
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return FALLBACK_RESPONSE

    try:
        client = AsyncAnthropic(api_key=api_key, timeout=TIMEOUT_SECONDS)
        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": _build_user_prompt(transaction, chunks_by_jur),
                }
            ],
        )
        parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        text = "".join(parts).strip()
        return text or FALLBACK_RESPONSE
    except Exception:
        return FALLBACK_RESPONSE
