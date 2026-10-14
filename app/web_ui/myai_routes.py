"""MyAI: the dashboard help assistant (POST /myai). Needs a login like every other route."""

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from agent import dashboard_help
from app.web_ui.auth_routes import get_current_username

router = APIRouter()


class MyAIRequest(BaseModel):
    message: str


class MyAIResponse(BaseModel):
    answer: str
    intent: str = "help"
    topic: str | None = None


@router.post("/myai", response_model=MyAIResponse)
async def myai(body: MyAIRequest, username: str = Depends(get_current_username)):
    """Answer a how-do-I question about the dashboard."""
    return MyAIResponse(**await run_in_threadpool(dashboard_help.answer, body.message))
