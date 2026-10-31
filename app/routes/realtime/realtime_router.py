"""Realtime change signals over a WebSocket (apps refetch on each signal)."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.constants.realtime.realtime_constants import PATH_REALTIME
from app.services.realtime import realtime_service

router = APIRouter()


@router.websocket(PATH_REALTIME)
async def realtime(websocket: WebSocket) -> None:
    await realtime_service.serve(websocket)
