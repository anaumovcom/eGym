import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { createRuntimeSession } from '@/mocks/stage3-data'
import { apiGet, apiPut } from '@/shared/api/client'
import { getExerciseSettingsSnapshot, saveExerciseSettings, useExerciseSettings, type ExerciseSettingsSnapshot } from './use-exercise-settings'

const runtime = vi.hoisted(() => ({ session: null as RuntimeWorkoutSession | null, restoreExerciseSettings: vi.fn(), userId: 'alexey' }))
vi.mock('@/stores/runtime-store', () => ({ useRuntimeStore: { getState: () => runtime } }))
vi.mock('@/stores/app-store', () => ({ useAppStore: { getState: () => ({ selectedUserId: runtime.userId }) } }))
vi.mock('@/shared/api/client', () => ({ apiGet: vi.fn(), apiPut: vi.fn() }))

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function exercise() { return runtime.session!.exercises[0] }
function snapshot() { return getExerciseSettingsSnapshot(exercise()) }
function mount(options: { hydrate?: boolean; debounceMs?: number } = {}) {
  return renderHook(() => useExerciseSettings({ session: runtime.session, exercise: exercise(), userId: runtime.userId, ...options }))
}
function edit(weight: number) {
  const session = runtime.session!
  runtime.session = { ...session, exercises: [{ ...exercise(), loadSettings: { ...exercise().loadSettings, weight } }] }
}

describe('useExerciseSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiGet).mockResolvedValue(null)
    vi.mocked(apiPut).mockResolvedValue({})
    runtime.userId = 'alexey'
    const initial = createRuntimeSession({ source: 'catalog', slug: 'push-up' })
    runtime.session = { ...initial, id: crypto.randomUUID(), view: 'exercise-setup', exercises: [initial.exercises[0]] }
    runtime.restoreExerciseSettings.mockImplementation((settings: ExerciseSettingsSnapshot) => {
      runtime.session = { ...runtime.session!, exercises: [{ ...exercise(), loadSettings: { ...exercise().loadSettings, ...settings },
        strengthMode: { ...exercise().strengthMode, id: settings.trainingMode ?? 'basic', dayType: settings.trainingDayType } }] }
    })
  })

  it('waits for settings and restores exact targets/mode once, including zero load/rest', async () => {
    const read = deferred<ExerciseSettingsSnapshot | null>()
    const settings = { ...snapshot(), weight: 0, sets: 5, reps: 17, restSeconds: 0, trainingMode: 'hypertrophy' }
    vi.mocked(apiGet).mockReturnValue(read.promise)
    const view = mount()
    expect(view.result.current.ready).toBe(false)
    await act(async () => read.resolve(settings))
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    expect(runtime.restoreExerciseSettings).toHaveBeenCalledExactlyOnceWith(settings)
    view.rerender()
    view.unmount()
    const reopened = mount()
    expect(reopened.result.current.ready).toBe(true)
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiPut).not.toHaveBeenCalled()
  })

  it('does not persist initial defaults on a successful null read', async () => {
    const view = mount({ debounceMs: 1 })
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    expect(await view.result.current.flush()).toBe(true)
    expect(apiPut).not.toHaveBeenCalled()
  })

  it('blocks failed reads, exposes the error and retries explicitly without fallback', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('read unavailable')).mockResolvedValueOnce(null)
    const view = mount()
    await waitFor(() => expect(view.result.current.error).toBe('read unavailable'))
    expect(view.result.current.ready).toBe(false)
    expect(await view.result.current.flush()).toBe(false)
    expect(apiPut).not.toHaveBeenCalled()
    await act(async () => { await view.result.current.retry() })
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('retains local edits across a failed GET and an explicit retry', async () => {
    const server = { ...snapshot(), weight: 22, reps: 18 }
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(server)
    const view = mount()
    await waitFor(() => expect(view.result.current.error).toBe('offline'))
    edit(47)
    view.rerender()
    await act(async () => { await view.result.current.retry() })
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    expect(snapshot()).toMatchObject({ weight: 47, reps: 18 })
  })

  it('preserves edits made during GET and flushes the edited snapshot', async () => {
    const read = deferred<ExerciseSettingsSnapshot | null>()
    const server = { ...snapshot(), weight: 20, reps: 19 }
    vi.mocked(apiGet).mockReturnValue(read.promise)
    const view = mount()
    edit(37)
    view.rerender()
    await act(async () => read.resolve(server))
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    expect(snapshot()).toMatchObject({ weight: 37, reps: 19 })
    await act(async () => { expect(await view.result.current.flush()).toBe(true) })
    expect(apiPut).toHaveBeenCalledWith('/api/runtime/exercises/settings', expect.objectContaining({ userId: 'alexey', weight: 37, reps: 19 }))
  })

  it('debounces changes and exposes retryable PUT errors', async () => {
    const view = mount({ debounceMs: 5 })
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    vi.mocked(apiPut).mockRejectedValueOnce(new Error('write unavailable')).mockResolvedValueOnce({})
    edit(41)
    view.rerender()
    await waitFor(() => expect(view.result.current.error).toBe('write unavailable'))
    expect(apiPut).toHaveBeenCalledTimes(1)
    await act(async () => { expect(await view.result.current.retry()).toBe(true) })
    expect(view.result.current.error).toBeNull()
    expect(apiPut).toHaveBeenCalledTimes(2)
  })

  it('ignores a GET arriving after navigation and cancels delayed writes on unmount', async () => {
    const read = deferred<ExerciseSettingsSnapshot | null>()
    const server = { ...snapshot(), weight: 99 }
    vi.mocked(apiGet).mockReturnValue(read.promise)
    const view = mount()
    view.unmount()
    await act(async () => read.resolve(server))
    expect(runtime.restoreExerciseSettings).not.toHaveBeenCalled()
    expect(apiPut).not.toHaveBeenCalled()
    const reopened = mount({ debounceMs: 1 })
    await waitFor(() => expect(reopened.result.current.ready).toBe(true))
    edit(46)
    reopened.rerender()
    reopened.unmount()
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 15)) })
    expect(apiPut).not.toHaveBeenCalled()
  })

  it('never hydrates resumed completed sets or active session counters', async () => {
    runtime.session = { ...runtime.session!, currentSetIndex: 1, completedSets: { [exercise().id]: [{ setNumber: 1, actualValue: 7, plannedValue: 10, tempoLabel: 'test' }] } }
    const resumed = mount()
    await waitFor(() => expect(resumed.result.current.ready).toBe(true))
    expect(apiGet).not.toHaveBeenCalled()
    expect(runtime.restoreExerciseSettings).not.toHaveBeenCalled()
    expect(runtime.session.currentSetIndex).toBe(1)
    resumed.unmount()
    runtime.session = { ...runtime.session, id: crypto.randomUUID(), view: 'exercise-session', currentSetIndex: 0, completedSets: {} }
    const active = mount({ hydrate: false })
    await waitFor(() => expect(active.result.current.ready).toBe(true))
    await act(async () => { await active.result.current.save({ ...snapshot(), weight: 33 }) })
    expect(apiGet).not.toHaveBeenCalled()
    expect(apiPut).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ weight: 33 }))
  })

  it('blocks user switching within the same runtime session', async () => {
    const view = mount()
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    runtime.userId = 'elena'
    view.rerender()
    expect(view.result.current.ready).toBe(false)
    expect(view.result.current.error).toContain('владельца')
    expect(await view.result.current.flush()).toBe(false)
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiPut).not.toHaveBeenCalled()
  })

  it('serializes cross-screen writes so an older PUT cannot overwrite a newer weight', async () => {
    const first = deferred<ExerciseSettingsSnapshot>()
    vi.mocked(apiPut).mockReturnValueOnce(first.promise).mockResolvedValueOnce({})
    const old = saveExerciseSettings('alexey', exercise().slug, { ...snapshot(), weight: 20 })
    const next = saveExerciseSettings('alexey', exercise().slug, { ...snapshot(), weight: 40 })
    await waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1))
    first.resolve(snapshot())
    await Promise.all([old, next])
    expect(apiPut).toHaveBeenNthCalledWith(2, expect.anything(), expect.objectContaining({ weight: 40 }))
  })

  it('flush drains edits committed during an in-flight save before allowing start', async () => {
    const view = mount()
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    const first = deferred<ExerciseSettingsSnapshot>()
    vi.mocked(apiPut).mockReturnValueOnce(first.promise).mockResolvedValueOnce({})
    edit(21)
    let flush!: Promise<boolean>
    act(() => { flush = view.result.current.flush() })
    await waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1))
    edit(42)
    await act(async () => { first.resolve(snapshot()); expect(await flush).toBe(true) })
    expect(apiPut).toHaveBeenNthCalledWith(2, expect.anything(), expect.objectContaining({ weight: 42 }))
  })

  it('does not continue a start flush or enqueue another snapshot after unmount', async () => {
    const view = mount()
    await waitFor(() => expect(view.result.current.ready).toBe(true))
    const first = deferred<ExerciseSettingsSnapshot>()
    vi.mocked(apiPut).mockReturnValueOnce(first.promise)
    edit(21)
    let flush!: Promise<boolean>
    act(() => { flush = view.result.current.flush() })
    await waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1))
    edit(42)
    view.unmount()
    first.resolve(snapshot())
    expect(await flush).toBe(false)
    expect(apiPut).toHaveBeenCalledTimes(1)
  })
})