from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.modbus import (
    DriverDiagnosticsSchema,
    ExchangeLogResponseSchema,
    ModbusCommandRequestSchema,
    ModbusCommandResultSchema,
    ModbusConnectionParamsSchema,
    ModbusConnectionStatusSchema,
    ModbusPositionsSchema,
    PositionExerciseSchema,
    PositionMotionStatusSchema,
    PositionCalibrationCaptureSchema,
    PositionCalibrationSchema,
    WeightlessPositionSchema,
    ModbusReadRequestSchema,
    ModbusReadResultSchema,
    ModbusWriteRequestSchema,
    ModbusWriteResultSchema,
    ParameterProfileSchema,
    ProfileCompareResultSchema,
    ProfileSaveRequestSchema,
    SerialPortInfoSchema,
    SoftwareStopResultSchema,
)
from app.services.modbus_service import modbus_service

router = APIRouter(prefix="/modbus")


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------

@router.get("/ports", response_model=list[SerialPortInfoSchema])
def list_ports() -> list[SerialPortInfoSchema]:
    """List available serial ports."""
    return modbus_service.list_ports()


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@router.get("/status", response_model=ModbusConnectionStatusSchema)
def get_connection_status() -> ModbusConnectionStatusSchema:
    return modbus_service.get_status()


@router.post("/connect", response_model=ModbusConnectionStatusSchema)
def connect(params: ModbusConnectionParamsSchema) -> ModbusConnectionStatusSchema:
    result = modbus_service.connect(params)
    return result


@router.post("/disconnect", response_model=ModbusConnectionStatusSchema)
def disconnect() -> ModbusConnectionStatusSchema:
    try:
        return modbus_service.disconnect()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/ping", response_model=ModbusReadResultSchema)
def ping() -> ModbusReadResultSchema:
    result = modbus_service.ping()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result.error)
    return result


# ---------------------------------------------------------------------------
# Read / Write
# ---------------------------------------------------------------------------

@router.post("/read", response_model=ModbusReadResultSchema)
def read_registers(req: ModbusReadRequestSchema) -> ModbusReadResultSchema:
    return modbus_service.read_registers(req)


@router.post("/write", response_model=ModbusWriteResultSchema)
def write_register(req: ModbusWriteRequestSchema) -> ModbusWriteResultSchema:
    if modbus_service.motion_active and req.address in {
        0x002, 0x090, 0x091, 0x05E, 0x05F, 0x168, 0x169, 0x190, 0x201,
    }:
        return ModbusWriteResultSchema(success=False, address=req.address, value=req.value,
                                       error="Изменение управляющих регистров во время Position mode запрещено")
    # The generic parameter editor must not bypass the manual torque gate on
    # real hardware; servo-off is not yet verified by this application.
    if 0x12C <= req.address <= 0x14B and req.value != 0 and not modbus_service.get_status().simulation_mode:
        return ModbusWriteResultSchema(
            success=False, address=req.address, value=req.value,
            error="Ручной тест момента недоступен: Servo-OFF реального привода не подтверждён (E-CTRL-UNAVAILABLE)",
        )
    return modbus_service.write_register(req)


@router.get("/positions", response_model=ModbusPositionsSchema)
def get_positions() -> ModbusPositionsSchema:
    return modbus_service.get_positions()


@router.post("/positions/zero", response_model=ModbusPositionsSchema)
def zero_positions() -> ModbusPositionsSchema:
    try:
        result = modbus_service.capture_zero()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result.left.current_pulses is None or result.right.current_pulses is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result.error)
    return result


@router.post("/software-stop", response_model=SoftwareStopResultSchema)
def software_stop() -> SoftwareStopResultSchema:
    """Legacy endpoint must not release a loaded vertical bar."""
    raise HTTPException(status_code=409, detail="Servo-OFF/нулевой момент запрещены как штатный STOP. Используйте position/stop-raise (только симуляция) или аппаратный E-STOP.")


@router.post("/position/exercise", response_model=PositionMotionStatusSchema)
def start_position_exercise(request: PositionExerciseSchema) -> PositionMotionStatusSchema:
    try:
        return modbus_service.start_position_exercise(request)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/position/limit", response_model=PositionMotionStatusSchema)
def update_position_limit(torque_limit: int = Query(ge=1, le=3000)) -> PositionMotionStatusSchema:
    try:
        return modbus_service.update_position_limit(torque_limit)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/position/stop-raise", response_model=PositionMotionStatusSchema)
def position_stop_raise() -> PositionMotionStatusSchema:
    try:
        return modbus_service.stop_raise()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/position/status", response_model=PositionMotionStatusSchema)
def position_status() -> PositionMotionStatusSchema:
    return modbus_service.position_motion_status()


@router.get("/position/calibration", response_model=PositionCalibrationSchema | None)
def position_calibration(exercise_key: str = Query(min_length=1)) -> PositionCalibrationSchema | None:
    return modbus_service.get_position_calibration(exercise_key)


@router.post("/position/calibration/capture", response_model=PositionCalibrationSchema)
def capture_position_calibration(req: PositionCalibrationCaptureSchema) -> PositionCalibrationSchema:
    try:
        return modbus_service.capture_position_point(req)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/position/weightless", response_model=PositionMotionStatusSchema)
def weightless_position(req: WeightlessPositionSchema) -> PositionMotionStatusSchema:
    try:
        return modbus_service.enter_weightless(req)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/position/hold", response_model=PositionMotionStatusSchema)
def hold_position() -> PositionMotionStatusSchema:
    try:
        return modbus_service.hold_position()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@router.get("/diagnostics", response_model=DriverDiagnosticsSchema)
def get_driver_diagnostics(slave_id: int | None = Query(default=None, ge=1, le=247)) -> DriverDiagnosticsSchema:
    return modbus_service.get_diagnostics(slave_id)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@router.post("/commands", response_model=ModbusCommandResultSchema)
def execute_command(req: ModbusCommandRequestSchema) -> ModbusCommandResultSchema:
    if modbus_service.motion_active and req.command in {
        "servo_off", "emergency_stop", "jog_start", "homing", "pos_load",
    }:
        return ModbusCommandResultSchema(success=False, command=req.command,
                                         error="Для Position mode используйте управляемый STOP; сервисные DI-команды заблокированы")
    result = modbus_service.execute_command(req)
    if not result.success and result.error == "Confirmation required for this operation":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.error)
    return result


# ---------------------------------------------------------------------------
# Exchange log
# ---------------------------------------------------------------------------

@router.get("/log", response_model=ExchangeLogResponseSchema)
def get_exchange_log(
    limit: int = Query(default=200, ge=1, le=500),
    direction: str | None = Query(default=None),
    action: str | None = Query(default=None),
) -> ExchangeLogResponseSchema:
    return modbus_service.get_log(limit=limit, direction=direction, action=action)


@router.delete("/log", status_code=status.HTTP_204_NO_CONTENT)
def clear_exchange_log() -> None:
    modbus_service.clear_log()


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

@router.get("/profiles", response_model=list[ParameterProfileSchema])
def list_profiles() -> list[ParameterProfileSchema]:
    return modbus_service.list_profiles()


@router.post("/profiles", response_model=ParameterProfileSchema)
def save_profile(req: ProfileSaveRequestSchema) -> ParameterProfileSchema:
    return modbus_service.save_profile(req)


@router.get("/profiles/{profile_id}/compare", response_model=ProfileCompareResultSchema)
def compare_profile(profile_id: str) -> ProfileCompareResultSchema:
    return modbus_service.compare_profile(profile_id)
