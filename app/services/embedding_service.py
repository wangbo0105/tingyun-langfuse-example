from openai import OpenAI

from app.config import settings

_client = OpenAI(
    api_key=settings.embedding_api_key or settings.openai_api_key,
    base_url=settings.embedding_base_url,
)


def create_embedding(text: str, model: str | None = None, dimensions: int | None = None) -> dict:
    kwargs = dict(
        model=model or settings.embedding_model,
        input=[text],
    )
    if dimensions:
        kwargs["dimensions"] = dimensions

    response = _client.embeddings.create(**kwargs)

    data = response.data[0]
    return {
        "embedding": data.embedding[:8],
        "total_dimensions": len(data.embedding),
        "model": response.model,
        "dimensions": dimensions,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "total_tokens": response.usage.total_tokens,
        },
    }


def create_full_embedding(text: str, model: str | None = None, dimensions: int | None = None) -> dict:
    """Return the full embedding vector (not truncated) for Milvus store/search."""
    kwargs = dict(
        model=model or settings.embedding_model,
        input=[text],
    )
    if dimensions:
        kwargs["dimensions"] = dimensions

    response = _client.embeddings.create(**kwargs)

    data = response.data[0]
    return {
        "embedding": data.embedding,
        "total_dimensions": len(data.embedding),
        "model": response.model,
        "dimensions": dimensions,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "total_tokens": response.usage.total_tokens,
        },
    }
