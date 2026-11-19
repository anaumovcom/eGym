import { apiGet, apiPost, apiPut } from '@/shared/api/client'

export type RunnableCode = string
export type CalibrationStatus = 'actual' | 'stale' | 'failed' | 'missing' | 'planned'
export type CalibrationPriority = 'critical' | 'important' | 'refinement'
export type Provenance = 'default' | 'measured' | 'manual' | 'derived'
export type Side = 'left' | 'right'

export type CalibrationSpec = {
  code: string
  group: string
  groupTitle: string
  title: string
  priority: CalibrationPriority
  priorityReason: string
  description: string
  steps: string[]
  durationS: number | null
  requires: string[]
  produces: string[]
  uses?: string[]
  inputs?: string[]
  prepare?: string | null
  order?: number
  stages?: string[]
  middleZone?: 'preferred' | 'required' | null
  participation?: 'automatic' | 'tape' | 'weight' | 'hands'
  implemented: boolean
  runnable: boolean
  status: CalibrationStatus
  staleReason?: string | null
  measuredAt: string | null
  lastCheck?: { finishedAt: string; ok: boolean } | null
}

export type ValueInfo = {
  value: number | boolean | null
  ci95: number | null
  provenance: Provenance
  runId: string | null
  measuredAt: string | null
  points: number | null
  rows?: [number, number][] | null
}

export type ParamKind = 'float' | 'int' | 'bool' | 'sign' | 'weight' | 'counts' | 'table'
export type ParamScope = 'side' | 'machine' | 'tunables' | 'envelope'

export type CalibrationChange = {
  scope: ParamScope
  key: string
  side: Side | null
  label: string
  unit: string
  kind: ParamKind
  old: ValueInfo | null
  new: ValueInfo | null
  changed: boolean
}

export type StageStatus = 'pending' | 'running' | 'done' | 'aborted' | 'failed'

export type FrictionTrack = {
  heightsMm: number[]
  heightBasis?: 'bar'
  sides: Record<Side, (number | null)[]>
  summary?: Partial<Record<Side, {
    peakMm: number | null; peakN: number | null; weightResidualN: number; weightWithinTolerance: boolean
    typicalN?: number; thresholdN?: number
  }>>
  binMm?: number
  speedMmS?: number
  coverageOk?: Record<Side, boolean>
  zeroToleranceMm?: number
  directionalN?: Record<Side, Record<'up' | 'down', (number | null)[]>>
  reference?: Record<Side, { zeroCounts: number | null; mmPerPulse: number; nPerRaw: number; sign: number }>
}
export type FrictionSource = 'modbus' | 'canopen' | 'twin' | 'unknown'
export type FrictionCoverage = { heightsMm: number[]; sides: Record<Side, (0 | 1 | 2 | 3)[]> }
export type FrictionScan = { id: string; code: string; status: string; startedAt: string; track: FrictionTrack }
export type FrictionArchive = { source: FrictionSource; hasMore: boolean; items: FrictionScan[] }
export type PlotStage = 'S7' | 'D2' | 'F3' | 'X3' | 'M5' | 'G4'
export type MeasurementArchive = { source: FrictionSource; priority?: CalibrationPriority; priorityReason?: string; hasMore: boolean; items: {
  id: string; code: string; status: string; startedAt: string; stageStatus?: string | null
  reason?: string | null; workingZone?: WorkingWindow | null; result: Record<string, unknown>
}[] }

export type CalibrationStage = {
  frames?: number
  verification?: boolean
  code: string
  title: string
  status: StageStatus
  progress: number
  note: string
  reason: string | null
  result: Record<string, unknown> | null
  workingZone?: WorkingWindow | null
}

export type CalibrationLog = Record<'t' | 'xL' | 'xR' | 'vL' | 'vR' | 'fL' | 'fR', number[]> & {
  cycleMs?: (number | null)[]; segment?: number[]; loadKg?: number[]; targetKg?: number[]
  skewMm?: (number | null)[]; holdTargetMm?: (number | null)[]
}
export type FaultResponse = 'ok' | 'warning' | 'skew' | 'telemetry' | 'drive'
export type FaultCase = {
  id: string; title: string; description: string; expected: FaultResponse; actual: FaultResponse; matches: boolean; detail: string
  frames: { ms: number; rawMm: number | null; deltaMm: number | null; state: 'ok' | 'warning' | 'stop' }[]
}
export type FaultRehearsalResult = { version: number; warningMm: number; criticalMm: number; cycleMs: number; cases: FaultCase[] }
export type WorkingWindow = { lowMm: number; highMm: number }

export type CalibrationPrompt = {
  text: string
  kind: 'confirm' | 'input' | 'action'
  label: string | null
  unit: string | null
  min: number | null
  max: number | null
}

export type CalibrationSessionPayload = {
  id: string
  code: RunnableCode
  title: string
  status: 'running' | 'done' | 'aborted' | 'failed'
  reason: string | null
  startedAt: string
  finishedAt: string | null
  elapsedS: number
  progress: number
  currentStage: string | null
  note: string
  deadManHeld: boolean
  frameAgeS?: number | null
  staleAfterS?: number
  prompt?: CalibrationPrompt | null
  stages: CalibrationStage[]
  changes: CalibrationChange[]
  hasChanges: boolean
  savedVersion: number | null
  log: CalibrationLog
  stageLog?: CalibrationLog | null
  frictionCoverage?: FrictionCoverage | null
  workingZone?: WorkingWindow | null
}

export type Precondition = { id: string; label: string; ok: boolean; detail: string | null }
export type CalibrationWorkingZone = 'middle'

export type CalibrationState = {
  session: CalibrationSessionPayload | null
  preconditions: Precondition[]
  profileVersion: number | null
  workingZone?: WorkingWindow | null
}

export type CalibrationRunRecord = {
  id: string
  code: string
  title: string | null
  status: string
  startedAt: string
  finishedAt: string | null
  reason: string | null
  savedVersion: number | null
  changes: CalibrationChange[]
}

export type StartOptions = { referenceKg?: number; workingZone?: CalibrationWorkingZone }

export type CalibrationRecord = { id: string; code?: string; title?: string | null; status?: string; startedAt?: string; savedVersion?: number | null; changes?: CalibrationChange[]
  stages: CalibrationStage[]; log: CalibrationLog | null; stageLogs?: Record<string, CalibrationLog>; workingZone: WorkingWindow | null; baseVersion: number | null; adapter: string | null }
export type SpeedDirection = {
  profileLimitMmS: number
  insideLimits: boolean
  measuredMinMmS: number | null
  measuredMaxMmS: number | null
  insideMeasuredRange: boolean
  brakingMm: number | null
  availableMm: number | null
}
export type SpeedStudy = {
  profileVersion: number | null
  targetMmS: number
  targetRpm: number
  driveLimitRpm: number
  alarmRpm: number
  centerMm: number | null
  cycleMs: number | null
  travelPerCycleMm: number | null
  adapter: 'modbus' | 'canopen' | 'twin'
  m5Source: 'modbus' | 'canopen' | 'twin' | null
  m5RunId: string | null
  replay: {
    strokeMm: number
    cycleMs: number
    cycleSource: Provenance
    periodS: number
    rmsMmS: number
    turnDelayMs: number | null
    points: [number, number, number][]
  } | null
  directions: { up: SpeedDirection; down: SpeedDirection }
}

export type ReportLine = { label: string; value: string; ok: boolean | null; comparison?: { value: number; limit: number } }

export type ParamItem = {
  scope: ParamScope
  key: string
  label: string
  description: string
  unit: string
  kind: ParamKind
  editable: boolean
  min: number | null
  max: number | null
  step: number | null
  producedBy: string[]
  restart: boolean
  values?: Record<Side, ValueInfo>
  effective?: ValueInfo & { label: string; key?: string; procedure: string | null }
  value?: ValueInfo
}

export type ParamGroup = { id: string; title: string; description: string; items: ParamItem[] }

export type ParametersPayload = { version: number | null; runtimeVersion: number | null; groups: ParamGroup[]
  audit?: { definitions: number; values: number; unset: number; issues: { label: string; side: Side | null; detail: string }[]
    pending?: { key: string; label: string; values: number; procedure: string }[] }
}

export type ObservationSource = 'twin' | 'modbus' | 'canopen'
export type SetObservation = {
  id: string; startedAt: string; source: ObservationSource; profileVersion: number; exerciseSlug: string | null; exerciseName: string | null
  status: 'recording' | 'completed' | 'interrupted'; reason: string | null
  setNumber: number; targetReps: number; mode: string; loadDirection: 'up' | 'down'; initialKg: number
  lowerMm: number; upperMm: number; fixedMm: number | null; startPoint: 'upper' | 'lower'
  elapsedS: number; workS: number; validFrames: number; invalidFrames: number; segments: number; maxGapMs: number
  fullReps: number; partialReps: number; minHeightMm: number | null; maxHeightMm: number | null
  maxSkewMm: number | null; skewHeightMm: number | null; upMmS: [number, number] | null; downMmS: [number, number] | null
  fixedPeakErrorMm?: [number, number] | null
  approach?: { fromMm: number; targetMm: number; seconds: number; peakMmS: number; errorsMm: [number, number]; status: 'moving' | 'hold' | 'interrupted' } | null
  skewWarningMm: number; ascentLimitMmS: number; descentLimitMmS: number
  encoderWindowS?: number; encoderWindows?: number; encoderUpMmS?: [number, number] | null; encoderDownMmS?: [number, number] | null
}

export type ParameterChangeRequest = { scope: ParamScope; key: string; side?: Side; value: number | boolean }

export type ParameterPreview = {
  baseVersion: number
  changes: { scope: ParamScope; key: string; side: Side | null; label: string; unit: string; kind: ParamKind; before: ValueInfo; after: ValueInfo; effective: ParamItem['effective'] | null; restart: boolean }[]
  statusChanges: { code: string; title: string; before: CalibrationStatus; after: CalibrationStatus }[]
}

export const motorKeys = {
  catalog: ['motor', 'calibrations'] as const,
  parameters: ['motor', 'parameters'] as const,
  runs: ['motor', 'runs'] as const,
  sessions: ['motor', 'session'] as const,
  session: (code: string, zone?: CalibrationWorkingZone) => zone
    ? ['motor', 'session', code, zone] as const : ['motor', 'session', code] as const,
}

export const motorApi = {
  faultRehearsal: () => apiGet<FaultRehearsalResult>('/api/motor/calibration/fault-rehearsal'),
  observations: (source: ObservationSource, offset = 0) =>
    apiGet<{ items: SetObservation[]; hasMore: boolean }>(`/api/motor/exercise-observations?source=${source}&offset=${offset}&limit=20`),
  observation: (id: string) => apiGet<SetObservation & { trace: CalibrationLog }>(`/api/motor/exercise-observations/${encodeURIComponent(id)}`),
  calibrations: () => apiGet<CalibrationSpec[]>('/api/motor/calibrations'),
  session: (code: string, workingZone?: CalibrationWorkingZone) =>
    apiGet<CalibrationState>(`/api/motor/calibration/session?code=${encodeURIComponent(code)}${workingZone ? `&workingZone=${workingZone}` : ''}`),
  start: (code: RunnableCode, options: StartOptions = {}) =>
    apiPost<CalibrationState>('/api/motor/calibration/start', { code, ...options }),
  keepalive: (sessionId: string, intervalMs: number) => apiPost<{ running: boolean }>('/api/motor/calibration/keepalive', { sessionId, intervalMs }),
  abort: (sessionId: string) => apiPost<{ session: CalibrationSessionPayload | null }>('/api/motor/calibration/abort', { sessionId }),
  reply: (sessionId: string, promptText: string, value: number | null) =>
    apiPost<{ session: CalibrationSessionPayload | null }>('/api/motor/calibration/reply', { sessionId, value, promptText }),
  accept: (sessionId: string, fitTravelLimit = false) => apiPost<{ version: number; session: CalibrationSessionPayload }>('/api/motor/calibration/accept', { sessionId, ...(fitTravelLimit ? { fitTravelLimit } : {}) }),
  discard: (sessionId: string) => apiPost<{ ok: boolean }>('/api/motor/calibration/discard', { sessionId }),
  runs: (limit = 20, code?: string) => apiGet<CalibrationRunRecord[]>(`/api/motor/calibration/runs?limit=${limit}${code ? '&code=' + encodeURIComponent(code) : ''}`),
  record: (id: string) => apiGet<CalibrationRecord>(`/api/motor/calibration/runs/${encodeURIComponent(id)}`),
  frictionTracks: (offset: number, source?: FrictionSource) =>
    apiGet<FrictionArchive>(`/api/motor/calibration/friction-tracks?offset=${offset}${source ? '&source=' + source : ''}`),
  measurementPlots: (stage: PlotStage, offset: number, source?: FrictionSource) =>
    apiGet<MeasurementArchive>(`/api/motor/calibration/measurement-plots?stage=${stage}&offset=${offset}${source ? '&source=' + source : ''}`),
  speedStudy: (target: number) => apiGet<SpeedStudy>(`/api/motor/calibration/speed-study?targetMmS=${target}`),
  parameters: () => apiGet<ParametersPayload>('/api/motor/parameters'),
  previewParameters: (changes: ParameterChangeRequest[], baseVersion: number) =>
    apiPost<ParameterPreview>('/api/motor/parameters/preview', { changes, baseVersion }),
  updateParameters: (changes: ParameterChangeRequest[], note?: string, baseVersion?: number) =>
    apiPut<ParametersPayload>('/api/motor/parameters', { changes, note, baseVersion }),
  reset: (scope: ResetScope) => apiPost<ParametersPayload>('/api/motor/profile/reset', { scope }),
}

export type ResetScope = 'calibrations' | 'parameters' | 'all'

export function formatValue(value: ValueInfo['value'] | undefined, kind: ParamKind, unit: string): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  if (kind === 'sign') return value >= 0 ? '+1 (прямое)' : '−1 (обратное)'
  const digits = kind === 'int' || kind === 'counts' ? 0 : Math.abs(value) >= 100 ? 1 : Math.abs(value) >= 1 ? 2 : 3
  const text = value.toLocaleString('ru-RU', digits > 0 && Math.abs(value) > 0 && Math.abs(value) < 0.01
    ? { maximumSignificantDigits: 4 } : { maximumFractionDigits: digits, minimumFractionDigits: 0 })
  return unit ? `${text} ${unit}` : text
}

export function kgfHint(value: ValueInfo['value'] | undefined, unit: string): string | null {
  if (unit !== 'Н' || typeof value !== 'number') return null
  return `≈ ${(value / 9.80665).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} кгс`
}

export function comparisonValue(value: ValueInfo['value'] | undefined, other: ValueInfo['value'] | undefined, kind: ParamKind, unit: string) {
  const text = formatValue(value, kind, unit)
  if (typeof value !== 'number' || typeof other !== 'number' || value === other || text !== formatValue(other, kind, unit)) return text
  const exact = value.toLocaleString('ru-RU', { maximumSignificantDigits: 17 })
  return unit ? `${exact} ${unit}` : exact
}

export const PROVENANCE_LABEL: Record<Provenance, string> = {
  measured: 'измерено',
  manual: 'вручную',
  default: 'по умолчанию',
  derived: 'расчёт',
}
