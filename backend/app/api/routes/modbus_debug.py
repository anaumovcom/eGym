from fastapi import APIRouter, HTTPException, Query, status

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
    return modbus_service.connect(params)


@router.post("/disconnect", response_model=ModbusConnectionStatusSchema)
def disconnect() -> ModbusConnectionStatusSchema:
    return modbus_service.disconnect()


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
def read_torque_telemetry(slave_id: int = Query(default=1, ge=1, le=247)) -> ModbusTorqueTelemetrySchema:
    return ModbusTorqueTelemetrySchema(slave_id=slave_id, **modbus_service.read_torque_telemetry(slave_id, extended=True))  # type: ignore[arg-type]


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
