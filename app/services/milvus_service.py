"""Milvus vector store service."""

from __future__ import annotations

import uuid
import time

from pymilvus import MilvusClient, DataType

from app.config import settings

_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    """Return a singleton MilvusClient, creating the collection on first call."""
    global _client
    if _client is None:
        uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
        _client = MilvusClient(uri=uri)
        _ensure_collection()
    return _client


def reset_client() -> None:
    """Reset the singleton so next call re-connects with updated settings."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


def _ensure_collection() -> None:
    """Create the collection and index if they don't exist."""
    client = get_milvus_client()
    collection_name = settings.milvus_collection

    if client.has_collection(collection_name):
        return

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(field_name="id", datatype=DataType.VARCHAR, max_length=64, is_primary=True)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=8192)
    schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=settings.milvus_dimensions)
    schema.add_field(field_name="model", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(field_name="created_at", datatype=DataType.INT64)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        params={"nlist": 128},
    )

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )


def store_embedding(
    text: str,
    embedding: list[float],
    model: str,
) -> dict:
    """Store an embedding vector into Milvus."""
    doc_id = uuid.uuid4().hex
    created_at = int(time.time())

    client = get_milvus_client()
    client.insert(
        collection_name=settings.milvus_collection,
        data=[{
            "id": doc_id,
            "text": text,
            "embedding": embedding,
            "model": model,
            "created_at": created_at,
        }],
    )
    return {"id": doc_id, "status": "stored", "vector_dim": len(embedding)}

