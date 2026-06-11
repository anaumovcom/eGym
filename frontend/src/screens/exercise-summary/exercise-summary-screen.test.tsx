import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
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
})