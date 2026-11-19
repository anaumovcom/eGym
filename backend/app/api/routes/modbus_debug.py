from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.modbus import (
    DriverDiagnosticsSchema,
    ExchangeLogResponseSchema,
    ModbusCommandRequestSchema,
    ModbusCommandResultSchema,
    ModbusConnectionParamsSchema,
    ModbusConnectionStatusSchema,
    ModbusPositionsSchema,
    ModbusReadRequestSchema,
    ModbusReadResultSchema,
    ModbusTorqueCommandRequestSchema,
    ModbusTorqueInitRequestSchema,
    ModbusTorqueInitResultSchema,
    ModbusTorqueResultSchema,
    ModbusTorqueTelemetrySchema,
    ModbusWriteRequestSchema,
    ModbusWriteResultSchema,
    ParameterProfileSchema,
    ProfileCompareResultSchema,
    ProfileSaveRequestSchema,
    SerialPortInfoSchema,
)
from app.services.hardware_runtime import hardware_runtime
from app.services.modbus_service import modbus_service


def require_modbus_channel() -> None:
    if hardware_runtime.canopen is not None:
        raise HTTPException(409, "Активен CANopen. Канал Modbus доступен после переключения в настройках приводов.")


router = APIRouter(prefix="/modbus", dependencies=[Depends(require_modbus_channel)])


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
    return _change_connection(params)


@router.post("/disconnect", response_model=ModbusConnectionStatusSchema)
def disconnect() -> ModbusConnectionStatusSchema:
    return _change_connection(None)


def _change_connection(params: ModbusConnectionParamsSchema | None) -> ModbusConnectionStatusSchema:
    try:
        with hardware_runtime._lock:
            require_modbus_channel()
            if hardware_runtime.modbus:
                return hardware_runtime.configure_modbus(params)
            return modbus_service.connect(params) if params else modbus_service.disconnect()
    except PermissionError as exc:
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
    return modbus_service.write_register(req)


@router.get("/positions", response_model=ModbusPositionsSchema)
def get_positions() -> ModbusPositionsSchema:
    return modbus_service.get_positions()


@router.post("/positions/zero", response_model=ModbusPositionsSchema)
def zero_positions() -> ModbusPositionsSchema:
    result = modbus_service.capture_zero()
    if result.left.current_pulses is None or result.right.current_pulses is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result.error)
    return result


@router.post("/positions/zero/set", response_model=ModbusPositionsSchema)
def set_zero_positions(left_pulses: int, right_pulses: int) -> ModbusPositionsSchema:
    return modbus_service.set_session_zero(left_pulses, right_pulses)


# ---------------------------------------------------------------------------
# Torque mode
# ---------------------------------------------------------------------------

@router.post("/torque/init", response_model=ModbusTorqueInitResultSchema)
def initialize_torque_mode(req: ModbusTorqueInitRequestSchema | None = None) -> ModbusTorqueInitResultSchema:
    req = req or ModbusTorqueInitRequestSchema()
    if hardware_runtime.modbus:
        errors = hardware_runtime.initialize_modbus_torque(req.torque_limit, req.speed_limit_rpm)
    else:
        modbus_service.end_manual_torque()
        errors = modbus_service.initialize_torque_mode(torque_limit=req.torque_limit, speed_limit_rpm=req.speed_limit_rpm)
    return ModbusTorqueInitResultSchema(success=not errors, errors=errors)


@router.post("/torque/command", response_model=ModbusTorqueResultSchema)
def set_torque_command(req: ModbusTorqueCommandRequestSchema) -> ModbusTorqueResultSchema:
    modbus_service.begin_manual_torque()
    error = modbus_service.set_torque_command(req.slave_id, req.torque_raw)
    return ModbusTorqueResultSchema(success=error is None, error=error)


@router.post("/torque/stop", response_model=ModbusTorqueInitResultSchema)
def stop_torque() -> ModbusTorqueInitResultSchema:
    modbus_service.end_manual_torque()
    errors = modbus_service.stop_all_torque()
    return ModbusTorqueInitResultSchema(success=not errors, errors=errors)


@router.get("/torque/telemetry", response_model=ModbusTorqueTelemetrySchema)
def read_torque_telemetry(slave_id: int = Query(default=1, ge=1, le=247), cached: bool = False) -> ModbusTorqueTelemetrySchema:
    if cached and hardware_runtime.modbus:
        data = modbus_service.cached_telemetry(slave_id, hardware_runtime.envelope.stale_frame_limit_s)
    else:
        # A standalone debug connection has no control loop to populate a cache.
        data = modbus_service.read_torque_telemetry(slave_id, extended=not cached)
    return ModbusTorqueTelemetrySchema.model_validate({"slave_id": slave_id, **data})


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@router.get("/diagnostics", response_model=DriverDiagnosticsSchema)
def get_driver_diagnostics(slave_id: int | None = Query(default=None, ge=1, le=247), cached: bool = False) -> DriverDiagnosticsSchema:
    if cached and not hardware_runtime.modbus:
        selected = slave_id or modbus_service.get_status().slave_id or 1
        modbus_service.read_torque_telemetry(selected, log=False)
    age = hardware_runtime.envelope.stale_frame_limit_s if cached else None
    return modbus_service.get_diagnostics(slave_id, cache_age_s=age)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@router.post("/commands", response_model=ModbusCommandResultSchema)
def execute_command(req: ModbusCommandRequestSchema) -> ModbusCommandResultSchema:
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
