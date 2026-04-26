"""FastAPI entry: REST + WebSocket + optional static frontend."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from smart_aroma.api.routes import router as api_router
from smart_aroma.config import get_settings
from smart_aroma.engine.aroma_controller import AromaController
from smart_aroma.logging_setup import setup_logging

log = logging.getLogger(__name__)


async def _broadcast_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(1.0)
        clients: list[WebSocket] = getattr(app.state, "ws_clients", [])
        if not clients:
            continue
        ctrl: AromaController = app.state.controller
        state = ctrl.get_public_state()
        stale: list[WebSocket] = []
        for ws in list(clients):
            try:
                await ws.send_json(state)
            except Exception:
                stale.append(ws)
        for ws in stale:
            if ws in clients:
                clients.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.controller = AromaController()
    app.state.ws_clients = []
    broadcast_task = asyncio.create_task(_broadcast_loop(app))
    log.info("SmartAroma backend started")
    try:
        yield
    finally:
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass
        log.info("SmartAroma backend shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_dir)

    app = FastAPI(title="SmartAroma", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.websocket("/ws/status")
    async def websocket_status(websocket: WebSocket) -> None:
        await websocket.accept()
        app.state.ws_clients.append(websocket)
        log.info("WebSocket connected; clients=%s", len(app.state.ws_clients))
        try:
            await websocket.send_json(app.state.controller.get_public_state())
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            log.info("WebSocket disconnected")
        finally:
            if websocket in app.state.ws_clients:
                app.state.ws_clients.remove(websocket)

    dist = settings.frontend_dist
    if dist is not None:
        p = Path(dist)
        if p.is_dir():
            app.mount("/", StaticFiles(directory=str(p), html=True), name="static")
            log.info("Serving static frontend from %s", p.resolve())

    return app


app = create_app()
