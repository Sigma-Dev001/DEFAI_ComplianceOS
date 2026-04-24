import logging
import os

from telegram import Bot

logger = logging.getLogger(__name__)


def _format_rule(rule) -> str:
    if isinstance(rule, dict):
        jur = str(rule.get("jurisdiction") or "").strip()
        rule_id = str(rule.get("rule_id") or "").strip()
        return " ".join(part for part in (jur, rule_id) if part) or "citation"
    return str(rule)


def _format_message(
    decision: str,
    score: int,
    confidence: str,
    reason: str,
    trace_id: str,
    rule_references: list,
) -> str:
    if rule_references:
        rules_block = "\n".join(f"• {_format_rule(rule)}" for rule in rule_references)
    else:
        rules_block = "• none"

    if decision == "FLAG":
        header = "⚠️ COMPLIANCE ALERT — FLAG"
        decision_line = "⚖️ Decision: Hold for manual review"
        why_line = "🔍 Why flagged:"
    else:
        header = "🚨 COMPLIANCE ALERT — BLOCK"
        decision_line = "⛔ Decision: Block transaction immediately"
        why_line = "🔍 Why blocked:"

    return (
        f"{header}\n"
        "\n"
        f"📋 Transaction: {trace_id}\n"
        f"📊 Risk Score: {score}/100  ({confidence} confidence)\n"
        f"{decision_line}\n"
        "\n"
        f"{why_line}\n"
        f"{reason}\n"
        "\n"
        "📜 Regulations triggered:\n"
        f"{rules_block}"
    )


async def send_alert(
    decision: str,
    score: int,
    confidence: str,
    reason: str,
    trace_id: str,
    rule_references: list[str],
) -> None:
    if decision not in ("FLAG", "BLOCK"):
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.info("Telegram not configured — skipping alert for trace %s", trace_id)
        return

    message = _format_message(
        decision=decision,
        score=score,
        confidence=confidence,
        reason=reason,
        trace_id=trace_id,
        rule_references=rule_references,
    )

    try:
        bot = Bot(token=token)
        async with bot:
            await bot.send_message(chat_id=chat_id, text=message)
    except Exception:
        logger.exception("Failed to send Telegram alert (trace_id=%s)", trace_id)
