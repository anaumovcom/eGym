import { apiDelete, apiGet, apiPost } from '@/shared/api/client'
import type {
  DriverDiagnostics,
  ExchangeLogResponse,
  ModbusCommandResult,
  ModbusConnectionParams,
  ModbusConnectionStatus,
  ModbusReadResult,
  ModbusPositions,
  PositionExercise,
  PositionCalibration,
  PositionMotionStatus,
  ModbusReadiness,
  ModbusWriteResult,
  ParameterProfile,
  ProfileCompareResult,
  SerialPortInfo,
} from '@/features/modbus/model/types'

function toSnake(params: ModbusConnectionParams) {
  return {
    port: params.port,
    baud_rate: params.baudRate,
    data_bits: params.dataBits,
    parity: params.parity,
    stop_bits: params.stopBits,
    slave_id: params.slaveId,
    right_slave_id: params.rightSlaveId,
    timeout_ms: params.timeoutMs,
    left_direction: params.leftDirection,
    right_direction: params.rightDirection,
  }
}

export async function fetchModbusPorts(): Promise<SerialPortInfo[]> {
  const raw = await apiGet<{ device: string; description: string; hardware_id: string | null }[]>('/api/modbus/ports')
  return raw.map((p) => ({ device: p.device, description: p.description, hardwareId: p.hardware_id }))
}

export async function fetchModbusStatus(): Promise<ModbusConnectionStatus> {
  const raw = await apiGet<Record<string, unknown>>('/api/modbus/status')
  return mapStatus(raw)
}

function mapPositions(raw: Record<string, unknown>): ModbusPositions {
  const readiness = (raw.readiness ?? {}) as Record<string, unknown>
  const ready = (key: string) => readiness[key] === true
  const side = (value: Record<string, unknown>) => ({
    slaveId: value.slave_id as number,
    currentPulses: (value.current_pulses as number | null) ?? null,
    zeroPulses: (value.zero_pulses as number | null) ?? null,
    positionMm: (value.position_mm as number | null) ?? null,
  })
  return {
    connected: raw.connected as boolean,
    simulationMode: (raw.simulation_mode as boolean) ?? false,
    zeroed: raw.zeroed as boolean,
    zeroGeneration: (raw.zero_generation as number) ?? 0,
    readiness: {
      communicationReady: ready('communication_ready'), encoderReady: ready('encoder_ready'),
      torqueControlReady: ready('torque_control_ready'), motionSafetyReady: ready('motion_safety_ready'),
      degradedManualMode: ready('degraded_manual_mode'), allowEncoderRead: ready('allow_encoder_read'),
      allowZeroOffset: ready('allow_zero_offset'), allowStatusRead: ready('allow_status_read'),
      allowManualTorqueTest: ready('allow_manual_torque_test'), allowAutomaticMotion: ready('allow_automatic_motion'),
      allowPositionAutoMove: ready('allow_position_auto_move'), allowProgramWorkout: ready('allow_program_workout'),
      allowHoming: ready('allow_homing'), noBrake: ready('no_brake'), noLimitSwitches: ready('no_limit_switches'),
      noHardwareStop: ready('no_hardware_stop'), noHardwareSync: ready('no_hardware_sync'),
      warning: (readiness.warning as string) ?? '',
    } satisfies ModbusReadiness,
    left: side(raw.left as Record<string, unknown>),
    right: side(raw.right as Record<string, unknown>),
    skewMm: (raw.skew_mm as number | null) ?? null,
    error: (raw.error as string | null) ?? null,
  }
}

export async function fetchModbusPositions(): Promise<ModbusPositions> {
  return mapPositions(await apiGet<Record<string, unknown>>('/api/modbus/positions'))
}

export async function zeroModbusPositions(): Promise<ModbusPositions> {
  return mapPositions(await apiPost<Record<string, unknown>>('/api/modbus/positions/zero', {}))
}

function mapPositionStatus(raw: Record<string, unknown>): PositionMotionStatus {
  return {
    state: raw.state as PositionMotionStatus['state'],
    targetType: raw.target_type as PositionMotionStatus['targetType'],
    targetMm: raw.target_mm as number | null,
    torqueLimit: raw.torque_limit as number | null,
    speedRpm: raw.speed_rpm as number | null,
    positions: mapPositions(raw.positions as Record<string, unknown>),
    servoOn: raw.servo_on as PositionMotionStatus['servoOn'],
    posLoad: raw.pos_load as PositionMotionStatus['posLoad'],
    drives: raw.drives as PositionMotionStatus['drives'],
    warning: raw.warning as string | null,
    error: raw.error as string | null,
    simulationOnly: raw.simulation_only === true,
  }
}

export async function fetchPositionStatus(): Promise<PositionMotionStatus> {
  return mapPositionStatus(await apiGet<Record<string, unknown>>('/api/modbus/position/status'))
}

export async function startPositionExercise(exercise: PositionExercise): Promise<PositionMotionStatus> {
  return mapPositionStatus(await apiPost<Record<string, unknown>>('/api/modbus/position/exercise', {
    exercise_key: exercise.exerciseKey ?? null,
    target_type: exercise.targetType, lower_boundary_mm: exercise.lowerBoundaryMm,
    fixed_position_mm: exercise.fixedPositionMm, torque_limit: exercise.torqueLimit,
    speed_rpm: exercise.speedRpm, min_mm: exercise.minMm, max_mm: exercise.maxMm,
  }))
}

function mapCalibration(raw: Record<string, unknown>): PositionCalibration {
  return {
    exerciseKey: raw.exercise_key as string,
    zeroGeneration: raw.zero_generation as number,
    lowerMm: raw.lower_mm as number | null,
    upperMm: raw.upper_mm as number | null,
    fixedMm: raw.fixed_mm as number | null,
  }
}

export async function fetchPositionCalibration(exerciseKey: string): Promise<PositionCalibration | null> {
  const raw = await apiGet<Record<string, unknown> | null>(`/api/modbus/position/calibration?exercise_key=${encodeURIComponent(exerciseKey)}`)
  return raw ? mapCalibration(raw) : null
}

export async function capturePositionCalibration(exerciseKey: string, point: 'lower' | 'upper' | 'fixed'): Promise<PositionCalibration> {
  return mapCalibration(await apiPost<Record<string, unknown>>('/api/modbus/position/calibration/capture', { exercise_key: exerciseKey, point }))
}

export async function enterPositionWeightless(torqueLimit: number, noMotionThreshold: number, speedRpm: number): Promise<PositionMotionStatus> {
  return mapPositionStatus(await apiPost<Record<string, unknown>>('/api/modbus/position/weightless', {
    torque_limit: torqueLimit, no_motion_threshold: noMotionThreshold, speed_rpm: speedRpm,
  }))
}

export async function holdPosition(): Promise<PositionMotionStatus> {
  return mapPositionStatus(await apiPost<Record<string, unknown>>('/api/modbus/position/hold', {}))
}

export async function changePositionLimit(value: number): Promise<PositionMotionStatus> {
  return mapPositionStatus(await apiPost<Record<string, unknown>>(`/api/modbus/position/limit?torque_limit=${value}`, {}))
}

export async function stopRaisePosition(): Promise<PositionMotionStatus> {
  return mapPositionStatus(await apiPost<Record<string, unknown>>('/api/modbus/position/stop-raise', {}))
}

export async function connectModbus(params: ModbusConnectionParams): Promise<ModbusConnectionStatus> {
  const raw = await apiPost<Record<string, unknown>>('/api/modbus/connect', toSnake(params))
  return mapStatus(raw)
}

export async function disconnectModbus(): Promise<ModbusConnectionStatus> {
  const raw = await apiPost<Record<string, unknown>>('/api/modbus/disconnect', {})
  return mapStatus(raw)
}

export async function pingModbus(slaveId?: number): Promise<ModbusReadResult> {
  return readModbusRegisters(0, 1, slaveId)
}

export async function readModbusRegisters(address: number, count = 1, slaveId?: number): Promise<ModbusReadResult> {
  const raw = await apiPost<Record<string, unknown>>('/api/modbus/read', {
    address,
    count,
    ...(slaveId != null ? { slave_id: slaveId } : {}),
  })
  return mapReadResult(raw)
}

export async function writeModbusRegister(address: number, value: number, slaveId?: number): Promise<ModbusWriteResult> {
  const raw = await apiPost<Record<string, unknown>>('/api/modbus/write', {
    address,
    value,
    ...(slaveId != null ? { slave_id: slaveId } : {}),
  })
  return mapWriteResult(raw)
}

export async function fetchModbusDiagnostics(slaveId?: number): Promise<DriverDiagnostics> {
  const raw = await apiGet<Record<string, unknown>>(`/api/modbus/diagnostics${slaveId != null ? `?slave_id=${slaveId}` : ''}`)
  return mapDiagnostics(raw)
}

export async function runModbusCommand(
  command: string,
  confirmed: boolean,
  params?: Record<string, number>,
  slaveId?: number,
): Promise<ModbusCommandResult> {
  return apiPost<ModbusCommandResult>('/api/modbus/commands', {
    command,
    confirmed,
    params: params ?? null,
    ...(slaveId != null ? { slave_id: slaveId } : {}),
  })
}

export async function fetchModbusLog(
  limit = 200,
  direction?: string,
  action?: string,
): Promise<ExchangeLogResponse> {
  const search = new URLSearchParams({ limit: String(limit) })
  if (direction) search.set('direction', direction)
  if (action) search.set('action', action)
  const raw = await apiGet<{ entries: unknown[]; total: number }>(`/api/modbus/log?${search.toString()}`)
  return {
    entries: (raw.entries as Record<string, unknown>[]).map(mapLogEntry),
    total: raw.total,
  }
}

export async function clearModbusLog(): Promise<void> {
  await apiDelete('/api/modbus/log')
}

export async function fetchModbusProfiles(): Promise<ParameterProfile[]> {
  const raw = await apiGet<Record<string, unknown>[]>('/api/modbus/profiles')
  return raw.map(mapProfile)
}

export async function saveModbusProfile(name: string, comment = '', addresses?: number[]): Promise<ParameterProfile> {
  const raw = await apiPost<Record<string, unknown>>('/api/modbus/profiles', {
    name,
    comment,
    ...(addresses ? { addresses } : {}),
  })
  return mapProfile(raw)
}

export async function compareModbusProfile(profileId: string): Promise<ProfileCompareResult> {
  const raw = await apiGet<Record<string, unknown>>(`/api/modbus/profiles/${profileId}/compare`)
  return {
    differences: (raw.differences as Record<string, unknown>[]).map((d) => ({
      address: d.address as number,
      addressHex: d.address_hex as string,
      name: d.name as string,
      driverValue: d.driver_value as number,
      profileValue: d.profile_value as number,
    })),
    matching: raw.matching as number,
    differing: raw.differing as number,
  }
}

// ---------------------------------------------------------------------------
// Mappers
// ---------------------------------------------------------------------------

function mapStatus(r: Record<string, unknown>): ModbusConnectionStatus {
  return {
    connected: r.connected as boolean,
    port: (r.port as string | null) ?? null,
    baudRate: (r.baud_rate as number | null) ?? null,
    parity: (r.parity as string | null) ?? null,
    slaveId: (r.slave_id as number | null) ?? null,
    rightSlaveId: (r.right_slave_id as number | null) ?? null,
    leftDirection: (r.left_direction as -1 | 1) ?? 1,
    rightDirection: (r.right_direction as -1 | 1) ?? 1,
    lastSuccessAt: (r.last_success_at as string | null) ?? null,
    okCount: (r.ok_count as number) ?? 0,
    errorCount: (r.error_count as number) ?? 0,
    errorMessage: (r.error_message as string | null) ?? null,
    simulationMode: (r.simulation_mode as boolean) ?? false,
  }
}

function mapReadResult(r: Record<string, unknown>): ModbusReadResult {
  const regs = ((r.registers as Record<string, unknown>[]) ?? []).map((reg) => ({
    address: reg.address as number,
    addressHex: reg.address_hex as string,
    value: reg.value as number,
    rawBytes: (reg.raw_bytes as string | null) ?? null,
    error: (reg.error as string | null) ?? null,
    readAt: (reg.read_at as string | null) ?? null,
  }))
  return {
    success: r.success as boolean,
    registers: regs,
    elapsedMs: (r.elapsed_ms as number | null) ?? null,
    error: (r.error as string | null) ?? null,
    rawRequest: (r.raw_request as string | null) ?? null,
    rawResponse: (r.raw_response as string | null) ?? null,
  }
}

function mapWriteResult(r: Record<string, unknown>): ModbusWriteResult {
  return {
    success: r.success as boolean,
    address: r.address as number,
    value: r.value as number,
    elapsedMs: (r.elapsed_ms as number | null) ?? null,
    error: (r.error as string | null) ?? null,
    rawRequest: (r.raw_request as string | null) ?? null,
    rawResponse: (r.raw_response as string | null) ?? null,
  }
}

function mapDiagnostics(r: Record<string, unknown>): DriverDiagnostics {
  return {
    responding: r.responding as boolean,
    slaveId: (r.slave_id as number | null) ?? null,
    baudRateCode: (r.baud_rate_code as number | null) ?? null,
    controlMode: (r.control_mode as number | null) ?? null,
    extendedMode: (r.extended_mode as number | null) ?? null,
    alarmCode: (r.alarm_code as number | null) ?? null,
    hasAlarm: (r.has_alarm as boolean) ?? false,
    motionSafe: (r.motion_safe as boolean) ?? false,
    statusSummary: (r.status_summary as string) ?? '',
    checkedAt: (r.checked_at as string | null) ?? null,
  }
}

function mapLogEntry(r: Record<string, unknown>) {
  return {
    id: r.id as number,
    ts: r.ts as string,
    direction: r.direction as 'TX' | 'RX' | 'INFO' | 'ERROR',
    slaveId: (r.slave_id as number | null) ?? null,
    action: r.action as string,
    parameter: (r.parameter as string | null) ?? null,
    address: (r.address as number | null) ?? null,
    value: (r.value as number | null) ?? null,
    result: (r.result as string | null) ?? null,
    rawRequest: (r.raw_request as string | null) ?? null,
    rawResponse: (r.raw_response as string | null) ?? null,
    error: (r.error as string | null) ?? null,
    elapsedMs: (r.elapsed_ms as number | null) ?? null,
  }
}

function mapProfile(r: Record<string, unknown>): ParameterProfile {
  return {
    id: (r.id as string | null) ?? null,
    name: r.name as string,
    driverModel: (r.driver_model as string) ?? 'Lichuan A6',
    slaveId: (r.slave_id as number) ?? 1,
    baudRate: (r.baud_rate as number) ?? 38400,
    parameters: ((r.parameters as Record<string, unknown>[]) ?? []).map((p) => ({
      address: p.address as number,
      name: p.name as string,
      value: p.value as number,
    })),
    comment: (r.comment as string) ?? '',
    createdAt: (r.created_at as string | null) ?? null,
  }
}
