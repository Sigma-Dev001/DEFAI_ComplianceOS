from dotenv import load_dotenv

load_dotenv()

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from db.models import RegulatoryChunk
from db.session import AsyncSessionLocal

MODEL_NAME = "all-MiniLM-L6-v2"
PER_JURISDICTION_K = 3

_model = SentenceTransformer(MODEL_NAME)
_model.max_seq_length = 512


def build_query(transaction: dict) -> str:
    fields = [
        ("amount", transaction.get("amount")),
        ("currency", transaction.get("currency")),
        ("sender_country", transaction.get("sender_country")),
        ("receiver_country", transaction.get("receiver_country")),
        ("jurisdiction", transaction.get("jurisdiction")),
        ("transfer_count_24h", transaction.get("transfer_count_24h")),
        ("avg_transfer_amount", transaction.get("avg_transfer_amount")),
    ]
    parts = [f"{key}={value}" for key, value in fields if value is not None]
    return "Transaction: " + "; ".join(parts)


def embed(text: str) -> list[float]:
    vector = _model.encode(text, normalize_embeddings=True)
    return vector.tolist()


async def retrieve(
    transaction: dict, per_jurisdiction: int = PER_JURISDICTION_K
) -> dict[str, list[dict]]:
    query = build_query(transaction)
    query_vec = embed(query)

    out: dict[str, list[dict]] = {}
    async with AsyncSessionLocal() as session:
        jur_rows = await session.execute(
            select(RegulatoryChunk.jurisdiction).distinct()
        )
        jurisdictions = sorted(r[0] for r in jur_rows.all())

        for jur in jurisdictions:
            stmt = (
                select(
                    RegulatoryChunk.content,
                    RegulatoryChunk.source_document,
                    RegulatoryChunk.jurisdiction,
                    RegulatoryChunk.created_at,
                )
                .where(RegulatoryChunk.jurisdiction == jur)
                .order_by(RegulatoryChunk.embedding.cosine_distance(query_vec))
                .limit(per_jurisdiction)
            )
            result = await session.execute(stmt)
            out[jur] = [
                {
                    "content": row.content,
                    "source_document": row.source_document,
                    "jurisdiction": row.jurisdiction,
                    "ingested_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in result.all()
            ]
    return out
