import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ExerciseSetupScreen } from '@/screens/exercise-setup/exercise-setup-screen'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { HardwareSnapshot } from '@/features/hardware/model/types'

const navigateMock = vi.fn()
const loadCurrentCalibrationMock = vi.fn<(...args: unknown[]) => Promise<null>>()
const buildBackendBuilderRuntimeSessionMock = vi.fn<(...args: unknown[]) => Promise<RuntimeWorkoutSession>>()
let currentSearch = '?source=catalog&slug=barbell-floor-press&calibration=missing'

vi.mock('@/features/runtime/lib/backend-builder-session', () => ({
  buildBackendBuilderRuntimeSession: (...args: unknown[]) => buildBackendBuilderRuntimeSessionMock(...args),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')

  return {
    ...actual,
    useNavigate: () => navigateMock,
    useLocation: () => ({ search: currentSearch }),
    useSearchParams: () => [new URLSearchParams(currentSearch)],
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

function renderScreen() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/exercise-setup${currentSearch}`]}>
        <ExerciseSetupScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ExerciseSetupScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    currentSearch = '?source=catalog&slug=barbell-floor-press&calibration=missing'
    navigateMock.mockReset()
    loadCurrentCalibrationMock.mockReset()
    loadCurrentCalibrationMock.mockResolvedValue(null)
    buildBackendBuilderRuntimeSessionMock.mockReset()

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

    renderScreen()

    await waitFor(() => expect(loadCurrentCalibrationMock).toHaveBeenCalledWith('alexey', 'barbell-floor-press'))

    await user.click(screen.getByRole('button', { name: 'Зафиксировать нижнюю точку' }))
    expect(screen.getAllByText('56 см').length).toBeGreaterThan(0)

    act(() => {
      useHardwareStore.setState({ snapshot: createSnapshot(760) })
    })

    await user.click(screen.getByRole('button', { name: 'Зафиксировать верхнюю точку' }))
    expect(screen.getAllByText('76 см').length).toBeGreaterThan(0)

    act(() => {
      useRuntimeStore.getState().updateCalibrationState('missing')
    })

    expect(screen.getAllByText('56 см').length).toBeGreaterThan(0)
    expect(screen.getAllByText('76 см').length).toBeGreaterThan(0)
  })

  it('replaces a stale backend builder session with the updated exercise plan', async () => {
    currentSearch = '?source=builder&programId=back-biceps&photo=before'

    useRuntimeStore.getState().initializeSession({
      source: 'builder',
      programId: 'back-biceps',
      photoMode: 'pre-workout',
    })

    const initialSession = useRuntimeStore.getState().session
    if (!initialSession) {
      throw new Error('Expected runtime session to be initialized')
    }

    const staleSession: RuntimeWorkoutSession = {
      ...initialSession,
      source: 'builder',
      programId: 'back-biceps',
      dataSource: 'backend',
      view: 'exercise-setup',
      exercises: initialSession.exercises.map((exercise, index) =>
        index === 0
          ? {
              ...exercise,
              slug: 'old-exercise',
              name: 'Старое упражнение',
            }
          : exercise,
      ),
    }
    const updatedSession: RuntimeWorkoutSession = {
      ...staleSession,
      exercises: staleSession.exercises.map((exercise, index) =>
        index === 0
          ? {
              ...exercise,
              slug: 'new-exercise',
              name: 'Новое упражнение',
            }
          : exercise,
      ),
    }

    useRuntimeStore.setState({ session: staleSession, sessionSignature: 'builder::back-biceps::pre-workout' })
    buildBackendBuilderRuntimeSessionMock.mockResolvedValue(updatedSession)

    renderScreen()

    await waitFor(() => expect(buildBackendBuilderRuntimeSessionMock).toHaveBeenCalled())
    await waitFor(() => expect(useRuntimeStore.getState().session?.exercises[0]?.slug).toBe('new-exercise'))
  })
})