from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from api.routes import router
from db.session import create_tables

MODEL = "claude-opus-4-7"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="DEFAI ComplianceOS", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": MODEL}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
