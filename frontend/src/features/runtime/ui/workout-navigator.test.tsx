import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { WorkoutNavigator } from '@/features/runtime/ui/workout-navigator'
import { apiPost } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiPost: vi.fn(),
}))

const originalHardwareState = useHardwareStore.getState()
const runCommand = vi.fn()

function LiveNavigator() {
  const session = useRuntimeStore((state) => state.session)
  return session ? <WorkoutNavigator session={session} /> : null
}

function renderNavigator() {
  return render(
    <MemoryRouter initialEntries={['/rest?source=today']}>
      <Routes>
        <Route path="/rest" element={<LiveNavigator />} />
        <Route path="/exercise-setup" element={<p>Экран настройки</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

function session() {
  return useRuntimeStore.getState().session!
}

async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /^Упражнения тренировки: выполнено/ }))
  return within(screen.getByRole('dialog', { name: 'Упражнения тренировки' }))
}

describe('WorkoutNavigator', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(apiPost).mockReset().mockResolvedValue({})
    runCommand.mockReset().mockResolvedValue({})
    useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
    useHardwareStore.setState({ snapshot: null, runCommand })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    // Two sets of the first exercise are done; the workout rests before the third one.
    useRuntimeStore.getState().finishCurrentSet()
    useRuntimeStore.getState().beginNextStep()
    useRuntimeStore.getState().finishCurrentSet()
    const first = session().exercises[0]
    useRuntimeStore.setState({ session: { ...session(), backendWorkoutSessionId: 7, backendExerciseSessionIds: { [first.id]: 41 } } })
  })

  afterEach(() => {
    cleanup()
    useHardwareStore.setState(originalHardwareState, true)
  })

  it('colors exercises and sets by progress and marks where the workout is', async () => {
    const user = userEvent.setup()
    renderNavigator()
    const panel = await openPanel(user)
    const [first, second] = session().exercises

    const firstItem = panel.getByRole('button', { name: new RegExp(`^${first.name}: сейчас, 2 из ${first.plan.length}`) }).closest('li')!
    expect(firstItem).toHaveAttribute('data-status', 'current')
    expect(firstItem).toHaveAttribute('aria-current', 'step')
    const sets = within(within(firstItem as HTMLElement).getByRole('group'))
    expect(sets.getByRole('button', { name: 'подход 1: повторить' })).toHaveAttribute('data-status', 'done')
    expect(sets.getByRole('button', { name: 'подход 3: сейчас' })).toBeDisabled()

    const secondItem = panel.getByRole('button', { name: new RegExp(`^${second.name}: не начато`) }).closest('li')!
    expect(secondItem).toHaveAttribute('data-status', 'pending')
    expect(within(within(secondItem as HTMLElement).getByRole('group')).getByRole('button', { name: 'подход 2: ещё не доступен' })).toBeDisabled()
  })

  it('opens another exercise at once and keeps the left one as partial', async () => {
    const user = userEvent.setup()
    renderNavigator()
    const panel = await openPanel(user)
    const [first, , third] = session().exercises

    await user.click(panel.getByRole('button', { name: new RegExp(`^${third.name}: не начато.*Перейти к следующему подходу$`) }))

    expect(await screen.findByText('Экран настройки')).toBeInTheDocument()
    expect(apiPost).not.toHaveBeenCalled()
    expect(session()).toMatchObject({ currentExerciseId: third.id, currentSetIndex: 0, view: 'exercise-setup' })
    expect(session().exerciseOutcomes?.[first.id]).toBe('partial')
    expect(session().completedSets[first.id]).toHaveLength(2)
  })

  it('asks before redoing a done set, trims the backend and stops a running set first', async () => {
    const user = userEvent.setup()
    useHardwareStore.setState({ snapshot: { control: { mode: 'training' } } as unknown as HardwareSnapshot })
    renderNavigator()
    const panel = await openPanel(user)
    const first = session().exercises[0]
    const firstItem = panel.getByRole('button', { name: new RegExp(`^${first.name}:`) }).closest('li')!

    await user.click(within(firstItem as HTMLElement).getByRole('button', { name: 'подход 2: повторить' }))
    const confirm = within(screen.getByRole('dialog', { name: 'Повторить подход 2?' }))
    expect(confirm.getByText(/подход будет выполнен заново/)).toBeInTheDocument()
    expect(apiPost).not.toHaveBeenCalled()

    await user.click(confirm.getByRole('button', { name: 'Повторить' }))

    expect(await screen.findByText('Экран настройки')).toBeInTheDocument()
    expect(runCommand).toHaveBeenCalledWith(expect.objectContaining({ action: 'complete_set', userId: 'alexey', exerciseSlug: first.slug }))
    expect(apiPost).toHaveBeenCalledTimes(1)
    const [path, body] = vi.mocked(apiPost).mock.calls[0] as [string, { exerciseSessionId: number; resetSets: boolean; status: string; sets: Array<{ setNumber: number }> }]
    expect(path).toBe('/api/runtime/exercises')
    expect(body).toMatchObject({ exerciseSessionId: 41, resetSets: true, status: 'in_progress' })
    expect(body.sets.map((set) => set.setNumber)).toEqual([1])
    expect(session()).toMatchObject({ currentExerciseId: first.id, currentSetIndex: 1, view: 'exercise-setup' })
    expect(session().completedSets[first.id]).toHaveLength(1)
  })

  it('redoes from the first set through the reset endpoint', async () => {
    const user = userEvent.setup()
    vi.mocked(apiPost).mockResolvedValue({ missingExerciseSessionIds: [] })
    renderNavigator()
    const panel = await openPanel(user)
    const first = session().exercises[0]
    const firstItem = panel.getByRole('button', { name: new RegExp(`^${first.name}:`) }).closest('li')!

    await user.click(within(firstItem as HTMLElement).getByRole('button', { name: 'подход 1: повторить' }))
    expect(screen.getByText(/этот и следующие подходы \(всего 2\)/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Повторить' }))

    expect(await screen.findByText('Экран настройки')).toBeInTheDocument()
    expect(vi.mocked(apiPost).mock.calls[0][0]).toBe('/api/runtime/exercises/reset')
    expect(session().completedSets[first.id]).toBeUndefined()
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('keeps the workout unchanged and shows the error when the backend fails', async () => {
    const user = userEvent.setup()
    vi.mocked(apiPost).mockRejectedValue(new Error('Сервер недоступен'))
    renderNavigator()
    const panel = await openPanel(user)
    const before = session()
    const firstItem = panel.getByRole('button', { name: new RegExp(`^${before.exercises[0].name}:`) }).closest('li')!

    await user.click(within(firstItem as HTMLElement).getByRole('button', { name: 'подход 2: повторить' }))
    await user.click(screen.getByRole('button', { name: 'Повторить' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Сервер недоступен')
    expect(session()).toBe(before)
    expect(screen.queryByText('Экран настройки')).not.toBeInTheDocument()
  })
})
