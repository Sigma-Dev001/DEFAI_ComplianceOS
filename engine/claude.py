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
    '  "summary_reason": "one to two sentence factual summary tying transaction fields to cited rules",\n'
    '  "recommended_action": "string"\n'
    "}\n\n"
    "CITATION REQUIREMENT — every citation must defend the score against a real "
    "clause. Each <citation> object MUST have all six keys populated:\n"
    "  {\n"
    '    "jurisdiction": "VARA",\n'
    '    "instrument": "Compliance and Risk Management Rulebook",\n'
    '    "rule_id": "Part II Rule 1.2",\n'
    '    "effective_date": "2023-02-07",\n'
    '    "quote_excerpt": "verbatim direct quote from the regulatory clause, 60 words or fewer",\n'
    '    "mapping": "This transaction triggers [rule_id] because [specific transaction field, e.g. transfer_count_24h=7] satisfies [element of the rule, e.g. \'unusual pattern\']."\n'
    "  }\n\n"
    "- quote_excerpt is a verbatim extract from the regulatory text, 60 words or fewer.\n"
    "- mapping is ONE sentence that names a specific field from the transaction "
    "(amount, currency, sender_country, receiver_country, transfer_count_24h, "
    "avg_transfer_amount, jurisdiction) AND the specific element of the cited "
    "rule that the field satisfies.\n\n"
    "Narrative language such as \"transaction exhibits structuring behavior\" is "
    "NOT acceptable in mapping or summary_reason. Every assertion must name a "
    "transaction field AND a rule element.\n\n"
    "EXAMPLE of acceptable mapping:\n"
    "  \"FATF R.20 requires that 'financial institutions should report suspicious "
    "transactions ... regardless of the amount.' This transaction triggers R.20 "
    "because transfer_count_24h=7 near the USD 10,000 reporting threshold "
    "satisfies the 'unusual pattern' condition.\"\n\n"
    "confidence MUST be a float between 0.00 and 1.00 representing the model's "
    "certainty in its classification. Do NOT return a label (high/medium/low).\n\n"
    "FATF chunks are provided as supporting context — cite FATF inside a "
    "regulator's decision when relevant but do NOT produce a top-level FATF "
    "decision.\n\n"
    "CALIBRATION GUIDANCE (guidance, not pinning — score from the evidence):\n"
    "- When structuring indicators are present between FATF-compliant "
    "jurisdictions (sub-threshold amounts, high 24h velocity, repeated similar "
    "amounts) and no aggravating factor is present, the FLAG range (40-65) is "
    "typically appropriate.\n"
    "- When a sanctioned jurisdiction (OFAC/UN lists, e.g. IR, KP, SY, CU, SD, "
    "MM, BY) is involved on either side of the transfer, the BLOCK range "
    "(66-100) is typically appropriate for regulators that enforce sanctions "
    "regimes.\n"
    "- These are reference bands. Score from the transaction evidence and the "
    "regulatory clauses you cite, not from these prompts alone."
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
