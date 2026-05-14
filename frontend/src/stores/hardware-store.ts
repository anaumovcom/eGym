import { create } from 'zustand'
import { ApiError } from '@/shared/api/client'
import {
  checkHardwareSafetyGate,
  deleteHardwareCalibration,
  fetchCurrentCalibration,
  fetchHardwareCalibrations,
  fetchHardwareSettings,
  fetchHardwareSnapshot,
  runHardwareCommand,
  saveHardwareCalibration,
  updateHardwareSafetySettings,
} from '@/features/hardware/api/hardware-api'
import type {
  HardwareCalibration,
  HardwareCalibrationPayload,
  HardwareCommandRequest,
  HardwareCommandResponse,
  HardwareSafetyGatePayload,
  HardwareSafetyGateResponse,
  HardwareSafetySettings,
  HardwareSettingsPayload,
  HardwareSnapshot,
} from '@/features/hardware/model/types'

type HardwareConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error'

type HardwareStore = {
  snapshot: HardwareSnapshot | null
  settings: HardwareSettingsPayload | null
  currentCalibration: HardwareCalibration | null
  calibrations: HardwareCalibration[]
  connectionStatus: HardwareConnectionStatus
  errorMessage: string | null
  setSnapshot: (snapshot: HardwareSnapshot) => void
  setConnectionStatus: (status: HardwareConnectionStatus) => void
  setErrorMessage: (message: string | null) => void
  loadSnapshot: (userId?: string | null) => Promise<HardwareSnapshot>
  loadSettings: (userId?: string | null) => Promise<HardwareSettingsPayload>
  loadCurrentCalibration: (userId: string, exerciseSlug: string) => Promise<HardwareCalibration | null>
  loadCalibrations: (userId: string) => Promise<HardwareCalibration[]>
  saveCalibration: (payload: HardwareCalibrationPayload) => Promise<HardwareCalibration>
  deleteCalibration: (calibrationId: number, actorUserId?: string | null) => Promise<void>
  updateSafetySettings: (payload: HardwareSafetySettings, userId?: string | null) => Promise<HardwareSafetySettings>
  checkSafetyGate: (payload: HardwareSafetyGatePayload) => Promise<HardwareSafetyGateResponse>
  runCommand: (payload: HardwareCommandRequest) => Promise<HardwareCommandResponse>
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message
  }

  return 'Не удалось связаться с hardware API.'
}

export const useHardwareStore = create<HardwareStore>((set, get) => ({
  snapshot: null,
  settings: null,
  currentCalibration: null,
  calibrations: [],
  connectionStatus: 'idle',
  errorMessage: null,
  setSnapshot: (snapshot) => set({ snapshot, errorMessage: null }),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setErrorMessage: (errorMessage) => set({ errorMessage }),
  loadSnapshot: async (userId) => {
    try {
      const snapshot = await fetchHardwareSnapshot(userId)
      set({ snapshot, errorMessage: null })
      return snapshot
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
  loadSettings: async (userId) => {
    try {
      const settings = await fetchHardwareSettings(userId)
      set({ settings, errorMessage: null })
      return settings
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
  loadCurrentCalibration: async (userId, exerciseSlug) => {
    try {
      const calibration = await fetchCurrentCalibration(userId, exerciseSlug)
      set({ currentCalibration: calibration, errorMessage: null })
      return calibration
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        set({ currentCalibration: null, errorMessage: null })
        return null
      }
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
  loadCalibrations: async (userId) => {
    try {
      const response = await fetchHardwareCalibrations(userId)
      set({ calibrations: response.items, errorMessage: null })
      return response.items
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
  saveCalibration: async (payload) => {
    try {
      const calibration = await saveHardwareCalibration(payload)
      const calibrations = get().calibrations.filter((item) => item.id !== calibration.id)
      set({
        currentCalibration: calibration,
        calibrations: [calibration, ...calibrations],
        errorMessage: null,
      })
      return calibration
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
  deleteCalibration: async (calibrationId, actorUserId) => {
    try {
      await deleteHardwareCalibration(calibrationId, actorUserId)
      set({
        currentCalibration: get().currentCalibration?.id === calibrationId ? null : get().currentCalibration,
        calibrations: get().calibrations.filter((item) => item.id !== calibrationId),
        errorMessage: null,
      })
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
  updateSafetySettings: async (payload, userId) => {
    try {
      const safety = await updateHardwareSafetySettings(payload, userId)
      const currentSettings = get().settings
      if (currentSettings) {
        set({ settings: { ...currentSettings, safety: { ...currentSettings.safety, ...safety } }, errorMessage: null })
      } else {
        set({ errorMessage: null })
      }
      return safety
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
  checkSafetyGate: async (payload) => {
    try {
      const response = await checkHardwareSafetyGate(payload)
      set({ errorMessage: response.allowed ? null : response.blockingReasons[0] ?? null })
      return response
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
  runCommand: async (payload) => {
    try {
      const response = await runHardwareCommand(payload)
      set({ snapshot: response.snapshot, errorMessage: null })
      return response
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      set({ errorMessage })
      throw error
    }
  },
}))