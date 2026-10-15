import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ExerciseSummaryScreen } from '@/screens/exercise-summary/exercise-summary-screen'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

describe('ExerciseSummaryScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    useAppStore.setState({
      selectedUserId: 'alexey',
      emergencyStopActive: false,
    })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
  })

  it('shows the next-exercise action when the workout has remaining exercises', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    useRuntimeStore.getState().finishExerciseWithResults([], 'completed')

    const session = useRuntimeStore.getState().session
    if (!session?.exerciseSummary) {
      throw new Error('Expected exercise summary to be available')
    }

    useRuntimeStore.setState({
      session: {
        ...session,
        exerciseSummary: {
          ...session.exerciseSummary,
          nextStepLabel: 'Открыть итог тренировки',
        },
      },
    })

    render(
      <MemoryRouter>
        <ExerciseSummaryScreen />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Перейти к следующему упражнению' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Открыть итог тренировки' })).not.toBeInTheDocument()
  })

  it('shows the workout-summary action when there is no next exercise', () => {
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    useRuntimeStore.getState().finishExerciseWithResults([], 'completed')

    render(
      <MemoryRouter>
        <ExerciseSummaryScreen />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Открыть итог тренировки' })).toBeInTheDocument()
  })

  it('returns to a skipped exercise from the summary of the next one', async () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    const [first, second] = useRuntimeStore.getState().session!.exercises
    useRuntimeStore.getState().completeExercise('skipped')
    useRuntimeStore.getState().continueAfterExerciseSummary()
    useRuntimeStore.getState().finishExerciseWithResults([], 'completed')

    render(
      <MemoryRouter initialEntries={['/exercise-summary']}>
        <Routes>
          <Route path="/exercise-summary" element={<ExerciseSummaryScreen />} />
          <Route path="/exercise-setup" element={<p>setup</p>} />
        </Routes>
      </MemoryRouter>,
    )

    const skipped = screen.getByRole('region', { name: 'Пропущенные упражнения' })
    expect(skipped).toHaveTextContent(first.name)
    expect(skipped).not.toHaveTextContent(second.name)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Выполнить упражнение' }))

    expect(await screen.findByText('setup')).toBeInTheDocument()
    expect(useRuntimeStore.getState().session).toMatchObject({ currentExerciseId: first.id, view: 'exercise-setup' })
  })

  it('leaves a summary that was already consumed for the step the workout is on', async () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    useRuntimeStore.getState().finishExerciseWithResults([], 'completed')
    useRuntimeStore.getState().continueAfterExerciseSummary()

    render(
      <MemoryRouter initialEntries={['/exercise-summary']}>
        <Routes>
          <Route path="/exercise-summary" element={<ExerciseSummaryScreen />} />
          <Route path="/exercise-setup" element={<p>setup</p>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('setup')).toBeInTheDocument()
  })
})