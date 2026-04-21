from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes import router
from db.models import RegulatoryChunk, Transaction
from db.session import create_tables, get_db

MODEL = "claude-opus-4-7"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="DEFAI ComplianceOS",
    description=(
        "AML/CFT compliance middleware. POST a transaction, "
        "get PASS/FLAG/BLOCK with regulatory citations in under 2 seconds."
    ),
    version="1.0.0",
    contact={
        "name": "Sigma",
        "url": "https://github.com/Sigma-Dev001/DEFAI_ComplianceOS",
    },
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    docs_result = await db.execute(
        select(func.count(func.distinct(RegulatoryChunk.source_document)))
    )
    tx_result = await db.execute(select(func.count(Transaction.id)))
    return {
        "status": "ok",
        "model": MODEL,
        "regulatory_docs_loaded": docs_result.scalar_one(),
        "transactions_processed": tx_result.scalar_one(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
