import asyncio
import hashlib
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import PyPDF2
from sentence_transformers import SentenceTransformer
from sqlalchemy import select, text

from db.models import RegulatoryChunk
from db.session import AsyncSessionLocal, create_tables

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "regulatory"
MODEL_NAME = "all-MiniLM-L6-v2"
TARGET_TOKENS = 220

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def detect_jurisdiction(filename: str) -> str:
    if "VARA" in filename:
        return "VARA"
    if "MAS" in filename:
        return "MAS"
    if "FCG" in filename:
        return "FCA"
    if "FATF" in filename:
        return "FATF"
    return "GENERAL"


def extract_text(path: Path) -> str:
    reader = PyPDF2.PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def file_content_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def chunk_text(text: str, tokenizer, target_tokens: int = TARGET_TOKENS) -> list[str]:
    sentences = split_sentences(text)
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0

    for sentence in sentences:
        sent_tokens = len(tokenizer.encode(sentence, add_special_tokens=False))
        if buffer and buffer_tokens + sent_tokens > target_tokens:
            chunks.append(" ".join(buffer))
            buffer = [sentence]
            buffer_tokens = sent_tokens
        else:
            buffer.append(sentence)
            buffer_tokens += sent_tokens

    if buffer:
        chunks.append(" ".join(buffer))
    return chunks


async def existing_chunk_indices(session, source_document: str) -> set[int]:
    result = await session.execute(
        select(RegulatoryChunk.chunk_index).where(
            RegulatoryChunk.source_document == source_document
        )
    )
    return {row[0] for row in result.all()}


async def ingest_file(path: Path, model: SentenceTransformer) -> None:
    filename = path.name
    jurisdiction = detect_jurisdiction(filename)
    doc_hash = file_content_hash(path)
    text = extract_text(path)
    chunks = chunk_text(text, model.tokenizer)
    total = len(chunks)

    if total == 0:
        print(f"Ingesting {filename}... no extractable text, skipping")
        return

    async with AsyncSessionLocal() as session:
        already_done = await existing_chunk_indices(session, filename)
        new_rows = 0
        for idx, content in enumerate(chunks):
            suffix = " (already ingested)" if idx in already_done else ""
            print(f"Ingesting {filename}... chunk {idx + 1}/{total}{suffix}")
            if idx in already_done:
                continue
            embedding = model.encode(content, normalize_embeddings=True).tolist()
            session.add(
                RegulatoryChunk(
                    source_document=filename,
                    chunk_index=idx,
                    content=content,
                    embedding=embedding,
                    jurisdiction=jurisdiction,
                    document_hash=doc_hash,
                )
            )
            new_rows += 1
        await session.commit()
        print(f"  {filename}: {new_rows} new chunks committed ({jurisdiction}) hash={doc_hash[:16]}")


async def backfill_document_hashes(pdfs: list[Path]) -> None:
    async with AsyncSessionLocal() as session:
        for path in pdfs:
            doc_hash = file_content_hash(path)
            await session.execute(
                text(
                    "UPDATE regulatory_chunks SET document_hash = :h "
                    "WHERE source_document = :f AND document_hash IS NULL"
                ),
                {"h": doc_hash, "f": path.name},
            )
        await session.commit()


async def main() -> None:
    await create_tables()
    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    model.max_seq_length = 512

    pdfs = sorted(DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {DOCS_DIR}")
        return

    await backfill_document_hashes(pdfs)
    print(f"Backfilled document_hash for {len(pdfs)} existing PDFs")

    for path in pdfs:
        await ingest_file(path, model)


if __name__ == "__main__":
    asyncio.run(main())
