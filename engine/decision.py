import hashlib
import json
import re

SANCTIONED_COUNTRIES = {"IR", "KP", "SY", "CU", "SD", "MM", "BY"}

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.IGNORECASE | re.DOTALL)
_JSON_BLOB_RE = re.compile(r"\{.*\}", re.DOTALL)

_CITATION_KEYS = (
    "jurisdiction",
    "instrument",
    "rule_id",
    "quote_excerpt",
)

_ACTION_BY_DECISION = {
    "PASS": "Transaction cleared",
    "FLAG": "Hold for manual review",
    "BLOCK": "Block transaction immediately",
}


def _extract_json(raw: str) -> dict | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        pass
    fence = _JSON_FENCE_RE.search(raw)
    if fence:
        try:
            return json.loads(fence.group(1))
        except (ValueError, TypeError):
            pass
    blob = _JSON_BLOB_RE.search(raw)
    if blob:
        try:
            return json.loads(blob.group(0))
        except (ValueError, TypeError):
            pass
    return None


def _score_to_decision(score: int) -> str:
    if score <= 39:
        return "PASS"
    if score <= 65:
        return "FLAG"
    return "BLOCK"


def _clamp_score(value) -> int:
    try:
        score = int(round(float(value)))
    except (ValueError, TypeError):
        score = 50
    return max(0, min(100, score))


def _clamp_confidence(value) -> float:
    try:
        conf = float(value)
    except (ValueError, TypeError):
        conf = 0.5
    return round(max(0.0, min(1.0, conf)), 2)


def _confidence_label(confidence: float) -> str:
    if confidence < 0.4:
        return "low"
    if confidence <= 0.7:
        return "medium"
    return "high"


def _normalize_citation(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    cleaned = {}
    for key in _CITATION_KEYS:
        value = raw.get(key)
        if value is None:
            return None
        cleaned[key] = str(value).strip()
        if not cleaned[key]:
            return None
    return cleaned


def _normalize_citations(raw_list) -> list[dict]:
    if not isinstance(raw_list, list):
        return []
    out: list[dict] = []
    for item in raw_list:
        normalized = _normalize_citation(item)
        if normalized is not None:
            out.append(normalized)
    return out


def _snapshot_hash(chunks_by_jur: dict[str, list[dict]] | None) -> str | None:
    if not chunks_by_jur:
        return None
    doc_hashes: set[tuple[str, str]] = set()
    for jur, chunks in chunks_by_jur.items():
        for chunk in chunks or []:
            doc_hash = chunk.get("document_hash")
            if not doc_hash:
                continue
            doc_hashes.add(
                (
                    str(chunk.get("jurisdiction", jur) or ""),
                    str(doc_hash),
                )
            )
    if not doc_hashes:
        return None
    hasher = hashlib.sha256()
    for t in sorted(doc_hashes):
        hasher.update(("|".join(t) + "\n").encode("utf-8"))
    return hasher.hexdigest()[:16]


def _parse_failure(
    transaction_id: str, processing_ms: int, reg_snapshot_id: str | None
) -> dict:
    return {
        "decision": "FLAG",
        "score": 50,
        "confidence": 0.30,
        "confidence_label": "low",
        "reason": "Parse error — manual review required",
        "decisions": {},
        "rule_references": [],
        "recommended_action": "Hold for manual review",
        "trace_id": transaction_id,
        "processing_ms": processing_ms,
        "reg_snapshot_id": reg_snapshot_id,
        "override_applied": False,
        "override_reason": None,
    }


def parse_claude_output(
    raw: str,
    transaction_id: str,
    transaction: dict,
    processing_ms: int,
    chunks_by_jur: dict[str, list[dict]] | None = None,
) -> dict:
    reg_snapshot_id = _snapshot_hash(chunks_by_jur)
    data = _extract_json(raw)
    if data is None or not isinstance(data.get("decisions"), dict):
        return _parse_failure(transaction_id, processing_ms, reg_snapshot_id)

    sender = transaction.get("sender_country")
    receiver = transaction.get("receiver_country")
    sanctions_hit = (
        sender in SANCTIONED_COUNTRIES or receiver in SANCTIONED_COUNTRIES
    )

    processed: dict[str, dict] = {}
    flat_citations: list[dict] = []
    max_score = 0
    has_block = False
    has_flag = False
    override_applied = False
    override_reasons: list[str] = []

    for reg_key, reg_body in data["decisions"].items():
        if not isinstance(reg_body, dict):
            continue
        score = _clamp_score(reg_body.get("score"))
        raw_decision = _score_to_decision(score)
        reg_decision = raw_decision

        if (
            raw_decision == "BLOCK"
            and score < 85
            and not sanctions_hit
            and sender is not None
            and receiver is not None
        ):
            reg_decision = "FLAG"
            override_applied = True
            override_reasons.append(
                f"{str(reg_key).lower()}: BLOCK(score={score}) downgraded to FLAG — "
                f"no sanctioned jurisdiction involved "
                f"(sender={sender}, receiver={receiver}) and score<85"
            )

        citations = _normalize_citations(reg_body.get("citations"))
        processed[str(reg_key).lower()] = {
            "decision": reg_decision,
            "score": score,
            "citations": citations,
        }
        flat_citations.extend(citations)
        max_score = max(max_score, score)
        if reg_decision == "BLOCK":
            has_block = True
        elif reg_decision == "FLAG":
            has_flag = True

    if not processed:
        return _parse_failure(transaction_id, processing_ms, reg_snapshot_id)

    if sanctions_hit:
        aggregate_decision = "BLOCK"
        if max_score < 85:
            max_score = 85
        override_applied = True
        override_reasons.append(
            f"Aggregate forced to BLOCK — sanctioned jurisdiction on "
            f"transfer (sender={sender}, receiver={receiver})"
        )
    elif has_block:
        aggregate_decision = "BLOCK"
    elif has_flag:
        aggregate_decision = "FLAG"
    else:
        aggregate_decision = "PASS"

    seen: set[tuple[str, str]] = set()
    unique_citations: list[dict] = []
    for citation in flat_citations:
        key = (citation["jurisdiction"], citation["rule_id"])
        if key in seen:
            continue
        seen.add(key)
        unique_citations.append(citation)

    confidence = _clamp_confidence(data.get("confidence"))
    summary = str(
        data.get("summary_reason") or data.get("reason") or "Manual review required"
    ).strip()
    recommended_action = str(
        data.get("recommended_action") or _ACTION_BY_DECISION[aggregate_decision]
    ).strip()
    if aggregate_decision == "FLAG" and not recommended_action:
        recommended_action = "Hold for manual review"

    return {
        "decision": aggregate_decision,
        "score": max_score,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "reason": summary,
        "decisions": processed,
        "rule_references": unique_citations,
        "recommended_action": recommended_action,
        "trace_id": transaction_id,
        "processing_ms": processing_ms,
        "reg_snapshot_id": reg_snapshot_id,
        "override_applied": override_applied,
        "override_reason": "; ".join(override_reasons) if override_reasons else None,
    }
