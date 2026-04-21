import logging
import os

from telegram import Bot

logger = logging.getLogger(__name__)


async def send_alert(
    decision: str,
    score: int,
    reason: str,
    trace_id: str,
    rule_references: list[str],
) -> None:
    if decision not in ("FLAG", "BLOCK"):
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning(
            "Telegram alert skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"
        )
        return

    rules_joined = ", ".join(rule_references) if rule_references else "none"
    message = (
        "🚨 COMPLIANCE ALERT 🚨\n"
        f"Decision: {decision}\n"
        f"Score: {score}/100\n"
        f"Transaction: {trace_id}\n"
        f"Rules: {rules_joined}\n"
        f"Reason: {reason}"
    )

    try:
        bot = Bot(token=token)
        async with bot:
            await bot.send_message(chat_id=chat_id, text=message)
    except Exception:
        logger.exception("Failed to send Telegram alert (trace_id=%s)", trace_id)
