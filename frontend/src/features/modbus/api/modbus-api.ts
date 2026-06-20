import { apiDelete, apiGet, apiPost } from '@/shared/api/client'
import type {
  DriverDiagnostics,
  ExchangeLogResponse,
  ModbusCommandResult,
  ModbusConnectionParams,
  ModbusConnectionStatus,
  ModbusReadResult,
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
    timeout_ms: params.timeoutMs,
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

export async function connectModbus(params: ModbusConnectionParams): Promise<ModbusConnectionStatus> {
  const raw = await apiPost<Record<string, unknown>>('/api/modbus/connect', toSnake(params))
  return mapStatus(raw)
}

export async function disconnectModbus(): Promise<ModbusConnectionStatus> {
  const raw = await apiPost<Record<string, unknown>>('/api/modbus/disconnect', {})
  return mapStatus(raw)
}

export async function pingModbus(): Promise<ModbusReadResult> {
  const raw = await apiPost<Record<string, unknown>>('/api/modbus/ping', {})
  return mapReadResult(raw)
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

export async function fetchModbusDiagnostics(): Promise<DriverDiagnostics> {
  const raw = await apiGet<Record<string, unknown>>('/api/modbus/diagnostics')
  return mapDiagnostics(raw)
}

export async function runModbusCommand(
  command: string,
  confirmed: boolean,
  params?: Record<string, number>,
): Promise<ModbusCommandResult> {
  return apiPost<ModbusCommandResult>('/api/modbus/commands', {
    command,
    confirmed,
    params: params ?? null,
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
