import re

SCORE_RE = re.compile(r"SCORE:\s*(\d{1,3})", re.IGNORECASE)
CONFIDENCE_RE = re.compile(r"CONFIDENCE:\s*(low|medium|high)", re.IGNORECASE)
REASON_RE = re.compile(
    r"REASON:\s*(.+?)(?=\n\s*RULES:|\Z)", re.IGNORECASE | re.DOTALL
)
RULES_RE = re.compile(r"RULES:\s*(.+?)\Z", re.IGNORECASE | re.DOTALL)

SANCTIONED_COUNTRIES = {"IR", "KP", "SY", "CU", "SD", "MM", "BY"}


def _score_to_decision(score: int) -> str:
    if score <= 39:
        return "PASS"
    if score <= 65:
        return "FLAG"
    return "BLOCK"


def _decision_to_action(decision: str) -> str:
    return {
        "PASS": "Transaction cleared",
        "FLAG": "Hold for manual review",
        "BLOCK": "Block transaction immediately",
    }[decision]


def _parse_rules(raw_rules: str) -> list[str]:
    if not raw_rules:
        return []
    stripped = raw_rules.strip()
    if stripped.lower() in {"none", "n/a", "-"}:
        return []
    return [
        part.strip()
        for part in stripped.split(",")
        if part.strip() and part.strip().lower() != "none"
    ]


def _parse_failure(transaction_id: str, processing_ms: int) -> dict:
    return {
        "decision": "FLAG",
        "score": 50,
        "confidence": "low",
        "reason": "Parse error — manual review required",
        "rule_references": [],
        "recommended_action": "Hold for manual review",
        "trace_id": transaction_id,
        "processing_ms": processing_ms,
    }


def parse_claude_output(
    raw: str,
    transaction_id: str,
    transaction: dict,
    processing_ms: int,
) -> dict:
    if not raw or not isinstance(raw, str):
        return _parse_failure(transaction_id, processing_ms)

    score_match = SCORE_RE.search(raw)
    confidence_match = CONFIDENCE_RE.search(raw)
    reason_match = REASON_RE.search(raw)
    rules_match = RULES_RE.search(raw)

    if not score_match or not confidence_match or not reason_match:
        return _parse_failure(transaction_id, processing_ms)

    try:
        score = int(score_match.group(1))
    except ValueError:
        return _parse_failure(transaction_id, processing_ms)

    score = max(0, min(100, score))
    confidence = confidence_match.group(1).lower()
    reason = reason_match.group(1).strip()
    rule_references = _parse_rules(rules_match.group(1) if rules_match else "")

    decision = _score_to_decision(score)

    if decision == "BLOCK" and score < 85:
        sender_country = transaction.get("sender_country")
        receiver_country = transaction.get("receiver_country")
        is_sanctioned = (
            sender_country in SANCTIONED_COUNTRIES
            or receiver_country in SANCTIONED_COUNTRIES
        )
        if (
            sender_country is not None
            and receiver_country is not None
            and not is_sanctioned
        ):
            decision = "FLAG"

    recommended_action = _decision_to_action(decision)
    if decision == "FLAG":
        recommended_action = "Hold for manual review"

    return {
        "decision": decision,
        "score": score,
        "confidence": confidence,
        "reason": reason,
        "rule_references": rule_references,
        "recommended_action": recommended_action,
        "trace_id": transaction_id,
        "processing_ms": processing_ms,
    }
