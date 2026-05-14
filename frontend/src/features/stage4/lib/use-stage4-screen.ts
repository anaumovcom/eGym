import { useEffect } from 'react'
import { useAppStore } from '@/stores/app-store'
import { useStage4Store } from '@/stores/stage4-store'

function getUserName(userId: string | null) {
  if (userId === 'elena') {
    return 'Елена'
  }

  if (userId === 'guest') {
    return 'Гость'
  }

  return 'Алексей'
}

export function useStage4Screen() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const blacklistedExerciseSlugs = useAppStore((state) => state.blacklistedExerciseSlugs)
  const toggleBlacklistedExercise = useAppStore((state) => state.toggleBlacklistedExercise)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)

  const profile = useStage4Store((state) => state.profile)
  const profileDraft = useStage4Store((state) => state.profileDraft)
  const settingsDraft = useStage4Store((state) => state.settingsDraft)
  const settingsSaved = useStage4Store((state) => state.settingsSaved)
  const dev = useStage4Store((state) => state.dev)
  const syncForUser = useStage4Store((state) => state.syncForUser)
  const patchDevFlags = useStage4Store((state) => state.patchDevFlags)
  const resetDevFlags = useStage4Store((state) => state.resetDevFlags)

  useEffect(() => {
    syncForUser(selectedUserId)
  }, [selectedUserId, syncForUser])

  return {
    selectedUserId,
    userName: getUserName(selectedUserId),
    blacklistedExerciseSlugs,
    toggleBlacklistedExercise,
    emergencyStopActive,
    setEmergencyStopActive,
    profile,
    profileDraft,
    settingsDraft,
    settingsSaved,
    dev,
    patchDevFlags,
    resetDevFlags,
  }
}