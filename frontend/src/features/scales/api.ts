import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/api/client'
import type { QueryClient } from '@tanstack/react-query'

export type ScaleMeasurement = {
  id: number
  userId: string
  weightKg: number
  timestamp: string
  stable: true
  deviceId: string
  impedanceOhm: number | null
}

export type ScaleStatus = {
  enabled: boolean
  paused: boolean
  pauseReason: string | null
  bluetoothAvailable: boolean
  scanning: boolean
  scanningMode: 'passive' | 'active' | null
  measuring: boolean
  deviceId: string | null
  lastSeen: string | null
  lastMeasurement: ScaleMeasurement | null
  devices: Array<{ deviceId: string; name: string; rssi: number | null; lastSeen: string }>
  error: string | null
  warning: string | null
}

export type ScaleSettings = Pick<ScaleStatus, 'enabled' | 'deviceId'>
export type ScaleActivityPhase = 'idle' | 'setup' | 'exercise' | 'rest'
export type ScaleActivity = { clientId: string; sequence: number; phase: ScaleActivityPhase }
export type ScalePeriod = 7 | 30 | 90
export const scaleKeys = {
  status: ['scales', 'status'] as const,
  history: (userId: string) => ['scales', 'history', userId] as const,
  latest: (userId: string) => ['scales', 'latest', userId] as const,
}

export const scalesApi = {
  status: () => apiGet<ScaleStatus>('/api/scales/status'),
  activity: (activity: ScaleActivity) => apiPut<ScaleStatus>('/api/scales/activity', activity),
  history: (userId: string, days: ScalePeriod | 3650) => apiGet<{ measurements: ScaleMeasurement[] }>(`/api/scales/measurements?userId=${encodeURIComponent(userId)}&days=${days}`),
  latest: (userId: string) => apiGet<ScaleMeasurement | null>(`/api/scales/measurements/latest?userId=${encodeURIComponent(userId)}`),
  scan: (enabled: boolean) => apiPost<unknown>(`/api/scales/scan/${enabled ? 'start' : 'stop'}`, {}),
  settings: (settings: ScaleSettings) => apiPut<unknown>('/api/scales/settings', settings),
  deleteMeasurement: (id: number, userId: string) => apiDelete(`/api/scales/measurements/${id}?userId=${encodeURIComponent(userId)}&confirm=true`),
}

export async function invalidateScaleOwner(client: QueryClient, userId: string) {
  await Promise.all([scaleKeys.history(userId), scaleKeys.latest(userId), ['progress-screen', userId], ['user-profile-screen', userId], ['body-measurements', userId]].map(queryKey => client.invalidateQueries({ queryKey })))
}