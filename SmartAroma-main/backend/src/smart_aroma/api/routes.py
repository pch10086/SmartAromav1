"""REST API for aroma session control."""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from smart_aroma.models.sequence_schema import StartRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["control"])


class ActionResponse(BaseModel):
    ok: bool
    message: str


@router.get("/state")
def get_state(request: Request) -> dict:
    """Latest snapshot (same shape as WebSocket payloads)."""
    ctrl = request.app.state.controller
    return ctrl.get_public_state()


@router.post("/start", response_model=ActionResponse)
def start_session(body: StartRequest, request: Request) -> ActionResponse:
    ctrl = request.app.state.controller
    ok, msg = ctrl.start(body.scene, body.persona, body.duration_level)
    log.info(
        "REST POST /api/start scene=%s persona=%s duration_level=%s ok=%s",
        body.scene,
        body.persona,
        body.duration_level,
        ok,
    )
    return ActionResponse(ok=ok, message=msg)


@router.post("/pause", response_model=ActionResponse)
def pause_session(request: Request) -> ActionResponse:
    ok, msg = request.app.state.controller.pause()
    log.info("REST POST /api/pause ok=%s", ok)
    return ActionResponse(ok=ok, message=msg)


@router.post("/resume", response_model=ActionResponse)
def resume_session(request: Request) -> ActionResponse:
    ok, msg = request.app.state.controller.resume()
    log.info("REST POST /api/resume ok=%s", ok)
    return ActionResponse(ok=ok, message=msg)


@router.post("/stop", response_model=ActionResponse)
def stop_session(request: Request) -> ActionResponse:
    ok, msg = request.app.state.controller.stop()
    log.info("REST POST /api/stop ok=%s", ok)
    return ActionResponse(ok=ok, message=msg)
