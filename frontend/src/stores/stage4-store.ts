import { create } from 'zustand'
import type { Stage4DevFlags, UserProfileData } from '@/entities/stage4/model/types'
import { defaultStage4DevFlags, getProfileSeed } from '@/mocks/stage4-data'

type Stage4Store = {
  profile: UserProfileData
  profileDraft: UserProfileData | null
  settingsSaved: Record<string, string | boolean>
  settingsDraft: Record<string, string | boolean>
  dev: Stage4DevFlags
  startProfileEdit: () => void
  updateProfileDraft: <K extends keyof UserProfileData>(key: K, value: UserProfileData[K]) => void
  saveProfileDraft: () => void
  cancelProfileEdit: () => void
  setSettingsValue: (key: string, value: string | boolean) => void
  saveSettingsDraft: () => void
  cancelSettingsDraft: () => void
  resetSettingsToDefaults: () => void
  patchDevFlags: (patch: Partial<Stage4DevFlags>) => void
  resetDevFlags: () => void
  syncForUser: (userId: string | null) => void
}

function createDefaultSettingsDraft() {
  return {
    interfaceTheme: 'dark',
    interfaceScale: '100%',
    language: 'Русский',
    units: 'kg / cm',
    brightnessMode: 'Авто',
    autoReturnMinutes: '5 минут',
    soundEnabled: true,
    voiceHintsEnabled: true,
    signalVolume: '70%',
    wifiMode: 'Wi-Fi',
    networkStatus: 'Подключено',
    guestMode: true,
    guestWeightLimit: '30 кг',
    workoutPin: true,
    servicePin: true,
    childLock: true,
    idleLockMinutes: '2 минуты',
    maxLoad: '80 кг',
    maxSpeed: 'Средняя',
    syncLimit: '5 мм',
    desyncAction: 'Остановить движение',
  }
}

export const useStage4Store = create<Stage4Store>((set, get) => ({
  profile: getProfileSeed('alexey'),
  profileDraft: null,
  settingsSaved: createDefaultSettingsDraft(),
  settingsDraft: createDefaultSettingsDraft(),
  dev: defaultStage4DevFlags,
  startProfileEdit: () => set((state) => ({ profileDraft: structuredClone(state.profile) })),
  updateProfileDraft: (key, value) =>
    set((state) =>
      state.profileDraft
        ? {
            profileDraft: {
              ...state.profileDraft,
              [key]: value,
            },
          }
        : state,
    ),
  saveProfileDraft: () =>
    set((state) =>
      state.profileDraft
        ? {
            profile: structuredClone(state.profileDraft),
            profileDraft: null,
          }
        : state,
    ),
  cancelProfileEdit: () => set({ profileDraft: null }),
  setSettingsValue: (key, value) => set((state) => ({ settingsDraft: { ...state.settingsDraft, [key]: value } })),
  saveSettingsDraft: () => set((state) => ({ settingsSaved: { ...state.settingsDraft } })),
  cancelSettingsDraft: () => set((state) => ({ settingsDraft: { ...state.settingsSaved } })),
  resetSettingsToDefaults: () => set({ settingsSaved: createDefaultSettingsDraft(), settingsDraft: createDefaultSettingsDraft() }),
  patchDevFlags: (patch) => set((state) => ({ dev: { ...state.dev, ...patch } })),
  resetDevFlags: () => set({ dev: defaultStage4DevFlags }),
  syncForUser: (userId) => {
    const next = getProfileSeed(userId)
    set({ profile: next, profileDraft: null, settingsDraft: { ...get().settingsSaved } })
  },
}))