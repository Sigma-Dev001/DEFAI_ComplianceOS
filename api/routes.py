import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alerts.telegram import send_alert
from db.models import Transaction
from db.session import get_db
from engine.claude import call_claude
from engine.decision import parse_claude_output
from engine.retrieval import retrieve

logger = logging.getLogger(__name__)

router = APIRouter()


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(..., description="Unique transaction identifier")
    amount: float = Field(..., description="Transaction amount in the specified currency")
    currency: str
    sender_country: str = Field(
        ..., description="ISO-2 country code of the sender e.g. SG, AE, IR"
    )
    receiver_country: str = Field(
        ..., description="ISO-2 country code of the receiver"
    )
    jurisdiction: str = Field(
        ..., description="Primary regulatory jurisdiction: FATF, MAS, FCA, MiCA"
    )
    transfer_count_24h: int = Field(
        1, description="Number of transfers by this sender in last 24 hours"
    )
    avg_transfer_amount: Optional[float] = Field(
        None, description="Average transfer amount in last 24 hours"
    )

    @model_validator(mode="after")
    def _default_avg_transfer_amount(self) -> "CheckRequest":
        if self.avg_transfer_amount is None:
            self.avg_transfer_amount = self.amount
        return self


@router.post(
    "/check",
    response_description=(
        "Compliance decision (PASS/FLAG/BLOCK) with score, confidence, "
        "plain-English reason, regulatory citations, recommended action, "
        "trace_id, and processing time in milliseconds."
    ),
)
async def check_transaction(
    payload: CheckRequest,
    db: AsyncSession = Depends(get_db),
):
    start = time.monotonic()
    transaction = payload.model_dump()

    try:
        try:
            chunks = await retrieve(transaction)
        except Exception:
            logger.warning(
                "Retrieval failed; proceeding with empty regulatory context",
                exc_info=True,
            )
            chunks = []

        raw_output = await call_claude(transaction, chunks)

        pre_commit_ms = int((time.monotonic() - start) * 1000)
        response = parse_claude_output(
            raw=raw_output,
            transaction_id=payload.transaction_id,
            transaction=transaction,
            processing_ms=pre_commit_ms,
        )

        try:
            db.add(
                Transaction(
                    transaction_id=payload.transaction_id,
                    request_payload=transaction,
                    claude_raw_output=raw_output,
                    decision=response["decision"],
                    score=response["score"],
                    confidence=response["confidence"],
                    reason=response["reason"],
                    rule_references=response["rule_references"],
                    recommended_action=response["recommended_action"],
                    processing_ms=pre_commit_ms,
                )
            )
            await db.commit()
        except Exception:
            logger.exception("Audit log write failed")
            await db.rollback()
            return JSONResponse(
                status_code=503,
                content={"error": "Audit log unavailable"},
            )

        response["processing_ms"] = int((time.monotonic() - start) * 1000)

        if response["decision"] in ("FLAG", "BLOCK"):
            await send_alert(
                decision=response["decision"],
                score=response["score"],
                confidence=response["confidence"],
                reason=response["reason"],
                trace_id=response["trace_id"],
                rule_references=response["rule_references"],
            )

        return response

    except Exception:
        logger.exception("Unhandled error in /check")
        return JSONResponse(
            status_code=503,
            content={"error": "Service temporarily unavailable"},
        )


@router.get(
    "/audit",
    response_description=(
        "The 20 most recent decisions, ordered by created_at DESC. "
        "Each row includes trace_id, decision, score, confidence, reason, "
        "rule_references, processing_ms, and created_at."
    ),
)
async def get_audit(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Transaction)
        .order_by(Transaction.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "trace_id": row.transaction_id,
            "decision": row.decision,
            "score": row.score,
            "confidence": row.confidence,
            "reason": row.reason,
            "rule_references": list(row.rule_references) if row.rule_references else [],
            "processing_ms": row.processing_ms,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get(
    "/trace/{transaction_id}",
    response_description=(
        "Full audit row for the most recent decision on this transaction_id, "
        "including the original request payload and Claude's raw reasoning output."
    ),
)
async def get_trace(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Transaction)
        .where(Transaction.transaction_id == transaction_id)
        .order_by(Transaction.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        return JSONResponse(status_code=404, content={"error": "not found"})

    return {
        "id": str(row.id),
        "transaction_id": row.transaction_id,
        "request_payload": row.request_payload,
        "claude_raw_output": row.claude_raw_output,
        "decision": row.decision,
        "score": row.score,
        "confidence": row.confidence,
        "reason": row.reason,
        "rule_references": list(row.rule_references) if row.rule_references else [],
        "recommended_action": row.recommended_action,
        "processing_ms": row.processing_ms,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
