import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SetFeedback } from './set-feedback'
import { apiPost } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

vi.mock('@/shared/api/client', () => ({ apiPost: vi.fn() }))

function fixture() {
  const original = useRuntimeStore.getState().session!
  const set = { ...original.restState!.completedSet, backendSetId: 91, subjectiveEffort: null, discomfortLevel: null }
  const session = { ...original, dataSource: 'backend' as const, restState: { ...original.restState!, completedSet: set },
    completedSets: { [original.currentExerciseId]: [set] } }
  useRuntimeStore.setState({ session })
  return session
}

describe('optional saved-set feedback', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(apiPost).mockReset()
    useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'machine-pulldown' })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()
  })

  it('starts entirely unknown and sends only the clicked explicit value with the stable saved ID', async () => {
    const session = fixture()
    vi.mocked(apiPost).mockResolvedValue({ subjectiveEffort: 6, discomfortLevel: null })
    render(<SetFeedback session={session} userId="alexey" />)
    expect(apiPost).not.toHaveBeenCalled()
    for (const button of screen.getAllByRole('button')) expect(button).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Умеренно · 6/10' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Умеренно · 6/10' })).toHaveAttribute('aria-pressed', 'true'))
    expect(apiPost).toHaveBeenCalledExactlyOnceWith('/api/runtime/sets/91/feedback', { userId: 'alexey', subjectiveEffort: 6 })
    expect(useRuntimeStore.getState().session?.restState?.completedSet).toMatchObject({ backendSetId: 91, subjectiveEffort: 6, discomfortLevel: null })
    expect(useRuntimeStore.getState().session?.completedSets[session.currentExerciseId][0].subjectiveEffort).toBe(6)
  })

  it('stores an explicit zero, reports positive discomfort, and never resets safety', async () => {
    const session = fixture()
    useAppStore.setState({ emergencyStopActive: true })
    vi.mocked(apiPost).mockResolvedValueOnce({ subjectiveEffort: null, discomfortLevel: 0 })
      .mockResolvedValueOnce({ subjectiveEffort: null, discomfortLevel: 1 })
    render(<SetFeedback session={session} userId="alexey" />)
    fireEvent.click(screen.getByRole('button', { name: 'Нет дискомфорта · 0/10' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Нет дискомфорта · 0/10' })).toHaveAttribute('aria-pressed', 'true'))
    fireEvent.click(screen.getByRole('button', { name: 'Дискомфорт · 1/10' }))
    await screen.findByRole('note')
    expect(useAppStore.getState().emergencyStopActive).toBe(true)
    expect(apiPost).toHaveBeenLastCalledWith('/api/runtime/sets/91/feedback', { userId: 'alexey', discomfortLevel: 1 })
  })

  it('shows a recoverable error without inventing a saved rating', async () => {
    const session = fixture()
    vi.mocked(apiPost).mockRejectedValue(new Error('offline'))
    render(<SetFeedback session={session} userId="alexey" />)
    fireEvent.click(screen.getByRole('button', { name: 'Тяжело · 9/10' }))
    await screen.findByRole('alert')
    expect(useRuntimeStore.getState().session?.restState?.completedSet.subjectiveEffort).toBeNull()
    expect(screen.getByRole('button', { name: 'Тяжело · 9/10' })).toHaveAttribute('aria-pressed', 'false')
  })

  it.each(['user', 'set', 'view'])('does not apply a late response after changing %s', async change => {
    const session = fixture()
    let resolve!: (value: unknown) => void
    vi.mocked(apiPost).mockImplementation(() => new Promise(done => { resolve = done }) as never)
    render(<SetFeedback session={session} userId="alexey" />)
    const button = screen.getByRole('button', { name: 'Легко · 3/10' })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(apiPost).toHaveBeenCalledTimes(1)
    if (change === 'user') useAppStore.setState({ selectedUserId: 'elena' })
    else useRuntimeStore.setState({ session: change === 'view' ? { ...session, view: 'exercise-session' } : {
      ...session, restState: { ...session.restState!, completedSet: { ...session.restState!.completedSet, backendSetId: 92 } } } })
    await act(async () => resolve({ subjectiveEffort: 3, discomfortLevel: null }))
    expect(useRuntimeStore.getState().session?.restState?.completedSet.subjectiveEffort).toBeNull()
  })
})