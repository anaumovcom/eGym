import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { PhotoProgressScreen } from '@/screens/photo-progress/photo-progress-screen'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')

  return {
    ...actual,
    useNavigate: () => navigateMock,
    useLocation: () => ({ search: '?source=today&photo=before' }),
    useSearchParams: () => [new URLSearchParams('?source=today&photo=before')],
  }
})

describe('PhotoProgressScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    navigateMock.mockReset()
    useAppStore.setState({
      selectedUserId: 'alexey',
      selectedExerciseSlug: 'machine-pulldown',
      selectedProgramId: 'back-biceps',
      selectedCalendarDayId: '2026-05-14',
      emergencyStopActive: false,
      favoriteExerciseSlugs: ['barbell-floor-press', 'barbell-bench-press', 'machine-pulldown', 'forearm-plank'],
      blacklistedExerciseSlugs: ['smith-machine-bench-press'],
    })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({ source: 'today', photoMode: 'pre-workout' })
  })

  it('keeps exercise setup after skipping pre-workout photo progress', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <PhotoProgressScreen />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: 'Сделать позже' }))

    expect(navigateMock).toHaveBeenCalledWith('/exercise-setup?source=today&photo=before')
    expect(useRuntimeStore.getState().session?.view).toBe('exercise-setup')
  })
})