import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import asyncpg
from dotenv import load_dotenv

# Load .env from backend/
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def _clean_dsn(dsn: str) -> str:
    """
    asyncpg does not handle libpq's channel_binding query param; Neon and others add it.
    Strip it so pooled connections succeed.
    """
    dsn = dsn.strip()
    if not dsn:
        return dsn
    parsed = urlparse(dsn)
    q = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() != "channel_binding"
    ]
    new_query = urlencode(q)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


class PostgresDatabase:
    """
    PostgreSQL persistence for RAG documents and cached FAQ embeddings.
    Replaces the previous MongoDB collections: `documents`, `faq_vector_store`.
    """

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        if self.pool is not None:
            return
        raw = (os.getenv("DATABASE_URL") or "").strip()
        if not raw:
            raise ValueError(
                "DATABASE_URL is not set. Example: "
                "postgresql://user:password@localhost:5432/your_db"
            )
        dsn = _clean_dsn(raw)
        try:
            self.pool = await asyncpg.create_pool(
                dsn,
                min_size=1,
                max_size=10,
                command_timeout=120,
            )
        except Exception as e:
            raise RuntimeError(
                f"PostgreSQL connection failed: {e}. "
                "Check DATABASE_URL, that the server is reachable, and credentials."
            ) from e
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    doc_id TEXT UNIQUE NOT NULL,
                    text TEXT NOT NULL,
                    metadata JSONB,
                    chunk_count INT NOT NULL DEFAULT 0
                );
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faq_vector_store (
                    id SERIAL PRIMARY KEY,
                    faq_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding DOUBLE PRECISION[] NOT NULL,
                    text TEXT,
                    updated_at TIMESTAMPTZ,
                    UNIQUE (faq_id, content_hash)
                );
                """
            )
        print("Connected to PostgreSQL")

    async def _ensure_pool(self) -> None:
        """Connect on first use if startup did not run or failed."""
        if self.pool is None:
            await self.connect()

    async def disconnect(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None
            print("Disconnected from PostgreSQL")

    async def insert_document(self, collection_name: str, data: Dict[str, Any]) -> str:
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            if collection_name == "documents":
                meta = data.get("metadata")
                meta_json = json.dumps(meta) if isinstance(meta, dict) else meta
                await conn.execute(
                    """
                    INSERT INTO documents (doc_id, text, metadata, chunk_count)
                    VALUES ($1, $2, $3::jsonb, $4)
                    """,
                    data["doc_id"],
                    data["text"],
                    meta_json,
                    int(data.get("chunk_count", 0)),
                )
                return str(data["doc_id"])

            if collection_name == "faq_vector_store":
                emb = data["embedding"]
                await conn.execute(
                    """
                    INSERT INTO faq_vector_store
                        (faq_id, content_hash, embedding, text, updated_at)
                    VALUES ($1, $2, $3::double precision[], $4, $5)
                    ON CONFLICT (faq_id, content_hash) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        text = EXCLUDED.text,
                        updated_at = EXCLUDED.updated_at
                    """,
                    data["faq_id"],
                    data["content_hash"],
                    emb,
                    data.get("text"),
                    data.get("updated_at"),
                )
                return str(data["faq_id"])

        raise ValueError(f"Unknown table/collection: {collection_name}")

    async def get_document(
        self, collection_name: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            if collection_name == "faq_vector_store":
                row = await conn.fetchrow(
                    """
                    SELECT faq_id, content_hash, embedding, text, updated_at
                    FROM faq_vector_store
                    WHERE faq_id = $1 AND content_hash = $2
                    """,
                    query["faq_id"],
                    query["content_hash"],
                )
                if row is None:
                    return None
                emb = row["embedding"]
                return {
                    "faq_id": row["faq_id"],
                    "content_hash": row["content_hash"],
                    "embedding": list(emb) if emb is not None else [],
                    "text": row["text"],
                    "updated_at": row["updated_at"],
                }

            if collection_name == "documents":
                doc_id = query.get("doc_id")
                if doc_id is None:
                    return None
                row = await conn.fetchrow(
                    """
                    SELECT doc_id, text, metadata, chunk_count
                    FROM documents
                    WHERE doc_id = $1
                    """,
                    doc_id,
                )
                if row is None:
                    return None
                meta = row["metadata"]
                if isinstance(meta, str):
                    meta = json.loads(meta)
                return {
                    "doc_id": row["doc_id"],
                    "text": row["text"],
                    "metadata": meta or {},
                    "chunk_count": row["chunk_count"],
                }

        raise ValueError(f"Unknown table/collection: {collection_name}")


postgres_db = PostgresDatabase()
