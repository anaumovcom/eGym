import { apiGet, apiPost, apiPut } from '@/shared/api/client'

export type RunnableCode = string
export type CalibrationStatus = 'actual' | 'missing' | 'planned'
export type Provenance = 'default' | 'measured' | 'manual' | 'derived'
export type Side = 'left' | 'right'

export type CalibrationSpec = {
  code: string
  group: string
  groupTitle: string
  title: string
  description: string
  steps: string[]
  durationS: number | null
  requires: string[]
  produces: string[]
  inputs?: string[]
  implemented: boolean
  runnable: boolean
  status: CalibrationStatus
  measuredAt: string | null
}

export type ValueInfo = {
  value: number | boolean | null
  ci95: number | null
  provenance: Provenance
  runId: string | null
  measuredAt: string | null
  points: number | null
}

export type ParamKind = 'float' | 'int' | 'bool' | 'sign' | 'weight' | 'counts'
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

export type CalibrationStage = {
  code: string
  title: string
  status: StageStatus
  progress: number
  note: string
  reason: string | null
  result: Record<string, unknown> | null
}

export type CalibrationLog = Record<'t' | 'xL' | 'xR' | 'vL' | 'vR' | 'fL' | 'fR', number[]>

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
  stages: CalibrationStage[]
  changes: CalibrationChange[]
  hasChanges: boolean
  savedVersion: number | null
  log: CalibrationLog
}

export type Precondition = { id: string; label: string; ok: boolean; detail: string | null }

export type CalibrationState = {
  session: CalibrationSessionPayload | null
  preconditions: Precondition[]
  profileVersion: number | null
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

export type StartOptions = { referenceKg?: number }

export type ReportLine = { label: string; value: string; ok: boolean | null }

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
  producedBy: string | null
  restart: boolean
  values?: Record<Side, ValueInfo>
  value?: ValueInfo
}

export type ParamGroup = { id: string; title: string; description: string; items: ParamItem[] }

export type ParametersPayload = { version: number | null; runtimeVersion: number | null; groups: ParamGroup[] }

export type ParameterChangeRequest = { scope: ParamScope; key: string; side?: Side; value: number | boolean }

export const motorApi = {
  calibrations: () => apiGet<CalibrationSpec[]>('/api/motor/calibrations'),
  session: (code: string) => apiGet<CalibrationState>(`/api/motor/calibration/session?code=${encodeURIComponent(code)}`),
  start: (code: RunnableCode, options: StartOptions = {}) =>
    apiPost<CalibrationState>('/api/motor/calibration/start', { code, ...options }),
  keepalive: () => apiPost<{ running: boolean }>('/api/motor/calibration/keepalive', {}),
  abort: () => apiPost<{ session: CalibrationSessionPayload | null }>('/api/motor/calibration/abort', {}),
  accept: () => apiPost<{ version: number; session: CalibrationSessionPayload }>('/api/motor/calibration/accept', {}),
  discard: () => apiPost<{ ok: boolean }>('/api/motor/calibration/discard', {}),
  runs: (limit = 20) => apiGet<CalibrationRunRecord[]>(`/api/motor/calibration/runs?limit=${limit}`),
  parameters: () => apiGet<ParametersPayload>('/api/motor/parameters'),
  updateParameters: (changes: ParameterChangeRequest[], note?: string) =>
    apiPut<ParametersPayload>('/api/motor/parameters', { changes, note }),
}

export function formatValue(value: ValueInfo['value'] | undefined, kind: ParamKind, unit: string): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  if (kind === 'sign') return value >= 0 ? '+1 (прямое)' : '−1 (обратное)'
  const digits = kind === 'int' || kind === 'counts' ? 0 : Math.abs(value) >= 100 ? 1 : Math.abs(value) >= 1 ? 2 : 3
  const text = value.toLocaleString('ru-RU', { maximumFractionDigits: digits, minimumFractionDigits: 0 })
  return unit ? `${text} ${unit}` : text
}

export function kgfHint(value: ValueInfo['value'] | undefined, unit: string): string | null {
  if (unit !== 'Н' || typeof value !== 'number') return null
  return `≈ ${(value / 9.80665).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} кгс`
}

export const PROVENANCE_LABEL: Record<Provenance, string> = {
  measured: 'измерено',
  manual: 'вручную',
  default: 'по умолчанию',
  derived: 'расчёт',
}
