from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.chat_service import chat, chat_stream

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    system_prompt: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    top_p: float = Field(default=1.0, ge=0, le=1)
    thinking: Optional[str | bool] = None


class ChatResponse(BaseModel):
    content: str
    model: str
    finish_reason: str | None = None
    usage: dict


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    result = chat(
        message=req.message,
        model=req.model,
        system_prompt=req.system_prompt,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        top_p=req.top_p,
        thinking=req.thinking,
    )
    return ChatResponse(**result)


@router.post("/chat/stream")
def chat_stream_endpoint(req: ChatRequest):
    generator = chat_stream(
        message=req.message,
        model=req.model,
        system_prompt=req.system_prompt,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        top_p=req.top_p,
        thinking=req.thinking,
    )
    return StreamingResponse(generator, media_type="text/event-stream")
