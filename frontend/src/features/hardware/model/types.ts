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
  controlMode?: string
  partialReps?: number
  loadTargetKg?: number
  loadEffectiveKg?: number
  loadMode?: string
  userForceKg?: number
  velocityMmPerSec?: number
  startPoint?: string
  fixedPositionMm?: number | null
}

export type HardwareControlState = {
  mode: string
  label: string
  message: string
  positionMm: number
  velocityMmPerSec: number
  accelerationMmPerSec2: number
  userForceKg: number
  userForceLeftKg: number
  userForceRightKg: number
  loadTargetKg: number
  loadEffectiveKg: number
  components: Record<string, number>
  repetitionCount: number
  partialReps: number
  concentricS: number
  eccentricS: number
  tempoLabel: string
  repQuality: number
  targetReached: boolean
  syncDeltaMm: number
  syncStatus: 'norm' | 'ok' | 'warning' | 'critical'
  asymmetryPercent: number
  gripDetected: boolean
  released: boolean
  stallS: number
  spotterActive: boolean
  failureDetected: boolean
  stillMs: number
  postStatus: string
  postResults: { id: string; label: string; passed: boolean; detail: string; severity: string }[]
  homed: boolean
  positionKnown: boolean
  homingPhase: string
  physicalBottomMm: number | null
  physicalTopMm: number | null
  workingBottomMm: number | null
  workingTopMm: number | null
  fullTravelMm: number | null
  heartbeatOk: boolean
  commOk: boolean
  powerOk: boolean
  brakeEngaged: boolean
  fixedHoldTestPassed: boolean
  fixedDriftMm: number
  isometricElapsedS: number
  moveTargetMm: number | null
  moveProgressPercent: number
  faultCode: string | null
  tickLatencyMs: number
  missedTicks: number
  counters: { travelMmTotal: number; cyclesTotal: number; loadedSecondsTotal: number }
  config: { lowerMm: number; upperMm: number; startPoint: string; loadKg: number; loadMode: string; targetReps: number; fixedPositionMm: number | null }
  brakes: Record<string, boolean>
  limitSwitches: Record<string, boolean>
  adapter: string
  temporaryParameters: number
}

export type HardwareProcedureStatus = {
  name: string | null
  label: string
  status: 'idle' | 'running' | 'done' | 'failed'
  step: string
  progressTicks: number
  result: Record<string, unknown> | null
  startedAt: string | null
  finishedAt: string | null
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

export type HardwarePanelStatus = {
  enabled: boolean
  connected: boolean
  ready: boolean
  handshakeComplete: boolean
  fresh: boolean
  rxAgeMs: number | null
  port: string | null
  firmwareVersion: string | null
  protocolVersion: number | null
  lastSeenAt: string | null
  buttons: Record<string, boolean>
  sensors: Record<string, boolean>
  bottomPair: boolean
  topPair: boolean
  faultCode: string | null
  diagnostics: Record<string, Record<string, unknown>>
  position: Record<string, unknown>
  machineState: string | null
  inputHealthy: boolean
  stopLatched: boolean
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
  control?: HardwareControlState
  procedure?: HardwareProcedureStatus
  calibrationRequired: boolean
  calibrationActual: boolean
  activeCalibrationId: number | null
  commandQueueDepth: number
  lastCommand: HardwareCommandSummary | null
  diagnosticsStatus: string
  lastDiagnosticsAt: string | null
  alerts: string[]
  panel: HardwarePanelStatus
}

export type HardwareCalibration = {
  id: number
  userId: string
  exerciseSlug: string
  setupType: 'bar_range' | 'fixed_position'
  lowerPointMm: number | null
  upperPointMm: number | null
  fixedPositionMm: number | null
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
  jogId?: string
  serviceMode?: boolean
  loadMode?: string
  startPoint?: string
  positionMm?: number
  lowerMm?: number
  upperMm?: number
  which?: 'lower' | 'upper' | 'fixed'
  waitForGrip?: boolean
  warmup?: boolean
  guest?: boolean
  asymmetricAllowed?: boolean
  repCountSource?: string
  bodyWeightKg?: number
  isometricDurationS?: number
  autoUser?: boolean
}

export type HardwareCommandResponse = {
  commandId: number
  status: string
  message: string
  snapshot: HardwareSnapshot
  safetyGate: HardwareSafetyGateResponse | null
  capturedPositionMm?: number | null
}

export type HardwareCalibrationPayload = {
  userId: string
  exerciseSlug: string
  setupType: 'bar_range' | 'fixed_position'
  lowerPointMm?: number | null
  upperPointMm?: number | null
  fixedPositionMm?: number | null
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