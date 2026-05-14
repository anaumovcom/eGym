import type { MachineHealth } from '@/entities/machine/model/types'
import type { SystemSettingsData } from '@/entities/stage4/model/types'

export type HardwareDriveTelemetry = {
  side: string
  status: 'connected' | 'warning' | 'error'
  connected: boolean
  positionMm: number
  speedMmPerSec: number
  accelerationMmPerSec2: number
  jerkMmPerSec3: number
  torqueLimitPercent: number
  currentA: number
  temperatureC: number
  errorCode?: string | null
  errorMessage?: string | null
}

export type HardwareMotionTelemetry = {
  moving: boolean
  motionProfile: string
  barPositionMm: number
  leftPositionMm: number
  rightPositionMm: number
  syncDeltaMm: number
  amplitudePercent: number
  tempoLabel: string
  repetitionCount: number
  currentSet: number
  targetSet: number
  targetReps: number
  direction: string
  lowerBoundMm?: number
  upperBoundMm?: number
}

export type HardwareCommandSummary = {
  id: number
  action: string
  status: string
  createdAt: string
  payload: Record<string, unknown>
}

export type HardwareSafetyStatus = {
  state: 'enabled' | 'disabled' | 'emergency_stop'
  label: string
  message: string
  requiresService: boolean
  activeEventId: number | null
}

export type HardwareSnapshot = {
  eventType: string
  emittedAt: string
  machine: MachineHealth
  safety: HardwareSafetyStatus
  emulatorMode: boolean
  serviceMode: boolean
  selectedUserId: string | null
  userSelected: boolean
  drives: HardwareDriveTelemetry[]
  motion: HardwareMotionTelemetry
  calibrationRequired: boolean
  calibrationActual: boolean
  activeCalibrationId: number | null
  commandQueueDepth: number
  lastCommand: HardwareCommandSummary | null
  diagnosticsStatus: string
  lastDiagnosticsAt: string | null
  alerts: string[]
}

export type HardwareCalibration = {
  id: number
  userId: string
  exerciseSlug: string
  lowerPointMm: number
  upperPointMm: number
  zeroPositionMm: number
  movementRangeConfirmed: boolean
  calibrationRequired: boolean
  isActive: boolean
  capturedAt: string
  expiresAt: string | null
  note?: string | null
}

export type HardwareSafetyCheck = {
  id: string
  label: string
  passed: boolean
  severity: 'critical' | 'warning'
  message: string
}

export type HardwareSafetyGateResponse = {
  allowed: boolean
  checks: HardwareSafetyCheck[]
  blockingReasons: string[]
  calibrationId: number | null
}

export type HardwareSafetySettings = Omit<SystemSettingsData['safety'], 'emergencyReady'>

export type HardwareSettingsPayload = SystemSettingsData

export type HardwareDiagnosticRecord = {
  id: number
  category: string
  title: string
  status: string
  severity: string
  description: string
  ranAt: string
  payloadJson: Record<string, unknown>
}

export type HardwareCommandRequest = {
  action: string
  userId?: string | null
  exerciseSlug?: string | null
  calibrationRequired?: boolean
  rangeConfirmed?: boolean
  weightKg?: number
  mode?: string
  targetSet?: number
  targetReps?: number
  direction?: string
  distanceMm?: number
  serviceMode?: boolean
}

export type HardwareCommandResponse = {
  commandId: number
  status: string
  message: string
  snapshot: HardwareSnapshot
  safetyGate: HardwareSafetyGateResponse | null
}

export type HardwareCalibrationPayload = {
  userId: string
  exerciseSlug: string
  lowerPointMm: number
  upperPointMm: number
  zeroPositionMm: number
  movementRangeConfirmed?: boolean
  calibrationRequired?: boolean
  expiresAt?: string | null
  note?: string | null
}

export type HardwareSafetyGatePayload = {
  userId?: string | null
  exerciseSlug: string
  calibrationRequired?: boolean
  rangeConfirmed?: boolean
  weightKg?: number
  mode?: string
}