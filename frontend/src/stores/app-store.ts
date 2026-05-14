import { create } from 'zustand'

type AppState = {
  selectedUserId: string | null
  selectedExerciseSlug: string | null
  selectedProgramId: string | null
  selectedCalendarDayId: string | null
  emergencyStopActive: boolean
  favoriteExerciseSlugs: string[]
  blacklistedExerciseSlugs: string[]
  setSelectedUserId: (userId: string) => void
  setSelectedExerciseSlug: (slug: string | null) => void
  setSelectedProgramId: (programId: string | null) => void
  setSelectedCalendarDayId: (dayId: string | null) => void
  setEmergencyStopActive: (value: boolean) => void
  toggleFavoriteExercise: (slug: string) => void
  toggleBlacklistedExercise: (slug: string) => void
}

export const useAppStore = create<AppState>((set) => ({
  selectedUserId: null,
  selectedExerciseSlug: 'machine-pulldown',
  selectedProgramId: 'back-biceps',
  selectedCalendarDayId: '2026-05-14',
  emergencyStopActive: false,
  favoriteExerciseSlugs: ['barbell-floor-press', 'barbell-bench-press', 'machine-pulldown', 'forearm-plank'],
  blacklistedExerciseSlugs: ['smith-machine-bench-press'],
  setSelectedUserId: (selectedUserId) => set({ selectedUserId }),
  setSelectedExerciseSlug: (selectedExerciseSlug) => set({ selectedExerciseSlug }),
  setSelectedProgramId: (selectedProgramId) => set({ selectedProgramId }),
  setSelectedCalendarDayId: (selectedCalendarDayId) => set({ selectedCalendarDayId }),
  setEmergencyStopActive: (emergencyStopActive) => set({ emergencyStopActive }),
  toggleFavoriteExercise: (slug) =>
    set((state) => {
      const exists = state.favoriteExerciseSlugs.includes(slug)

      return {
        favoriteExerciseSlugs: exists ? state.favoriteExerciseSlugs.filter((item) => item !== slug) : [...state.favoriteExerciseSlugs, slug],
        blacklistedExerciseSlugs: exists ? state.blacklistedExerciseSlugs : state.blacklistedExerciseSlugs.filter((item) => item !== slug),
      }
    }),
  toggleBlacklistedExercise: (slug) =>
    set((state) => {
      const exists = state.blacklistedExerciseSlugs.includes(slug)

      return {
        blacklistedExerciseSlugs: exists ? state.blacklistedExerciseSlugs.filter((item) => item !== slug) : [...state.blacklistedExerciseSlugs, slug],
        favoriteExerciseSlugs: exists ? state.favoriteExerciseSlugs : state.favoriteExerciseSlugs.filter((item) => item !== slug),
      }
    }),
}))