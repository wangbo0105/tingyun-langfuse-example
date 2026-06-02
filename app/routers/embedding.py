from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.embedding_service import create_embedding

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
