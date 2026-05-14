import { beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from '@/stores/app-store'

const defaultState = {
  selectedUserId: null,
  selectedExerciseSlug: 'machine-pulldown',
  selectedProgramId: 'back-biceps',
  selectedCalendarDayId: '2026-05-14',
  emergencyStopActive: false,
  favoriteExerciseSlugs: ['barbell-floor-press', 'barbell-bench-press', 'machine-pulldown', 'forearm-plank'],
  blacklistedExerciseSlugs: ['smith-machine-bench-press'],
}

describe('app store persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    useAppStore.setState(defaultState)
  })

  it('persists user context but does not persist emergency stop flag', () => {
    useAppStore.getState().setSelectedUserId('alexey')
    useAppStore.getState().setSelectedProgramId('back-biceps')
    useAppStore.getState().setEmergencyStopActive(true)

    const payload = JSON.parse(localStorage.getItem('egym-app-store') ?? '{}')

    expect(payload.state.selectedUserId).toBe('alexey')
    expect(payload.state.selectedProgramId).toBe('back-biceps')
    expect(payload.state.emergencyStopActive).toBeUndefined()
  })
})