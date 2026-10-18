import asyncio
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from app.schemas.scale import ScaleActivity, ScaleHistory, ScaleMeasurement, ScaleSettings, ScaleStatus
from app.services.scale_service import ScaleService

router = APIRouter(prefix="/scales")


def get_scale_service(request: Request) -> ScaleService:
    return request.app.state.scale_service


@router.get("/status", response_model=ScaleStatus)
async def get_scale_status(service: ScaleService = Depends(get_scale_service)) -> ScaleStatus:
    return service.snapshot()


@router.put("/settings", response_model=ScaleStatus)
async def select_scale(payload: ScaleSettings, service: ScaleService = Depends(get_scale_service)) -> ScaleStatus:
    if payload.device_id:
        payload.device_id = payload.device_id.upper()
        if payload.device_id != service.status.device_id and payload.device_id not in {
            device.device_id for device in service.snapshot().devices
        }:
            raise HTTPException(400, "Сначала найдите весы поблизости")
    try:
        return await service.configure(payload)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/scan/start", response_model=ScaleStatus)
async def start_scanning(service: ScaleService = Depends(get_scale_service)) -> ScaleStatus:
    return await service.start_scanning()


@router.put("/activity", response_model=ScaleStatus)
async def update_scale_activity(payload: ScaleActivity, service: ScaleService = Depends(get_scale_service)) -> ScaleStatus:
    return service.update_activity(payload)


@router.delete("/measurements/{measurement_id}", status_code=204)
async def delete_measurement(
    measurement_id: int, user_id: str = Query(alias="userId"), confirm: bool = Query(default=False),
    service: ScaleService = Depends(get_scale_service),
) -> None:
    if not confirm:
        raise HTTPException(400, "Подтвердите удаление измерения")
    try:
        await service.delete_measurement(measurement_id, user_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.post("/scan/stop", response_model=ScaleStatus)
async def stop_scanning(service: ScaleService = Depends(get_scale_service)) -> ScaleStatus:
    return await service.stop_scanning()


@router.get("/measurements/latest", response_model=ScaleMeasurement | None)
async def get_last_measurement(
    user_id: str = Query(alias="userId"), service: ScaleService = Depends(get_scale_service),
) -> ScaleMeasurement | None:
    return await service._db(lambda db: service.repository.latest(db, user_id))


@router.get("/measurements", response_model=ScaleHistory)
async def get_weight_history(
    user_id: str = Query(alias="userId"), days: int = Query(default=30, ge=1, le=3650),
    service: ScaleService = Depends(get_scale_service),
) -> ScaleHistory:
    return ScaleHistory(measurements=await service._db(lambda db: service.repository.history(db, user_id, days)))


@router.websocket("/realtime")
async def scale_realtime(websocket: WebSocket) -> None:
    # Same bounded subscription pattern as hardware/realtime, separate from
    # motor telemetry and its command channel. No connection state is implied.
    origin = websocket.headers.get("origin")
    if origin:
        from app.core.config import get_settings

        own_origin = f"{'https' if websocket.url.scheme == 'wss' else 'http'}://{websocket.url.netloc}"
        if origin not in [own_origin, *get_settings().cors_origins]:
            await websocket.close(code=1008)
            return
    service = websocket.app.state.scale_service
    await websocket.accept()
    queue = service.subscribe()

    async def send() -> None:
        while True:
            await websocket.send_json(service.snapshot().model_dump(mode="json", by_alias=True))
            with suppress(TimeoutError):
                await asyncio.wait_for(queue.get(), timeout=2)
            # Coalesce high-frequency advertising updates for touch-screen UI.
            await asyncio.sleep(0.2)

    sender = asyncio.create_task(send())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        service.unsubscribe(queue)