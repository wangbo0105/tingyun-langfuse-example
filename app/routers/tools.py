from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.tools_service import tools_run

router = APIRouter(prefix="/api", tags=["tools"])


class ToolsRequest(BaseModel):
    query: str
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=1.0, ge=0, le=1)


class ToolsResponse(BaseModel):
    tool_calls: list[dict]
    final_answer: str


@router.post("/tools", response_model=ToolsResponse)
def tools_endpoint(req: ToolsRequest):
    result = tools_run(
        query=req.query,
        model=req.model,
        temperature=req.temperature,
        top_p=req.top_p,
    )
    return ToolsResponse(**result)
