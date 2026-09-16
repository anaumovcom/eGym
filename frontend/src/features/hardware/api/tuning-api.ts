import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/api/client'
import type {
  EmulatorControl,
  EmulatorState,
  RecordingDetail,
  RecordingsList,
  RecordingSummary,
  TuningEvent,
  TuningPreset,
  TuningPresetDiff,
  TuningSchema,
  TuningUpdateResult,
  TuningValues,
} from '@/features/hardware/model/tuning-types'
import type { HardwareProcedureStatus } from '@/features/hardware/model/types'

export function fetchTuningSchema() {
  return apiGet<TuningSchema>('/api/hardware/tuning/schema')
}

export function fetchTuning() {
  return apiGet<TuningValues>('/api/hardware/tuning')
}

export function updateTuning(values: Record<string, unknown>, apply: 'temporary' | 'persist', actorUserId?: string | null) {
  return apiPut<TuningUpdateResult>('/api/hardware/tuning', { values, apply, actorUserId })
}

export function revertTuning() {
  return apiPost<TuningValues>('/api/hardware/tuning/revert', {})
}

export function resetTuning(actorUserId?: string | null) {
  const search = actorUserId ? `?actorUserId=${encodeURIComponent(actorUserId)}` : ''
  return apiPost<TuningValues>(`/api/hardware/tuning/reset${search}`, {})
}

export function fetchPresets() {
  return apiGet<TuningPreset[]>('/api/hardware/tuning/presets')
}

export function savePreset(title: string, description: string, values?: Record<string, unknown>, actorUserId?: string | null) {
  return apiPost<TuningPreset>('/api/hardware/tuning/presets', { title, description, values, actorUserId })
}

export function deletePreset(presetId: string) {
  return apiDelete(`/api/hardware/tuning/presets/${encodeURIComponent(presetId)}`)
}

export function diffPreset(presetId: string) {
  return apiGet<TuningPresetDiff>(`/api/hardware/tuning/presets/${encodeURIComponent(presetId)}/diff`)
}

export function applyPreset(presetId: string, apply: 'temporary' | 'persist', actorUserId?: string | null) {
  const search = new URLSearchParams({ apply })
  if (actorUserId) search.set('actorUserId', actorUserId)
  return apiPost<TuningUpdateResult>(`/api/hardware/tuning/presets/${encodeURIComponent(presetId)}/apply?${search}`, {})
}

export function startProcedure(name: string, args: Record<string, unknown> = {}, actorUserId?: string | null) {
  return apiPost<HardwareProcedureStatus>(`/api/hardware/tuning/procedures/${encodeURIComponent(name)}`, { args, actorUserId })
}

export function abortProcedure() {
  return apiPost<HardwareProcedureStatus>('/api/hardware/tuning/procedures/abort', {})
}

export function fetchEvents(limit = 100) {
  return apiGet<TuningEvent[]>(`/api/hardware/tuning/events?limit=${limit}`)
}

export function fetchEmulator() {
  return apiGet<EmulatorState>('/api/hardware/tuning/emulator')
}

export function controlEmulator(payload: EmulatorControl) {
  return apiPost<EmulatorState>('/api/hardware/tuning/emulator', payload)
}

export function fetchRecordings() {
  return apiGet<RecordingsList>('/api/hardware/tuning/recordings')
}

export function controlRecording(action: 'start' | 'stop' | 'snapshot', options: { title?: string; comment?: string; seconds?: number } = {}) {
  return apiPost<RecordingSummary & { recording?: boolean }>('/api/hardware/tuning/recordings', { action, ...options })
}

export function fetchRecording(recordingId: number) {
  return apiGet<RecordingDetail>(`/api/hardware/tuning/recordings/${recordingId}`)
}

export function deleteRecording(recordingId: number) {
  return apiDelete(`/api/hardware/tuning/recordings/${recordingId}`)
}
