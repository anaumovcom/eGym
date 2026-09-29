import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkoutSummaryScreen } from '@/screens/workout-summary/workout-summary-screen'
import { apiPost } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

const navigateMock = vi.fn()
let currentSearch = '?source=catalog&slug=barbell-floor-press'

vi.mock('react-router-dom', async () => ({
  ...await vi.importActual<typeof import('react-router-dom')>('react-router-dom'),
  useNavigate: () => navigateMock,
  useLocation: () => ({ search: currentSearch }),
  useSearchParams: () => [new URLSearchParams(currentSearch)],
}))

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiPost: vi.fn(),
}))

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WorkoutSummaryScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('WorkoutSummaryScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    navigateMock.mockReset()
    vi.mocked(apiPost).mockReset()
    currentSearch = '?source=catalog&slug=barbell-floor-press'
    useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()
    useRuntimeStore.getState().setBackendWorkoutSessionId(42)
    useRuntimeStore.getState().setBackendExerciseSessionId(useRuntimeStore.getState().session!.currentExerciseId, 91)
    useRuntimeStore.getState().completeWorkout('partial')
    vi.mocked(apiPost).mockResolvedValue({ ...useRuntimeStore.getState().session!.workoutSummary, workoutSessionId: 42 })
  })

  it.each(['', '&photo=before', '&photo=after'])('saves results without a photo step or today CTA (%s)', async (photo) => {
    const user = userEvent.setup()
    currentSearch += photo
    renderScreen()

    await waitFor(() => expect(useRuntimeStore.getState().session?.backendWorkoutSaved).toBe(true))
    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(apiPost).toHaveBeenCalledWith('/api/runtime/workouts', expect.objectContaining({
      userId: 'alexey', source: 'catalog', status: 'partial', workoutSessionId: 42, exerciseSessionIds: [91],
    }))
    expect(screen.queryByRole('button', { name: /фото|план на сегодня/i })).not.toBeInTheDocument()
    expect(useRuntimeStore.getState().session?.view).toBe('workout-summary')
    expect(navigateMock).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Усталость и восстановление' }))
    expect(navigateMock).toHaveBeenCalledWith('/fatigue')
  })

  it('resumes remaining sets with backend IDs and results intact after a legacy photo URL', async () => {
    const user = userEvent.setup()
    currentSearch += '&photo=after'
    const session = useRuntimeStore.getState().session!
    renderScreen()
    await waitFor(() => expect(useRuntimeStore.getState().session?.backendWorkoutSaved).toBe(true))

    await user.click(screen.getByRole('button', { name: /Доделать/ }))

    expect(navigateMock).toHaveBeenCalledWith(`/exercise-session${currentSearch}`)
    expect(useRuntimeStore.getState().session).toMatchObject({
      id: session.id,
      view: 'exercise-session',
      currentExerciseId: session.currentExerciseId,
      currentSetIndex: 1,
      completedSets: session.completedSets,
      backendWorkoutSessionId: 42,
      backendExerciseSessionIds: session.backendExerciseSessionIds,
      backendWorkoutSaved: false,
    })
  })
})