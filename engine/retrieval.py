from dotenv import load_dotenv

load_dotenv()

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from db.models import RegulatoryChunk
from db.session import AsyncSessionLocal

MODEL_NAME = "all-MiniLM-L6-v2"
TOP_K = 5

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


async def retrieve(transaction: dict, top_k: int = TOP_K) -> list[str]:
    query = build_query(transaction)
    query_vec = embed(query)

    async with AsyncSessionLocal() as session:
        stmt = (
            select(RegulatoryChunk.content)
            .order_by(RegulatoryChunk.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]
