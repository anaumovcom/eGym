import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BuilderExerciseEditor, BuilderExerciseItem, BuilderWorkoutGroup, WorkoutBuilderData } from '@/entities/builder/model/types'
import { buildStrengthPlan } from '@/features/strength/lib/strength-plan'
import { getExerciseDetails, getWorkoutBuilderData } from '@/mocks/stage2-data'
import { WorkoutBuilderScreen } from '@/screens/builder/workout-builder-screen'
import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(), apiPut: vi.fn(), apiPost: vi.fn(), apiDelete: vi.fn(),
}))

vi.mock('@/shared/ui/stage2/screen-components', async () => ({
  ...await vi.importActual<typeof import('@/shared/ui/stage2/screen-components')>('@/shared/ui/stage2/screen-components'),
  // Keep the real safety shell/dialogs, but do not fetch body-map assets.
  CompactBodyMapMini: () => null,
}))

type SavePayload = {
  userId: string
  programId: string
  workoutName: string
  groups: BuilderWorkoutGroup[]
  selectedExerciseId?: string
  selectedExercise?: BuilderExerciseEditor
}
type ServerProgram = { data: WorkoutBuilderData; editors: Map<string, BuilderExerciseEditor> }
type User = ReturnType<typeof userEvent.setup>

const originalAppState = useAppStore.getState()
const originalHardwareState = useHardwareStore.getState()
const hardwareCommand = vi.fn()
const fetchMock = vi.fn().mockRejectedValue(new Error('Real network is forbidden in builder persistence tests'))
const firstId = 'group-pullups-1'
const secondId = 'group-squat-1'
const programId = 'back-biceps'
let client: QueryClient
let programs: Map<string, ServerProgram>
let writes: SavePayload[]
let firstSaveGate: Promise<void> | undefined
let addedDetails: ReturnType<typeof getExerciseDetails>

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => { resolve = done })
  return { promise, resolve }
}

function editorForItem(item: BuilderExerciseItem): BuilderExerciseEditor {
  const loadType = item.loadType ?? 'weighted'
  const setParams = {
    sets: Number(item.sets.match(/^\d+/)?.[0] ?? 3),
    reps: Number(item.sets.match(/×(\d+)/)?.[1] ?? 10),
    weight: loadType === 'weighted' ? Number(item.load.match(/\d+/)?.[0] ?? 0) : 0,
    restSeconds: Number(item.rest.match(/\d+/)?.[0] ?? 120),
    ...(loadType === 'timed' ? { durationSeconds: Number(item.sets.match(/×(\d+)/)?.[1] ?? 60) } : {}),
  }
  const strengthModeId = item.strengthModeId ?? 'basic'
  return {
    name: item.name, subtitle: item.muscleGroup, setParams, loadType,
    loadMode: 'Обычный вес', tempo: 'Обычный', strengthModeId,
    strengthDayType: item.strengthDayType ?? null,
    strengthPlan: item.strengthPlan ?? buildStrengthPlan(strengthModeId, item.strengthDayType, setParams, loadType, { sets: setParams.sets, durationSeconds: setParams.durationSeconds }),
    note: `Note for ${item.id}`,
  }
}

function seedProgram(id: string, mode = 'basic', weight = 45) {
  const data = structuredClone(getWorkoutBuilderData())
  data.selectedProgramId = id
  data.info.name = data.programs.find((program) => program.id === id)!.name
  data.groups = [{ ...data.groups[0], items: data.groups[0].items.slice(0, 2).map((item, index) => {
    const next = { ...item, previewVideoUrl: undefined, strengthModeId: mode, load: `${index ? 60 : weight} кг` }
    return { ...next, strengthPlan: editorForItem(next).strengthPlan }
  }) }]
  const editors = new Map(data.groups[0].items.map((item) => [item.id, editorForItem(item)]))
  data.selectedExercise = structuredClone(editors.get(firstId)!)
  return { data, editors }
}

function serverData(id: string, selectedId = firstId): WorkoutBuilderData {
  const program = programs.get(id)!
  const item = program.data.groups.flatMap((group) => group.items).find((entry) => entry.id === selectedId)!
  return structuredClone({
    ...program.data, selectedExerciseId: selectedId,
    selectedExercise: program.editors.get(selectedId) ?? editorForItem(item),
  })
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderBuilder() {
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/builder?programId=${programId}&selectedExerciseId=${firstId}`]}>
          <WorkoutBuilderScreen />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
}

function stage() { return within(screen.getByRole('region', { name: 'Выбранное упражнение' })) }

async function commitValue(label: string, value: number, scope = stage()) {
  const input = scope.getByRole('textbox', { name: new RegExp(`^${label}(,|$)`) })
  fireEvent.change(input, { target: { value: String(value) } })
  fireEvent.keyDown(input, { key: 'Enter' })
  // Flush React and save microtasks without blurring a stale stepper draft.
  await act(async () => {})
}

async function saved() {
  await waitFor(() => expect(document.querySelector('.builder-save-status')).toHaveTextContent('Сохранено'))
}

async function selectItem(user: User, name: string, id: string) {
  await user.click(screen.getByRole('button', { name: `Выбрать упражнение ${name}`, exact: true }))
  await waitFor(() => {
    expect(screen.getByTestId('location')).toHaveTextContent(`selectedExerciseId=${id}`)
    expect(stage().getByRole('heading', { name, exact: true })).toBeVisible()
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', fetchMock)
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  useHardwareStore.setState({ snapshot: null, runCommand: hardwareCommand })
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } })
  programs = new Map([[programId, seedProgram(programId)], ['fullbody-base', seedProgram('fullbody-base', 'strength', 80)]])
  writes = []
  firstSaveGate = undefined
  addedDetails = { ...getExerciseDetails('barbell-curl'), name: 'Новое сгибание', equipment: 'Barbell', force: 'Pull', previewVideoUrl: undefined }
  addedDetails.loadSettings = { ...addedDetails.loadSettings, sets: 3, reps: 10, weight: 20, restSeconds: 120, mode: 'Обычный вес', tempo: 'Обычный' }
  vi.mocked(apiGet).mockReset().mockImplementation(async <T,>(path: string): Promise<T> => {
    const url = new URL(path, 'http://localhost')
    if (url.pathname === '/api/builder') return serverData(url.searchParams.get('programId') ?? programId, url.searchParams.get('selectedExerciseId') ?? firstId) as T
    if (url.pathname === '/api/dashboard') return { workouts: [] } as T
    if (url.pathname === '/api/exercises') return { items: [addedDetails], availableFilters: { muscles: [], equipment: [] } } as T
    if (url.pathname === `/api/exercises/${addedDetails.slug}`) return structuredClone(addedDetails) as T
    throw new Error(`Unexpected GET ${path}`)
  })
  vi.mocked(apiPut).mockReset().mockImplementation(async <T,>(path: string, body: unknown): Promise<T> => {
    expect(path).toBe('/api/builder/plan')
    const payload = structuredClone(body as SavePayload)
    const first = writes.length === 0
    writes.push(payload)
    if (first && firstSaveGate) await firstSaveGate
    const program = programs.get(payload.programId)!
    program.data.groups = structuredClone(payload.groups)
    program.data.info.name = payload.workoutName
    if (payload.selectedExerciseId && payload.selectedExercise) {
      // Never silently accept an editor belonging to a different selected item.
      const item = payload.groups.flatMap((group) => group.items).find((entry) => entry.id === payload.selectedExerciseId)
      expect(payload.selectedExercise.name).toBe(item?.name)
      program.editors.set(payload.selectedExerciseId, structuredClone(payload.selectedExercise))
    }
    return {} as T
  })
  vi.mocked(apiPost).mockReset().mockRejectedValue(new Error('Unexpected POST'))
  vi.mocked(apiDelete).mockReset().mockRejectedValue(new Error('Unexpected DELETE'))
})

afterEach(() => {
  cleanup()
  client.clear()
  useAppStore.setState(originalAppState, true)
  useHardwareStore.setState(originalHardwareState, true)
  vi.unstubAllGlobals()
  expect(hardwareCommand).not.toHaveBeenCalled()
  expect(fetchMock).not.toHaveBeenCalled()
  expect(apiPost).not.toHaveBeenCalled()
  expect(apiDelete).not.toHaveBeenCalled()
})

describe('builder plan persistence regressions', () => {
  it('saves no weight as bodyweight, restores it and allows adding weight again', async () => {
    const user = userEvent.setup()
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    await user.click(stage().getByRole('button', { name: 'Без веса', exact: true }))
    await saved()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ loadType: 'bodyweight', setParams: { weight: 0 } })
    expect(writes.at(-1)!.groups[0].items[0]).toMatchObject({ loadType: 'bodyweight', load: 'вес тела' })
    await selectItem(user, 'Присед', secondId)
    await selectItem(user, 'Тяга сверху', firstId)
    expect(stage().getByRole('textbox', { name: 'Вес, кг' })).toHaveValue('')
    expect(stage().getByRole('textbox', { name: 'Вес, кг' })).toHaveAttribute('placeholder', 'вес тела')
    await commitValue('Вес', 5)
    await saved()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ loadType: 'weighted', setParams: { weight: 5 } })
    expect(writes.at(-1)!.groups[0].items[0]).toMatchObject({ loadType: 'weighted', load: '5 кг' })
    await user.click(stage().getByRole('button', { name: 'Уменьшить: Вес' }))
    await saved()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ loadType: 'weighted', setParams: { weight: 4 } })
    await commitValue('Вес', 0)
    await saved()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ loadType: 'bodyweight', setParams: { weight: 0 } })
    await user.click(stage().getByRole('button', { name: 'Увеличить: Вес' }))
    await saved()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ loadType: 'weighted', setParams: { weight: 1 } })
  })

  it('autosaves per-side reps without doubling the builder plan and restores the flag on A → B → A', async () => {
    const user = userEvent.setup()
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    const checkbox = stage().getByRole('checkbox', { name: 'На каждую сторону', exact: true })
    expect(checkbox).not.toBeChecked()
    expect(stage().queryByText(/на левую и/)).not.toBeInTheDocument()
    await user.click(checkbox)
    await saved()
    expect(checkbox).toHaveAccessibleDescription('10 повторов на левую и 10 повторов на правую сторону')
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ perSide: true, setParams: { reps: 10 } })
    expect(writes.at(-1)!.groups[0].items[0]).toMatchObject({ perSide: true, sets: '3×10' })
    expect(writes.at(-1)!.groups[0].items[0].strengthPlan).toHaveLength(3)
    expect(screen.getByRole('button', { name: 'Выбрать упражнение Тяга сверху', exact: true })).toHaveTextContent('на каждую сторону')
    await selectItem(user, 'Присед', secondId)
    expect(stage().getByRole('checkbox', { name: 'На каждую сторону' })).not.toBeChecked()
    await selectItem(user, 'Тяга сверху', firstId)
    expect(stage().getByRole('checkbox', { name: 'На каждую сторону' })).toBeChecked()
    await user.click(stage().getByRole('checkbox', { name: 'На каждую сторону' }))
    await saved()
    expect(writes.at(-1)!.selectedExercise!.perSide).toBe(false)
    expect(writes.at(-1)!.groups[0].items[0].perSide).toBe(false)
    expect(screen.getByRole('button', { name: 'Выбрать упражнение Тяга сверху', exact: true })).not.toHaveTextContent('на каждую сторону')
    await selectItem(user, 'Присед', secondId)
    await selectItem(user, 'Тяга сверху', firstId)
    expect(stage().getByRole('checkbox', { name: 'На каждую сторону' })).not.toBeChecked()
  })

  it('keeps per-side timed targets through queued autosaves and mode changes', async () => {
    const user = userEvent.setup()
    const gate = deferred()
    firstSaveGate = gate.promise
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    try {
      await user.click(stage().getByRole('checkbox', { name: 'На каждую сторону' }))
      await user.click(stage().getByRole('radio', { name: 'На время' }))
      await commitValue('Длительность', 90)
      expect(stage().getByText('90 сек на левую и 90 сек на правую сторону')).toBeVisible()
      expect(apiPut).toHaveBeenCalledTimes(1)
      await act(async () => { gate.resolve() })
      await saved()
      expect(writes).toHaveLength(3)
      expect(writes.every((write) => write.selectedExercise?.perSide === true && write.groups[0].items[0].perSide === true)).toBe(true)
      expect(writes.at(-1)!.selectedExercise).toMatchObject({ perSide: true, loadType: 'timed', setParams: { durationSeconds: 90 } })
      expect(writes.at(-1)!.groups[0].items[0].sets).toBe('3×90 сек')
      await selectItem(user, 'Присед', secondId)
      await selectItem(user, 'Тяга сверху', firstId)
      expect(stage().getByRole('checkbox', { name: 'На каждую сторону' })).toBeChecked()
      expect(stage().getByText('90 сек на левую и 90 сек на правую сторону')).toBeVisible()
      await user.click(stage().getByRole('radio', { name: 'Повторы' }))
      await saved()
      expect(stage().getByRole('checkbox', { name: 'На каждую сторону' })).toBeChecked()
      expect(stage().getByText('10 повторов на левую и 10 повторов на правую сторону')).toBeVisible()
    } finally {
      await act(async () => { gate.resolve() })
    }
  })

  it('normalizes a legacy editor from the item flag and retains it on unrelated edits', async () => {
    const program = programs.get(programId)!
    program.data.groups[0].items[0].perSide = true
    // Legacy editor has no flag, but the saved item is already per-side.
    expect(program.editors.get(firstId)!.perSide).toBeUndefined()
    const user = userEvent.setup()
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    expect(stage().getByRole('checkbox', { name: 'На каждую сторону' })).toBeChecked()
    await user.click(stage().getByRole('button', { name: 'Увеличить: Вес' }))
    await saved()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ perSide: true, setParams: { weight: 46 } })
    expect(writes.at(-1)!.groups[0].items[0].perSide).toBe(true)
  })

  it('preserves per-side on replacement and on the next immediate editor save', async () => {
    const user = userEvent.setup()
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    await user.click(stage().getByRole('checkbox', { name: 'На каждую сторону' }))
    await saved()
    await user.click(stage().getByRole('button', { name: 'Заменить упражнение Тяга сверху', exact: true }))
    await user.click(await screen.findByRole('button', { name: `Выбрать ${addedDetails.name}`, exact: true }))
    const dialog = screen.getByRole('dialog', { name: 'Настройте замену' })
    await user.click(within(dialog).getByRole('button', { name: 'Заменить в тренировке', exact: true }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(stage().getByRole('checkbox', { name: 'На каждую сторону' })).toBeChecked()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ name: addedDetails.name, perSide: true })
    expect(writes.at(-1)!.groups[0].items[0]).toMatchObject({ slug: addedDetails.slug, perSide: true })
    await user.click(stage().getByRole('button', { name: 'Увеличить: Повторы' }))
    await saved()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ name: addedDetails.name, perSide: true, setParams: { reps: 11 } })
    await selectItem(user, 'Присед', secondId)
    await selectItem(user, addedDetails.name, firstId)
    expect(stage().getByRole('checkbox', { name: 'На каждую сторону' })).toBeChecked()
  })

  it('serializes rapid editor saves and sends the latest timed duration only after the first PUT resolves', async () => {
    const user = userEvent.setup()
    const gate = deferred()
    firstSaveGate = gate.promise
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    expect(stage().getByRole('textbox', { name: 'Вес, кг' })).toHaveValue('45')
    try {
      await user.click(stage().getByRole('radio', { name: 'На время' }))
      await waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1))
      expect(writes[0].selectedExercise).toMatchObject({ loadType: 'timed', setParams: { durationSeconds: 60 } })
      await user.click(stage().getByRole('button', { name: 'Увеличить: Длительность' }))
      expect(stage().getByRole('textbox', { name: /^Длительность,/ })).toHaveValue('75')
      expect(apiPut).toHaveBeenCalledTimes(1)
      expect(document.querySelector('.builder-save-status')).toHaveTextContent('Сохранение…')
      await act(async () => { gate.resolve() })
      await saved()
      expect(apiPut).toHaveBeenCalledTimes(2)
      expect(writes[1].selectedExercise).toMatchObject({ loadType: 'timed', setParams: { durationSeconds: 75 } })
      expect(programs.get(programId)!.editors.get(firstId)).toMatchObject({ loadType: 'timed', setParams: { durationSeconds: 75 } })
      expect(programs.get(programId)!.data.groups[0].items[0]).toMatchObject({ loadType: 'timed', sets: '3×75 сек' })
    } finally {
      await act(async () => { gate.resolve() })
    }
  })

  it('restores saved mode and duration on A → B → A despite an older cached editor and strength plan', async () => {
    const user = userEvent.setup()
    const cacheKey = ['workout-builder', 'alexey', programId, firstId]
    const oldResponse = serverData(programId)
    client.setQueryData(cacheKey, oldResponse)
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    await user.click(stage().getByRole('button', { name: 'Без веса', exact: true }))
    await user.click(stage().getByRole('radio', { name: 'На время' }))
    await user.click(stage().getByRole('radio', { name: 'Повторы' }))
    await saved()
    expect(writes.at(-1)!.selectedExercise).toMatchObject({ loadType: 'bodyweight', setParams: { weight: 0 } })
    expect(writes.at(-1)!.selectedExercise!.setParams.durationSeconds).toBeUndefined()
    await user.click(stage().getByRole('radio', { name: 'На время' }))
    await commitValue('Длительность', 90)
    await user.click(stage().getByRole('button', { name: 'Режим и комментарий', exact: true }))
    const dialog = screen.getByRole('dialog', { name: 'Режим и комментарий' })
    expect(within(dialog).getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeEnabled()
    await user.click(within(dialog).getByRole('button', { name: 'Выбрать режим силовой тренировки' }))
    await user.click(within(dialog).getByRole('button', { name: /^Последний подход до отказа/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Готово', exact: true }))
    await saved()
    expect(programs.get(programId)!.editors.get(firstId)).toMatchObject({ strengthModeId: 'last_set_failure', loadType: 'timed', setParams: { durationSeconds: 90 } })
    // A's query was cached before these edits. Returning must update/invalidate it,
    // not merge its old editor/plan over the saved data.
    await selectItem(user, 'Присед', secondId)
    expect(stage().getByRole('radio', { name: 'Повторы' })).toBeChecked()
    expect(stage().getByRole('textbox', { name: 'Вес, кг' })).toHaveValue('60')
    await selectItem(user, 'Тяга сверху', firstId)
    expect(stage().getByRole('radio', { name: 'На время' })).toBeChecked()
    expect(stage().getByRole('textbox', { name: /^Длительность,/ })).toHaveValue('90')
    expect(stage().getByText('Последний подход до отказа', { exact: true })).toBeVisible()
    expect(programs.get(programId)!.editors.get(firstId)!.setParams.durationSeconds).toBe(90)
  })

  it('keeps custom added exercise parameters separate when selecting an existing item again', async () => {
    const user = userEvent.setup()
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    await user.click(stage().getByRole('radio', { name: 'На время' }))
    await commitValue('Длительность', 105)
    await saved()
    const existingEditor = structuredClone(programs.get(programId)!.editors.get(firstId)!)
    await user.click(screen.getByRole('button', { name: 'Добавить упражнение', exact: true }))
    await user.click(await screen.findByRole('button', { name: `Выбрать ${addedDetails.name}`, exact: true }))
    const dialog = screen.getByRole('dialog', { name: 'Настройте подходы' })
    await commitValue('Подходы', 7, within(dialog))
    await commitValue('Повторы', 17, within(dialog))
    await commitValue('Вес', 23, within(dialog))
    await commitValue('Отдых', 75, within(dialog))
    await user.click(within(dialog).getByRole('button', { name: 'Добавить в тренировку' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const addedItem = programs.get(programId)!.data.groups[0].items.find((item) => item.slug === addedDetails.slug)!
    expect(addedItem).toMatchObject({ sets: '7×17', load: '23 кг', rest: '75 сек', loadType: 'weighted' })
    await selectItem(user, addedDetails.name, addedItem.id)
    expect(stage().getByRole('textbox', { name: 'Подходы', exact: true })).toHaveValue('7')
    expect(stage().getByRole('textbox', { name: 'Повторы', exact: true })).toHaveValue('17')
    expect(stage().getByRole('textbox', { name: 'Вес, кг' })).toHaveValue('23')
    await user.click(stage().getByRole('button', { name: 'Увеличить: Повторы' }))
    await saved()
    await selectItem(user, 'Тяга сверху', firstId)
    expect(stage().getByRole('radio', { name: 'На время' })).toBeChecked()
    expect(stage().getByRole('textbox', { name: /^Длительность,/ })).toHaveValue('105')
    expect(programs.get(programId)!.editors.get(firstId)).toEqual(existingEditor)
    expect(programs.get(programId)!.editors.get(addedItem.id)).toMatchObject({ name: addedDetails.name, setParams: { reps: 18, weight: 23, sets: 7 } })
  })

  it('does not carry strength plans across programs sharing the same group and exercise IDs', async () => {
    const user = userEvent.setup()
    renderBuilder()
    await screen.findByRole('heading', { name: 'Тяга сверху', exact: true })
    expect(stage().getByText('Базовый режим', { exact: true })).toBeVisible()
    // Same mounted component and same item IDs, but a different program/editor identity.
    await user.click(screen.getByRole('button', { name: 'Мои тренировки', exact: true }))
    await screen.findByRole('heading', { name: 'Мои тренировки', exact: true })
    await user.click(screen.getByRole('button', { name: 'Открыть тренировку «Фуллбоди база»', exact: true }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('programId=fullbody-base'))
    await waitFor(() => expect(stage().getByText('Силовой режим', { exact: true })).toBeVisible())
    expect(stage().queryByText('Базовый режим', { exact: true })).not.toBeInTheDocument()
    expect(stage().getByRole('textbox', { name: 'Вес, кг' })).toHaveValue('80')
    await user.click(stage().getByRole('button', { name: 'Увеличить: Вес' }))
    await saved()
    const last = writes.at(-1)!
    expect(last).toMatchObject({ programId: 'fullbody-base', selectedExerciseId: firstId, selectedExercise: { strengthModeId: 'strength', setParams: { weight: 81 } } })
    expect(last.groups[0].items[0].strengthModeId).toBe('strength')
    expect(last.groups[0].items[0].strengthPlan).toEqual(last.selectedExercise!.strengthPlan)
    expect(programs.get(programId)!.editors.get(firstId)).toMatchObject({ strengthModeId: 'basic', setParams: { weight: 45 } })
  })
})