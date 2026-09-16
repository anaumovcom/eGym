export type TuningParameterType = 'number' | 'integer' | 'boolean' | 'enum'

export type TuningParameterSpec = {
  key: string
  group: string
  label: string
  description: string
  type: TuningParameterType
  default: unknown
  unit: string
  min: number | null
  max: number | null
  hardMin: number | null
  hardMax: number | null
  step: number | null
  options: string[]
  requiresRestart: boolean
  safetyCritical: boolean
}

export type TuningGroup = { id: string; label: string; description: string }

export type TuningSchema = {
  groups: TuningGroup[]
  parameters: TuningParameterSpec[]
  procedures: {
    measurements: { id: string; label: string }[]
    scenarios: { id: string; label: string }[]
  }
}

export type TuningValues = {
  values: Record<string, unknown>
  persisted: Record<string, unknown>
  temporary: Record<string, unknown>
  serviceMode: boolean
  adapter: string
}

export type TuningUpdateResult = {
  changed: Record<string, { from: unknown; to: unknown }>
  values: Record<string, unknown>
  temporary: Record<string, unknown>
}

export type TuningPreset = {
  id: string
  title: string
  description: string
  createdAt: string
  values: Record<string, unknown>
  builtin: boolean
}

export type TuningPresetDiff = {
  presetId: string
  differences: { key: string; current: unknown; preset: unknown; label: string }[]
}

export type TelemetryBatch = {
  eventType: 'telemetry.batch'
  fields: string[]
  samples: (number | string)[][]
  events: TuningEvent[]
  control?: Record<string, unknown>
}

export type TuningEvent = {
  time: number
  kind: string
  message: string
  [key: string]: unknown
}

export type EmulatorState = {
  active: boolean
  physics?: Record<string, number>
  userForceKg?: number
  userBias?: number
  scenario?: { name: string; strengthKg: number; periodS: number; repsDone: number; tiltBias: number }
  faults?: { powerLoss: boolean; physicalEstop: boolean; commLost: string[]; encoderDrift: Record<string, number>; overheat: string[] }
  events?: { time: number; kind: string; message: string }[]
}

export type EmulatorControl = {
  action: 'user_force' | 'scenario' | 'fault' | 'clear_faults' | 'physics'
  forceKg?: number
  bias?: number
  name?: string
  strengthKg?: number
  periodS?: number
  lowerMm?: number
  upperMm?: number
  failAfterReps?: number
  tiltBias?: number
  jerkKg?: number
  fault?: string
  side?: 'left' | 'right'
  value?: number
  physics?: Record<string, number>
}

export type RecordingSummary = {
  id: number
  title: string
  comment: string
  createdAt: string
  kind: 'manual' | 'incident'
  sampleCount: number
  durationS: number
}

export type RecordingDetail = RecordingSummary & {
  fields: string[]
  parameters: Record<string, unknown>
  samples: (number | string)[][]
  events: TuningEvent[]
}

export type RecordingsList = {
  recording: boolean
  recordings: RecordingSummary[]
  incidents: RecordingSummary[]
}
