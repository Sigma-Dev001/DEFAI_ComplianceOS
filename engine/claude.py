import json
import os

from anthropic import AsyncAnthropic

MODEL = "claude-opus-4-7"
MAX_TOKENS = 1024
TIMEOUT_SECONDS = 30.0

SYSTEM_PROMPT = (
    "You are a compliance analyst specializing in AML/CFT risk assessment. "
    "Analyze the transaction against the provided regulatory context. "
    "Always respond in exactly this format:\n"
    "SCORE: [0-100]\n"
    "CONFIDENCE: [low/medium/high]\n"
    "REASON: [plain English explanation of why this transaction is or is not suspicious]\n"
    "RULES: [comma-separated regulatory citations e.g. FATF R.20, MiCA Art.38]\n"
    "\n"
    "STRUCTURING CALIBRATION:\n"
    "- Structuring pattern alone (sub-threshold transfers, high velocity) = 45-60\n"
    "- Structuring + new account (<30 days) = 55-65\n"
    "- Structuring + sanctioned jurisdiction = 70-85\n"
    "- Sanctions hit alone (OFAC/UN listed country) = 80-95\n"
    "\n"
    "The 85+ range is reserved for sanctioned jurisdictions (e.g. IR, KP, RU). "
    "Structuring between FATF-compliant jurisdictions (e.g. AE, SG, UK, US) "
    "without a sanctions hit must score in the 55-65 FLAG range, not BLOCK."
)

FALLBACK_RESPONSE = (
    "SCORE: 50\n"
    "CONFIDENCE: low\n"
    "REASON: API unavailable\n"
    "RULES: none"
)


def _build_user_prompt(transaction: dict, chunks: list[str]) -> str:
    transaction_json = json.dumps(transaction, indent=2, default=str)
    if chunks:
        numbered = "\n\n".join(
            f"[{i + 1}] {chunk}" for i, chunk in enumerate(chunks)
        )
    else:
        numbered = "(no regulatory context retrieved)"
    return (
        f"Transaction:\n{transaction_json}\n\n"
        f"Relevant regulations:\n{numbered}\n\n"
        "Score this transaction's compliance risk."
    )


async def call_claude(transaction: dict, chunks: list[str]) -> str:
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
                {"role": "user", "content": _build_user_prompt(transaction, chunks)}
            ],
        )
        parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        text = "".join(parts).strip()
        return text or FALLBACK_RESPONSE
    except Exception:
        return FALLBACK_RESPONSE
