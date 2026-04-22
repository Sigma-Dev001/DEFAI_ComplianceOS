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
from screening.ofac import screen_wallet

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
    tx_hash: Optional[str] = Field(None, description="On-chain transaction hash")
    chain: Optional[str] = Field(None, description="Chain name e.g. bitcoin, ethereum, tron")
    from_address: Optional[str] = Field(None, description="Sender wallet address")
    to_address: Optional[str] = Field(None, description="Receiver wallet address")
    contract_address: Optional[str] = Field(
        None, description="Contract address if token transfer"
    )
    token_symbol: Optional[str] = Field(None, description="Token symbol e.g. USDT, USDC")

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
        sender_screen = await screen_wallet(payload.from_address)
        receiver_screen = await screen_wallet(payload.to_address)

        if sender_screen["hit"] or receiver_screen["hit"]:
            hit = sender_screen if sender_screen["hit"] else receiver_screen
            reason = (
                f"Wallet address {hit['address']} matches OFAC SDN entry: "
                f"{hit['match']}"
            )
            processing_ms = int((time.monotonic() - start) * 1000)
            ofac_decisions = {
                reg: {"decision": "BLOCK", "score": 100, "citations": []}
                for reg in ("vara", "mas", "fca")
            }
            response = {
                "decision": "BLOCK",
                "score": 100,
                "confidence": 1.0,
                "confidence_label": "high",
                "reason": reason,
                "decisions": ofac_decisions,
                "rule_references": [],
                "recommended_action": (
                    "Block transaction immediately — OFAC SDN wallet match"
                ),
                "trace_id": payload.transaction_id,
                "processing_ms": processing_ms,
            }
            try:
                db.add(
                    Transaction(
                        transaction_id=payload.transaction_id,
                        request_payload=transaction,
                        claude_raw_output="[OFAC SDN bypass — Claude not called]",
                        decision="BLOCK",
                        score=100,
                        confidence=1.0,
                        reason=reason,
                        rule_references=[],
                        recommended_action=response["recommended_action"],
                        decisions=ofac_decisions,
                        reg_snapshot_id=None,
                        processing_ms=processing_ms,
                    )
                )
                await db.commit()
            except Exception:
                logger.exception("Audit log write failed (OFAC bypass)")
                await db.rollback()
                return JSONResponse(
                    status_code=503,
                    content={"error": "Audit log unavailable"},
                )

            await send_alert(
                decision="BLOCK",
                score=100,
                confidence="high",
                reason=reason,
                trace_id=payload.transaction_id,
                rule_references=[],
            )
            return response

        transaction["wallet_screening"] = {
            "from_address": sender_screen,
            "to_address": receiver_screen,
            "status": "clean",
        }

        try:
            chunks_by_jur = await retrieve(transaction)
        except Exception:
            logger.warning(
                "Retrieval failed; proceeding with empty regulatory context",
                exc_info=True,
            )
            chunks_by_jur = {}

        raw_output = await call_claude(transaction, chunks_by_jur)

        pre_commit_ms = int((time.monotonic() - start) * 1000)
        response = parse_claude_output(
            raw=raw_output,
            transaction_id=payload.transaction_id,
            transaction=transaction,
            processing_ms=pre_commit_ms,
            chunks_by_jur=chunks_by_jur,
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
                    decisions=response["decisions"],
                    reg_snapshot_id=response.get("reg_snapshot_id"),
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

        response.pop("reg_snapshot_id", None)
        response["processing_ms"] = int((time.monotonic() - start) * 1000)

        if response["decision"] in ("FLAG", "BLOCK"):
            await send_alert(
                decision=response["decision"],
                score=response["score"],
                confidence=response["confidence_label"],
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
            "decisions": row.decisions,
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
        "decisions": row.decisions,
        "reg_snapshot_id": row.reg_snapshot_id,
        "processing_ms": row.processing_ms,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
