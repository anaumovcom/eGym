import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { WorkoutBuilderData } from '@/entities/builder/model/types'
import { getWorkoutBuilderData } from '@/mocks/stage2-data'
import { WorkoutBuilderScreen } from '@/screens/builder/workout-builder-screen'
import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
}))

vi.mock('@/shared/ui/stage2/screen-components', async () => ({
  ...await vi.importActual<typeof import('@/shared/ui/stage2/screen-components')>('@/shared/ui/stage2/screen-components'),
  // Body-map SVG fetching is unrelated to creation; keep the shell and safety dialog real.
  CompactBodyMapMini: () => null,
}))

const originalAppState = useAppStore.getState()
const originalHardwareState = useHardwareStore.getState()
const hardwareCommand = vi.fn()
const fetchMock = vi.fn().mockRejectedValue(new Error('Real network is forbidden in builder creation tests'))
const dialogName = 'Создать новую тренировку?'
const confirmName = 'Создать тренировку'
let client: QueryClient
let builder: WorkoutBuilderData
let originalBuilder: WorkoutBuilderData

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function currentUrl() {
  return new URL(screen.getByTestId('location').textContent!, 'http://localhost')
}

async function openNoteField(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Режим и комментарий', exact: true }))
  return screen.getByRole('textbox', { name: 'Комментарий к упражнению' })
}

function renderBuilder(path = '/builder') {
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <WorkoutBuilderScreen />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', fetchMock)
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  useHardwareStore.setState({ snapshot: null, runCommand: hardwareCommand })
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } })
  builder = getWorkoutBuilderData()
  originalBuilder = structuredClone(builder)
  vi.mocked(apiGet).mockReset()
  vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => {
    if (!path.startsWith('/api/builder?')) throw new Error(`Unexpected request ${path}`)
    const params = new URL(path, 'http://localhost').searchParams
    if (params.get('programId') === 'created-program') {
      return {
        ...structuredClone(builder),
        programs: [...builder.programs, { id: 'created-program', name: 'Новая тренировка', subtitle: 'Пустая тренировка', recommendedToday: false }],
        selectedProgramId: 'created-program',
        selectedExerciseId: '',
        info: { ...builder.info, name: 'Новая тренировка' },
        groups: [{ id: 'new-group-1', kind: 'single', title: 'Новая группа', betweenRoundsRest: '120 сек', items: [] }],
      } as T
    }
    return structuredClone(builder) as T
  })
  vi.mocked(apiPost).mockReset().mockResolvedValue({ id: 'created-program', status: 'created' })
  vi.mocked(apiPut).mockReset().mockResolvedValue({})
  vi.mocked(apiDelete).mockReset().mockResolvedValue(undefined)
})

afterEach(() => {
  cleanup()
  client.clear()
  useAppStore.setState(originalAppState, true)
  useHardwareStore.setState(originalHardwareState, true)
  vi.unstubAllGlobals()
  expect(hardwareCommand).not.toHaveBeenCalled()
  expect(fetchMock).not.toHaveBeenCalled()
  expect(apiDelete).not.toHaveBeenCalled()
})

describe('HOME-6/HOME-8 builder creation confirmation', () => {
  it('opens the URL intent without writes, keeps STOP in the safety dialog and cancels without losing the existing plan', async () => {
    const user = userEvent.setup()
    renderBuilder('/builder?create=new&programId=back-biceps&selectedExerciseId=group-pullups-1&source=home')
    const dialog = await screen.findByRole('dialog', { name: dialogName })
    expect(within(dialog).getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeEnabled()
    expect(dialog.querySelector('.forma-dialog-dock')).not.toBeNull()
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).not.toHaveBeenCalled()

    await user.click(within(dialog).getByRole('button', { name: 'Отмена' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(currentUrl().pathname).toBe('/builder')
    expect(Object.fromEntries(currentUrl().searchParams)).toEqual({ programId: 'back-biceps', selectedExerciseId: 'group-pullups-1', source: 'home' })
    expect(screen.getByRole('heading', { level: 1, name: new RegExp(originalBuilder.info.name) })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Выбрать упражнение Тяга сверху', exact: true })).toBeVisible()
    expect(builder).toEqual(originalBuilder)
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Новая тренировка', exact: true })).toHaveFocus())
    expect(await openNoteField(user)).toHaveValue(originalBuilder.selectedExercise.note)
    expect(apiPut).not.toHaveBeenCalled()
  })

  it.each(['/builder', '/builder?create=other'])('does not open or create on mount at %s; the normal button opens the same cancellable dialog', async (path) => {
    const user = userEvent.setup()
    renderBuilder(path)
    await screen.findByRole('heading', { name: 'Мои тренировки', exact: true })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(apiPost).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Новая тренировка', exact: true }))
    expect(screen.getByRole('dialog', { name: dialogName })).toBeVisible()
    expect(apiPost).not.toHaveBeenCalled()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(currentUrl().searchParams.has('create')).toBe(false)
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).not.toHaveBeenCalled()
  })

  it('creates only once after confirmation, blocks duplicate/close while pending, selects the result and invalidates dashboard caches', async () => {
    const user = userEvent.setup()
    const creation = deferred<{ id: string; status: string }>()
    vi.mocked(apiPost).mockReturnValue(creation.promise)
    client.setQueryData(['dashboard', 'alexey', 'default'], { workouts: ['existing'] })
    client.setQueryData(['dashboard', 'alexey', 'planned'], { workouts: ['existing'] })
    client.setQueryData(['dashboard', 'elena', 'default'], { workouts: ['other-user'] })
    const view = renderBuilder('/builder?create=new&programId=back-biceps&selectedExerciseId=group-pullups-1&source=home')
    const dialog = await screen.findByRole('dialog', { name: dialogName })
    await user.dblClick(within(dialog).getByRole('button', { name: confirmName }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1))
    expect(within(dialog).getByRole('button', { name: 'Создание…' })).toBeDisabled()
    expect(within(dialog).getByRole('button', { name: 'Отмена' })).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(dialog).toBeVisible()
    expect(currentUrl().searchParams.get('programId')).toBe('back-biceps')
    expect(apiPost).toHaveBeenCalledWith('/api/programs', expect.objectContaining({
      userId: 'alexey', name: 'Новая тренировка', recommendedToday: false,
      structure: { builderGroups: [{ id: 'new-group-1', kind: 'single', title: 'Новая группа', betweenRoundsRest: '120 сек', items: [] }] },
    }))
    expect(apiPut).not.toHaveBeenCalled()

    await act(async () => { creation.resolve({ id: 'created-program', status: 'created' }) })
    await screen.findByRole('button', { name: 'Добавь упражнения', exact: true })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(Object.fromEntries(currentUrl().searchParams)).toEqual({ programId: 'created-program', source: 'home' })
    expect(apiGet).toHaveBeenCalledWith('/api/builder?userId=alexey&programId=created-program')
    expect(client.getQueryState(['dashboard', 'alexey', 'default'])?.isInvalidated).toBe(true)
    expect(client.getQueryState(['dashboard', 'alexey', 'planned'])?.isInvalidated).toBe(true)
    expect(client.getQueryState(['dashboard', 'elena', 'default'])?.isInvalidated).toBe(false)
    expect(client.getQueryState(['workout-builder', 'alexey', 'back-biceps', 'group-pullups-1'])?.isInvalidated).toBe(true)
    expect(builder).toEqual(originalBuilder)
    // BUILD-1: the list of workouts is a separate view reached from the editor.
    await user.click(screen.getByRole('button', { name: 'Мои тренировки', exact: true }))
    expect(await screen.findByRole('heading', { name: 'Мои тренировки', exact: true })).toBeVisible()
    expect(currentUrl().searchParams.has('programId')).toBe(false)
    for (const program of builder.programs) expect(await screen.findByRole('button', { name: `Открыть тренировку «${program.name}»`, exact: true })).toBeVisible()
    expect(apiPut).not.toHaveBeenCalled()

    const resultingUrl = '/builder?programId=created-program&source=home'
    view.unmount()
    renderBuilder(resultingUrl)
    await screen.findByRole('heading', { level: 1, name: /Новая тренировка/ })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(apiPost).toHaveBeenCalledTimes(1)
  })

  it('shows a recoverable creation error without altering the current program, and retries only on explicit confirmation', async () => {
    const user = userEvent.setup()
    vi.mocked(apiPost).mockRejectedValueOnce(new Error('Create failed'))
    renderBuilder('/builder?create=new&programId=back-biceps')
    const dialog = await screen.findByRole('dialog', { name: dialogName })
    await user.click(within(dialog).getByRole('button', { name: confirmName }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Не удалось создать тренировку')
    expect(within(dialog).getByRole('button', { name: confirmName })).toBeEnabled()
    expect(within(dialog).getByRole('button', { name: 'Отмена' })).toBeEnabled()
    expect(currentUrl().searchParams.get('programId')).toBe('back-biceps')
    expect(currentUrl().searchParams.get('create')).toBe('new')
    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(builder).toEqual(originalBuilder)
    await user.click(within(dialog).getByRole('button', { name: confirmName }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(apiPost).toHaveBeenCalledTimes(2)
    expect(currentUrl().searchParams.get('programId')).toBe('created-program')
    expect(apiPut).not.toHaveBeenCalled()
  })

  it('allows cancel after a failed POST and clears the error on reopening without another write', async () => {
    const user = userEvent.setup()
    vi.mocked(apiPost).mockRejectedValueOnce(new Error('Create failed'))
    renderBuilder('/builder?create=new&programId=back-biceps')
    await screen.findByRole('dialog', { name: dialogName })
    await user.click(screen.getByRole('button', { name: confirmName }))
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(currentUrl().searchParams.has('create')).toBe(false)
    expect(currentUrl().searchParams.get('programId')).toBe('back-biceps')
    await user.click(screen.getByRole('button', { name: 'Новая тренировка', exact: true }))
    expect(screen.getByRole('dialog', { name: dialogName })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(apiPut).not.toHaveBeenCalled()
    expect(builder).toEqual(originalBuilder)
  })

  it('waits for the existing plan autosave before posting or switching programs', async () => {
    const user = userEvent.setup()
    const save = deferred<unknown>()
    vi.mocked(apiPut).mockReturnValue(save.promise)
    renderBuilder('/builder?programId=back-biceps')
    const note = await openNoteField(user)
    fireEvent.change(note, { target: { value: 'Keep my latest note' } })
    expect(apiPut).toHaveBeenCalledTimes(1)
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'Новая тренировка', exact: true }))
    await user.click(screen.getByRole('button', { name: confirmName }))
    expect(screen.getByRole('button', { name: 'Создание…' })).toBeDisabled()
    expect(apiPost).not.toHaveBeenCalled()
    expect(currentUrl().searchParams.get('programId')).toBe('back-biceps')
    expect(apiPut).toHaveBeenCalledWith('/api/builder/plan', expect.objectContaining({
      programId: 'back-biceps', workoutName: originalBuilder.info.name,
      selectedExercise: expect.objectContaining({ note: 'Keep my latest note' }),
      groups: expect.arrayContaining(originalBuilder.groups.map((group) => expect.objectContaining({ id: group.id }))),
    }))
    await act(async () => { save.resolve({}) })
    await waitFor(() => expect(currentUrl().searchParams.get('programId')).toBe('created-program'))
    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(apiPost).toHaveBeenCalledTimes(1)
  })

  it('does not create or discard local edits if the pending autosave fails', async () => {
    const user = userEvent.setup()
    const save = deferred<unknown>()
    vi.mocked(apiPut).mockReturnValue(save.promise)
    renderBuilder('/builder?programId=back-biceps')
    fireEvent.change(await openNoteField(user), { target: { value: 'Unsaved note' } })
    await user.keyboard('{Escape}')
    expect(document.querySelector('.builder-save-status')).toHaveTextContent('Сохранение…')
    await user.click(screen.getByRole('button', { name: 'Новая тренировка', exact: true }))
    await user.click(screen.getByRole('button', { name: confirmName }))
    await act(async () => { save.reject(new Error('Save failed')) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось сохранить текущую тренировку')
    expect(apiPost).not.toHaveBeenCalled()
    expect(currentUrl().searchParams.get('programId')).toBe('back-biceps')
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(document.querySelector('.builder-save-status')).toHaveTextContent('Не удалось сохранить изменения')
    expect(await openNoteField(user)).toHaveValue('Unsaved note')
    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(builder).toEqual(originalBuilder)
  })

  it('supports an empty builder but still requires confirmation before creating the first workout', async () => {
    const user = userEvent.setup()
    builder = { ...builder, programs: [], groups: [], selectedProgramId: '', selectedExerciseId: '', info: { ...builder.info, name: '' } }
    renderBuilder('/builder?create=new')
    await screen.findByRole('dialog', { name: dialogName })
    expect(apiPost).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: confirmName }))
    await waitFor(() => expect(currentUrl().searchParams.get('programId')).toBe('created-program'))
    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(apiPut).not.toHaveBeenCalled()
  })
})