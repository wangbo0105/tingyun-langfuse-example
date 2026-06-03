from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.embedding_service import create_embedding, create_full_embedding
from app.services import milvus_service

router = APIRouter(prefix="/api", tags=["embedding"])


class EmbeddingRequest(BaseModel):
    text: str
    model: str | None = None
    dimensions: int | None = Field(default=None, ge=1, le=8192)


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    total_dimensions: int
    model: str
    dimensions: int | None
    usage: dict


@router.post("/embedding", response_model=EmbeddingResponse)
def embedding_endpoint(req: EmbeddingRequest):
    result = create_embedding(text=req.text, model=req.model, dimensions=req.dimensions)
    return EmbeddingResponse(**result)


class StoreRequest(BaseModel):
    text: str
    model: str | None = None
    dimensions: int | None = Field(default=None, ge=1, le=8192)


class StoreResponse(BaseModel):
    id: str
    status: str
    vector_dim: int
    model: str
    embedding_preview: list[float]
    usage: dict


@router.post("/embedding/store", response_model=StoreResponse)
def store_endpoint(req: StoreRequest):
    emb = create_full_embedding(text=req.text, model=req.model, dimensions=req.dimensions)
    store_result = milvus_service.store_embedding(
        text=req.text,
        embedding=emb["embedding"],
        model=emb["model"],
    )
    return StoreResponse(
        id=store_result["id"],
        status=store_result["status"],
        vector_dim=store_result["vector_dim"],
        model=emb["model"],
        embedding_preview=emb["embedding"][:8],
        usage=emb["usage"],
    )
