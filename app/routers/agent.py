from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.agent_service import agent_run, agent_stream

router = APIRouter(prefix="/api", tags=["agent"])


class AgentRequest(BaseModel):
    query: str
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=1.0, ge=0, le=1)


class AgentResponse(BaseModel):
    steps: list[dict]
    final_answer: str


@router.post("/agent", response_model=AgentResponse)
def agent_endpoint(req: AgentRequest):
    result = agent_run(
        query=req.query,
        model=req.model,
        temperature=req.temperature,
        top_p=req.top_p,
    )
    return AgentResponse(**result)


@router.post("/agent/stream")
def agent_stream_endpoint(req: AgentRequest):
    generator = agent_stream(
        query=req.query,
        model=req.model,
        temperature=req.temperature,
        top_p=req.top_p,
    )
    return StreamingResponse(generator, media_type="text/event-stream")
