import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ExerciseSetupScreen } from '@/screens/exercise-setup/exercise-setup-screen'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { HardwareSnapshot } from '@/features/hardware/model/types'

const navigateMock = vi.fn()
const loadCurrentCalibrationMock = vi.fn<(...args: unknown[]) => Promise<null>>()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')

  return {
    ...actual,
    useNavigate: () => navigateMock,
    useLocation: () => ({ search: '?source=catalog&slug=barbell-floor-press&calibration=missing' }),
    useSearchParams: () => [new URLSearchParams('?source=catalog&slug=barbell-floor-press&calibration=missing')],
  }
})

function createSnapshot(barPositionMm: number): HardwareSnapshot {
  return {
    motion: {
      barPositionMm,
    },
    safety: {
      state: 'enabled',
    },
  } as HardwareSnapshot
}

describe('ExerciseSetupScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    navigateMock.mockReset()
    loadCurrentCalibrationMock.mockReset()
    loadCurrentCalibrationMock.mockResolvedValue(null)

    useAppStore.setState({
      selectedUserId: 'alexey',
      selectedExerciseSlug: 'barbell-floor-press',
      selectedProgramId: 'back-biceps',
      selectedCalendarDayId: '2026-05-14',
      emergencyStopActive: false,
      favoriteExerciseSlugs: ['barbell-floor-press', 'barbell-bench-press', 'machine-pulldown', 'forearm-plank'],
      blacklistedExerciseSlugs: ['smith-machine-bench-press'],
    })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({
      source: 'catalog',
      slug: 'barbell-floor-press',
      calibrationState: 'missing',
    })
    useHardwareStore.setState({
      snapshot: createSnapshot(560),
      currentCalibration: null,
      errorMessage: null,
      loadCurrentCalibration: loadCurrentCalibrationMock,
      saveCalibration: vi.fn(),
      deleteCalibration: vi.fn(),
      checkSafetyGate: vi.fn(),
      runCommand: vi.fn(),
      setErrorMessage: vi.fn(),
    })
  })

  it('keeps captured calibration points after rerendering the same exercise without a saved calibration', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <ExerciseSetupScreen />
      </MemoryRouter>,
    )

    await waitFor(() => expect(loadCurrentCalibrationMock).toHaveBeenCalledWith('alexey', 'barbell-floor-press'))

    await user.click(screen.getByRole('button', { name: 'Зафиксировать нижнюю точку' }))
    expect(screen.getByText('56 см')).toBeInTheDocument()

    act(() => {
      useHardwareStore.setState({ snapshot: createSnapshot(760) })
    })

    await user.click(screen.getByRole('button', { name: 'Зафиксировать верхнюю точку' }))
    expect(screen.getByText('76 см')).toBeInTheDocument()

    act(() => {
      useRuntimeStore.getState().updateCalibrationState('missing')
    })

    expect(screen.getByText('56 см')).toBeInTheDocument()
    expect(screen.getByText('76 см')).toBeInTheDocument()
  })
})