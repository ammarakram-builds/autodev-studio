"""FastAPI routes for AutoDev Studio."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agents import get_agents_metadata, AgencyOrchestrator
from backend.core.llm_client import LLMClient
from backend.memory.memory_manager import MemoryManager

router = APIRouter(prefix="/api", tags=["AutoDev Studio API"])

_memory_manager: Optional[MemoryManager] = None
_orchestrator: Optional[AgencyOrchestrator] = None


def get_memory_manager() -> MemoryManager:
    """Dependency provider for MemoryManager singleton."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def get_orchestrator(
    memory: MemoryManager = Depends(get_memory_manager),
) -> AgencyOrchestrator:
    """Dependency provider for AgencyOrchestrator."""
    global _orchestrator
    if _orchestrator is None:
        llm = LLMClient()
        _orchestrator = AgencyOrchestrator(llm=llm, memory=memory)
    return _orchestrator


class FeedbackRequest(BaseModel):
    """Payload schema for manual agent rule and feedback injection."""

    agent_name: str = Field(..., min_length=1, description="Target agent name or 'global'")
    lesson: str = Field(..., min_length=3, description="Actionable lesson or engineering rule")
    category: str = Field("general", description="Category tag (e.g., architecture, security, coding)")


@router.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    """Return metadata for all 20 specialized SaaS-building agents."""
    return get_agents_metadata()


@router.get("/memory")
def get_memory_state(
    memory: MemoryManager = Depends(get_memory_manager),
) -> dict[str, Any]:
    """Return current memory statistics, stored lessons, and full run history."""
    return {
        "stats": memory.get_stats(),
        "lessons": memory._memory.get("lessons", []),
        "runs": memory._memory.get("runs", []),
    }


@router.post("/memory/feedback")
def submit_feedback(
    payload: FeedbackRequest,
    memory: MemoryManager = Depends(get_memory_manager),
) -> dict[str, Any]:
    """Manually add or reinforce a learned rule for an agent or globally."""
    agent_name = payload.agent_name.strip()
    lesson = payload.lesson.strip()
    category = payload.category.strip() or "general"

    if not agent_name or not lesson:
        raise HTTPException(status_code=400, detail="agent_name and lesson cannot be empty.")

    lesson_record = memory.add_lesson(
        agent_name=agent_name,
        lesson=lesson,
        category=category,
    )

    return {
        "status": "success",
        "lesson": lesson_record,
        "stats": memory.get_stats(),
    }


@router.get("/run/stream")
def stream_pipeline_execution(
    project_idea: str = Query(..., min_length=1, description="SaaS project idea or prompt"),
    user_feedback: str = Query("", description="Optional feedback or steering guidance"),
    memory: MemoryManager = Depends(get_memory_manager),
):
    """Execute the 20-agent pipeline and stream live SSE events."""
    try:
        # Instantiate or retrieve orchestrator
        orchestrator = get_orchestrator(memory=memory)
    except Exception as exc:
        def error_event_stream():
            err_json = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            yield f"data: {err_json}\n\n"

        return StreamingResponse(
            error_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def sse_event_stream():
        try:
            for event in orchestrator.run_stream(
                project_idea=project_idea,
                user_feedback=user_feedback,
            ):
                event_data = json.dumps(event, ensure_ascii=False)
                yield f"data: {event_data}\n\n"
        except Exception as exc:
            err_payload = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            yield f"data: {err_payload}\n\n"

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
