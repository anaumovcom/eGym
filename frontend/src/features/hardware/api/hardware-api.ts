import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/api/client'
import type {
  HardwareCalibration,
  HardwareCalibrationPayload,
  HardwareCommandRequest,
  HardwareCommandResponse,
  HardwareDiagnosticRecord,
  HardwareSafetyGatePayload,
  HardwareSafetyGateResponse,
  HardwareSafetySettings,
  HardwareSettingsPayload,
  HardwareSnapshot,
} from '@/features/hardware/model/types'

export async function fetchHardwareSnapshot(userId?: string | null) {
  const search = userId ? `?userId=${encodeURIComponent(userId)}` : ''
  return apiGet<HardwareSnapshot>(`/api/hardware/status${search}`)
}

export async function fetchHardwareSettings(userId?: string | null) {
  const search = userId ? `?userId=${encodeURIComponent(userId)}` : ''
  return apiGet<HardwareSettingsPayload>(`/api/hardware/settings${search}`)
}

export async function updateHardwareSafetySettings(payload: HardwareSafetySettings, userId?: string | null) {
  const search = userId ? `?userId=${encodeURIComponent(userId)}` : ''
  return apiPut<HardwareSafetySettings>(`/api/hardware/settings/safety${search}`, payload)
}

export async function fetchHardwareDiagnostics() {
  return apiGet<HardwareDiagnosticRecord[]>('/api/hardware/diagnostics')
}

export async function checkHardwareSafetyGate(payload: HardwareSafetyGatePayload) {
  return apiPost<HardwareSafetyGateResponse>('/api/hardware/safety-gate/check', payload)
}

export async function runHardwareCommand(payload: HardwareCommandRequest) {
  return apiPost<HardwareCommandResponse>('/api/hardware/commands', payload)
}

export async function fetchHardwareCalibrations(userId: string) {
  return apiGet<{ items: HardwareCalibration[] }>(`/api/hardware/calibrations?userId=${encodeURIComponent(userId)}`)
}

export async function fetchCurrentCalibration(userId: string, exerciseSlug: string) {
  const search = `?userId=${encodeURIComponent(userId)}&exerciseSlug=${encodeURIComponent(exerciseSlug)}`
  return apiGet<HardwareCalibration>(`/api/hardware/calibrations/current${search}`)
}

export async function saveHardwareCalibration(payload: HardwareCalibrationPayload) {
  return apiPost<HardwareCalibration>('/api/hardware/calibrations', payload)
}

export async function deleteHardwareCalibration(calibrationId: number, actorUserId?: string | null) {
  const search = new URLSearchParams({ confirm: 'true' })
  if (actorUserId) {
    search.set('actorUserId', actorUserId)
  }
  await apiDelete(`/api/hardware/calibrations/${calibrationId}?${search.toString()}`)
}