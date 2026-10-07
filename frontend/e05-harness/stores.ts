import { create } from 'zustand'
import type { HardwareSnapshot } from '../src/features/hardware/model/types'
import type { RuntimeWorkoutSession } from '../src/entities/runtime/model/types'

// These replace imports, rather than importing/persisting any application store.
export const commands: unknown[] = []
export const useAppStore = create(() => ({ selectedUserId: 'e05-fixture', emergencyStopActive: false }))
export const useHardwareStore = create(() => ({
  snapshot: null as HardwareSnapshot | null, connectionStatus: 'disconnected',
  runCommand: async (command: unknown) => { commands.push(command); throw new Error('Hardware unavailable in E05 harness') },
  setErrorMessage: (_message: string) => {},
}))
export const useRuntimeStore = create(() => ({ session: null as RuntimeWorkoutSession | null }))
export const useStage4Store = create(() => ({ settingsSaved: { soundEnabled: true, voiceHintsEnabled: true, signalVolume: '100%' } }))