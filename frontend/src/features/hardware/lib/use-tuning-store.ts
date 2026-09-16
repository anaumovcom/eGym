import { create } from 'zustand'
import {
  abortProcedure,
  applyPreset,
  controlEmulator,
  controlRecording,
  deletePreset,
  deleteRecording,
  diffPreset,
  fetchEmulator,
  fetchEvents,
  fetchPresets,
  fetchRecording,
  fetchRecordings,
  fetchTuning,
  fetchTuningSchema,
  resetTuning,
  revertTuning,
  savePreset,
  startProcedure,
  updateTuning,
} from '@/features/hardware/api/tuning-api'
import type {
  EmulatorControl,
  EmulatorState,
  RecordingDetail,
  RecordingsList,
  TelemetryBatch,
  TuningEvent,
  TuningPreset,
  TuningPresetDiff,
  TuningSchema,
  TuningValues,
} from '@/features/hardware/model/tuning-types'
import type { HardwareProcedureStatus } from '@/features/hardware/model/types'

export const LIVE_BUFFER_LIMIT = 3000

type Sample = (number | string)[]

type TuningStore = {
  schema: TuningSchema | null
  tuning: TuningValues | null
  pending: Record<string, unknown>
  presets: TuningPreset[]
  presetDiff: TuningPresetDiff | null
  events: TuningEvent[]
  procedure: HardwareProcedureStatus | null
  emulator: EmulatorState | null
  recordings: RecordingsList | null
  openedRecording: RecordingDetail | null
  compareRecording: RecordingDetail | null
  liveFields: string[]
  liveSamples: Sample[]
  livePaused: boolean
  liveControl: Record<string, unknown> | null
  errorMessage: string | null
  busy: boolean
  loadSchema: () => Promise<void>
  loadTuning: () => Promise<void>
  setPending: (key: string, value: unknown) => void
  clearPending: (key?: string) => void
  apply: (mode: 'temporary' | 'persist', actorUserId?: string | null) => Promise<void>
  revert: () => Promise<void>
  reset: (actorUserId?: string | null) => Promise<void>
  loadPresets: () => Promise<void>
  savePreset: (title: string, description: string, actorUserId?: string | null) => Promise<void>
  deletePreset: (id: string) => Promise<void>
  diffPreset: (id: string) => Promise<void>
  applyPreset: (id: string, mode: 'temporary' | 'persist', actorUserId?: string | null) => Promise<void>
  loadEvents: () => Promise<void>
  runProcedure: (name: string, args?: Record<string, unknown>, actorUserId?: string | null) => Promise<void>
  abortProcedure: () => Promise<void>
  setProcedure: (procedure: HardwareProcedureStatus | null) => void
  loadEmulator: () => Promise<void>
  controlEmulator: (payload: EmulatorControl) => Promise<void>
  loadRecordings: () => Promise<void>
  recording: (action: 'start' | 'stop' | 'snapshot', options?: { title?: string; comment?: string; seconds?: number }) => Promise<void>
  openRecording: (id: number, slot?: 'main' | 'compare') => Promise<void>
  closeRecording: (slot?: 'main' | 'compare') => void
  deleteRecording: (id: number) => Promise<void>
  ingestBatch: (batch: TelemetryBatch) => void
  setLivePaused: (paused: boolean) => void
  clearLive: () => void
  setError: (message: string | null) => void
}

function message(error: unknown) {
  return error instanceof Error ? error.message : 'Ошибка запроса к hardware API.'
}

export const useTuningStore = create<TuningStore>((set, get) => ({
  schema: null,
  tuning: null,
  pending: {},
  presets: [],
  presetDiff: null,
  events: [],
  procedure: null,
  emulator: null,
  recordings: null,
  openedRecording: null,
  compareRecording: null,
  liveFields: [],
  liveSamples: [],
  livePaused: false,
  liveControl: null,
  errorMessage: null,
  busy: false,
  loadSchema: async () => {
    try {
      set({ schema: await fetchTuningSchema() })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  loadTuning: async () => {
    try {
      set({ tuning: await fetchTuning(), errorMessage: null })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  setPending: (key, value) => set((state) => ({ pending: { ...state.pending, [key]: value } })),
  clearPending: (key) =>
    set((state) => {
      if (!key) return { pending: {} }
      const next = { ...state.pending }
      delete next[key]
      return { pending: next }
    }),
  apply: async (mode, actorUserId) => {
    const pending = get().pending
    if (Object.keys(pending).length === 0) return
    set({ busy: true })
    try {
      await updateTuning(pending, mode, actorUserId)
      set({ pending: {}, errorMessage: null })
      await get().loadTuning()
    } catch (error) {
      set({ errorMessage: message(error) })
    } finally {
      set({ busy: false })
    }
  },
  revert: async () => {
    try {
      set({ tuning: await revertTuning(), pending: {}, errorMessage: null })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  reset: async (actorUserId) => {
    try {
      set({ tuning: await resetTuning(actorUserId), pending: {}, errorMessage: null })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  loadPresets: async () => {
    try {
      set({ presets: await fetchPresets() })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  savePreset: async (title, description, actorUserId) => {
    try {
      await savePreset(title, description, undefined, actorUserId)
      await get().loadPresets()
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  deletePreset: async (id) => {
    try {
      await deletePreset(id)
      await get().loadPresets()
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  diffPreset: async (id) => {
    try {
      set({ presetDiff: await diffPreset(id) })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  applyPreset: async (id, mode, actorUserId) => {
    set({ busy: true })
    try {
      await applyPreset(id, mode, actorUserId)
      set({ errorMessage: null, presetDiff: null })
      await get().loadTuning()
    } catch (error) {
      set({ errorMessage: message(error) })
    } finally {
      set({ busy: false })
    }
  },
  loadEvents: async () => {
    try {
      set({ events: await fetchEvents(120) })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  runProcedure: async (name, args = {}, actorUserId) => {
    try {
      set({ procedure: await startProcedure(name, args, actorUserId), errorMessage: null })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  abortProcedure: async () => {
    try {
      set({ procedure: await abortProcedure() })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  setProcedure: (procedure) => set({ procedure }),
  loadEmulator: async () => {
    try {
      set({ emulator: await fetchEmulator() })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  controlEmulator: async (payload) => {
    try {
      set({ emulator: await controlEmulator(payload), errorMessage: null })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  loadRecordings: async () => {
    try {
      set({ recordings: await fetchRecordings() })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  recording: async (action, options = {}) => {
    try {
      await controlRecording(action, options)
      await get().loadRecordings()
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  openRecording: async (id, slot = 'main') => {
    try {
      const detail = await fetchRecording(id)
      set(slot === 'main' ? { openedRecording: detail } : { compareRecording: detail })
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  closeRecording: (slot = 'main') => set(slot === 'main' ? { openedRecording: null } : { compareRecording: null }),
  deleteRecording: async (id) => {
    try {
      await deleteRecording(id)
      set((state) => ({
        openedRecording: state.openedRecording?.id === id ? null : state.openedRecording,
        compareRecording: state.compareRecording?.id === id ? null : state.compareRecording,
      }))
      await get().loadRecordings()
    } catch (error) {
      set({ errorMessage: message(error) })
    }
  },
  ingestBatch: (batch) =>
    set((state) => {
      const merged = state.livePaused ? state.liveSamples : [...state.liveSamples, ...batch.samples].slice(-LIVE_BUFFER_LIMIT)
      const eventsMap = new Map<string, TuningEvent>()
      for (const event of [...state.events, ...batch.events]) {
        eventsMap.set(`${event.time}-${event.kind}-${event.message}`, event)
      }
      const events = [...eventsMap.values()].sort((a, b) => a.time - b.time).slice(-400)
      return {
        liveFields: batch.fields,
        liveSamples: merged,
        events,
        liveControl: batch.control ?? state.liveControl,
      }
    }),
  setLivePaused: (livePaused) => set({ livePaused }),
  clearLive: () => set({ liveSamples: [] }),
  setError: (errorMessage) => set({ errorMessage }),
}))
