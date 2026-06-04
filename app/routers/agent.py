import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.agent_service import agent_run, agent_stream
from app.services.stream_utils import CancelToken, watch_disconnect

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
async def agent_stream_endpoint(req: AgentRequest, request: Request):
    cancel = CancelToken()
    generator = agent_stream(
        query=req.query,
        model=req.model,
        temperature=req.temperature,
        top_p=req.top_p,
        cancel=cancel,
    )
    response = StreamingResponse(generator, media_type="text/event-stream")
    asyncio.get_event_loop().create_task(watch_disconnect(request, cancel))
    return response
