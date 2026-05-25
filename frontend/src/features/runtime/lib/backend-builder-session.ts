import type { BuilderExerciseItem, BuilderLoadType, BuilderWorkoutGroup, WorkoutBuilderData } from '@/entities/builder/model/types'
import type { ExerciseDetails, ExerciseLoadSettings } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'
import type {
  RuntimeCalibrationState,
  RuntimeExerciseKind,
  RuntimeExercisePlan,
  RuntimePhotoMode,
  RuntimePhotoProgressState,
  RuntimePhotoShot,
  RuntimePhotoView,
  RuntimeSetPlan,
  RuntimeWorkoutSession,
  RuntimeWorkoutSummaryState,
} from '@/entities/runtime/model/types'
import { buildStrengthPlan, getStrengthModeTitle, normalizeStrengthDayType, normalizeStrengthModeId, toRuntimeSetPlan } from '@/features/strength/lib/strength-plan'
import { apiGet } from '@/shared/api/client'

const defaultPhotoHints: Record<RuntimePhotoView, string> = {
  front: 'Встаньте лицом к камере и совместите силуэт.',
  side: 'Повернитесь боком к камере и сохраните нейтральную позу.',
  back: 'Повернитесь спиной к камере и держите плечи ровно.',
}

const fallbackMachine: MachineHealth = {
  machineState: 'ready',
  machineLabel: 'Тренажёр готов',
  leftDrive: 'connected',
  rightDrive: 'connected',
  safety: 'enabled',
  calibration: 'Калибровка: перед упражнением',
}

type BuilderRuntimeSessionOptions = {
  userId: string
  programId: string
  runId?: string
  photoMode?: RuntimePhotoMode | null
  calibrationState?: RuntimeCalibrationState
}

type BuilderExerciseEntry = {
  group: BuilderWorkoutGroup
  item: BuilderExerciseItem
}

export async function buildBackendBuilderRuntimeSession(options: BuilderRuntimeSessionOptions): Promise<RuntimeWorkoutSession> {
  const builderParams = new URLSearchParams({ userId: options.userId, programId: options.programId })
  const [builderData, machine] = await Promise.all([
    apiGet<WorkoutBuilderData>(`/api/builder?${builderParams.toString()}`),
    apiGet<MachineHealth>('/api/machine/status').catch(() => fallbackMachine),
  ])

  const entries = builderData.groups.flatMap((group) => group.items.map((item) => ({ group, item })))
  if (entries.length === 0) {
    throw new Error('В выбранной тренировке нет упражнений')
  }

  const uniqueSlugs = [...new Set(entries.map(({ item }) => item.slug))]
  const detailsEntries = await Promise.all(
    uniqueSlugs.map(async (slug) => {
      const details = await apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(slug)}?userId=${encodeURIComponent(options.userId)}`)
      return [slug, details] as const
    }),
  )
  const detailsBySlug = new Map(detailsEntries)

  const exercises = entries.map(({ group, item }, index) => {
    const details = detailsBySlug.get(item.slug)
    if (!details) {
      throw new Error(`Не удалось загрузить упражнение ${item.slug}`)
    }

    return buildRuntimeExerciseFromBuilderItem({
      group,
      item,
      details,
      order: index + 1,
      calibrationState: options.calibrationState,
      workoutName: builderData.info.name,
    })
  }).map((exercise, index, allExercises) => ({
    ...exercise,
    nextExerciseId: allExercises[index + 1]?.id,
  }))

  const photoMode = options.photoMode ?? null

  return {
    id: `backend-builder-${options.programId}-${options.runId ?? exercises.map((exercise) => exercise.id).join('-')}`,
    source: 'builder',
    programId: options.programId,
    runId: options.runId,
    dataSource: 'backend',
    view: photoMode ? 'photo-progress' : 'exercise-setup',
    machine,
    workoutTitle: builderData.info.name,
    workoutSubtitle: [builderData.info.type, builderData.info.duration].filter(Boolean).join(' · '),
    currentExerciseId: exercises[0].id,
    currentSetIndex: 0,
    photoProgress: buildPhotoProgressState(photoMode ?? 'manual', false),
    exercises,
    completedSets: {},
    completedExerciseIds: [],
    workoutSummary: buildBuilderWorkoutSummary(builderData, exercises),
  }
}

function buildRuntimeExerciseFromBuilderItem({
  group,
  item,
  details,
  order,
  calibrationState,
  workoutName,
}: {
  group: BuilderWorkoutGroup
  item: BuilderExerciseItem
  details: ExerciseDetails
  order: number
  calibrationState?: RuntimeCalibrationState
  workoutName: string
}): RuntimeExercisePlan {
  const loadType = inferBuilderLoadType(item)
  const kind = getRuntimeKind(loadType)
  const restSeconds = parseSeconds(item.rest, details.loadSettings.restSeconds)
  const setCount = parseSetCount(item.sets, details.loadSettings.sets)
  const targetValue = loadType === 'timed'
    ? parseDurationSeconds(item.sets, details.loadSettings.reps)
    : parseTargetReps(item.sets, details.loadSettings.reps)
  const weight = loadType === 'weighted' ? parseWeight(item.load, details.loadSettings.weight) : 0
  const loadSettings: ExerciseLoadSettings = {
    ...details.loadSettings,
    weight,
    sets: setCount,
    reps: targetValue,
    restSeconds,
    mode: loadType === 'timed' ? 'Темповый режим' : loadType === 'bodyweight' ? 'Без тренажёра' : details.loadSettings.mode,
    recommendation: `Параметры взяты из тренировки «${workoutName}».`,
    calibration: kind === 'machine' && weight > 0
      ? calibrationState === 'saved'
        ? 'ready'
        : 'required'
      : 'unavailable',
  }
  const normalizedModeId = normalizeStrengthModeId(item.strengthModeId)
  const normalizedDayType = normalizeStrengthDayType(normalizedModeId, item.strengthDayType)
  const resolvedCalibrationState: RuntimeCalibrationState = kind === 'machine' && weight > 0
    ? (calibrationState ?? 'missing')
    : 'not-needed'
  const muscles = item.muscles?.length ? item.muscles : details.muscles
  const name = item.name || details.name
  const plan = buildRuntimeSetPlan({ item, loadType, loadSettings, modeId: normalizedModeId, dayType: normalizedDayType })

  return {
    id: item.id || `${item.slug}-${order}`,
    slug: item.slug,
    order,
    name,
    secondaryName: details.secondaryName,
    kind,
    muscles,
    summary: {
      ...details,
      name,
      muscles,
    },
    details: {
      ...details,
      name,
      muscles,
      loadSettings,
    },
    loadSettings,
    calibrationState: resolvedCalibrationState,
    movementRangeLabel: resolvedCalibrationState === 'saved' ? 'Калибровка сохранена' : resolvedCalibrationState === 'missing' ? 'Калибровка не найдена' : 'Не требуется',
    movementRangeSaved: resolvedCalibrationState === 'saved',
    plan,
    strengthMode: {
      id: normalizedModeId,
      title: getStrengthModeTitle(normalizedModeId),
      dayType: normalizedDayType,
    },
    recommendation: `Следуйте плану из конструктора: ${item.sets}, отдых ${item.rest}.`,
    previewLabel: group.kind === 'single' ? undefined : group.title,
  }
}

function buildRuntimeSetPlan({
  item,
  loadType,
  loadSettings,
  modeId,
  dayType,
}: {
  item: BuilderExerciseItem
  loadType: BuilderLoadType
  loadSettings: Pick<ExerciseLoadSettings, 'weight' | 'sets' | 'reps' | 'restSeconds'>
  modeId: string
  dayType: string | null
}): RuntimeSetPlan[] {
  if (loadType === 'timed') {
    return Array.from({ length: loadSettings.sets }, () => ({
      targetSeconds: loadSettings.reps,
      weightLabel: 'вес тела',
      restSeconds: loadSettings.restSeconds,
    }))
  }

  if (item.strengthPlan?.length) {
    return item.strengthPlan.map(toRuntimeSetPlan)
  }

  if (loadType === 'bodyweight') {
    return Array.from({ length: loadSettings.sets }, () => ({
      targetReps: loadSettings.reps,
      targetMinReps: loadSettings.reps,
      targetMaxReps: loadSettings.reps,
      weightLabel: 'вес тела',
      restSeconds: loadSettings.restSeconds,
    }))
  }

  return buildStrengthPlan(modeId, dayType, loadSettings, 'weighted').map(toRuntimeSetPlan)
}

function inferBuilderLoadType(item: Pick<BuilderExerciseItem, 'load' | 'sets' | 'loadType'>): BuilderLoadType {
  if (item.loadType) {
    return item.loadType
  }

  if (item.sets.includes('сек')) {
    return 'timed'
  }

  if (item.load.toLowerCase().includes('вес')) {
    return 'bodyweight'
  }

  return 'weighted'
}

function getRuntimeKind(loadType: BuilderLoadType): RuntimeExerciseKind {
  if (loadType === 'timed') {
    return 'timed'
  }

  if (loadType === 'bodyweight') {
    return 'bodyweight'
  }

  return 'machine'
}

function parseSetCount(value: string, fallback: number) {
  const match = value.match(/^(\d+)/)
  return Math.max(1, Number(match?.[1] ?? fallback))
}

function parseTargetReps(value: string, fallback: number) {
  const match = value.match(/[×x]\s*(\d+)/i)
  if (match) {
    return Math.max(1, Number(match[1]))
  }

  const fallbackMatch = value.match(/\d+/)
  return Math.max(1, Number(fallbackMatch?.[0] ?? fallback))
}

function parseDurationSeconds(value: string, fallback: number) {
  const matches = [...value.matchAll(/(\d+)\s*сек/gi)]
  const lastMatch = matches.at(-1)
  return Math.max(1, Number(lastMatch?.[1] ?? fallback))
}

function parseSeconds(value: string, fallback: number) {
  const match = value.match(/\d+/)
  return Math.max(15, Number(match?.[0] ?? fallback))
}

function parseWeight(value: string, fallback: number) {
  const match = value.replace(',', '.').match(/\d+(?:\.\d+)?/)
  return Math.max(0, Number(match?.[0] ?? fallback))
}

function buildPhotoShots(): RuntimePhotoShot[] {
  return [
    { view: 'front', status: 'pending', title: 'Спереди', hint: defaultPhotoHints.front },
    { view: 'side', status: 'pending', title: 'Сбоку', hint: defaultPhotoHints.side },
    { view: 'back', status: 'pending', title: 'Сзади', hint: defaultPhotoHints.back },
  ]
}

function buildPhotoProgressState(mode: RuntimePhotoMode, completed = false): RuntimePhotoProgressState {
  return {
    mode,
    autoPrompt: mode !== 'manual',
    completed,
    currentView: completed ? 'back' : 'front',
    shots: completed
      ? buildPhotoShots().map((shot) => ({
          ...shot,
          status: 'ready',
          imageUrl: `/assets/photo-progress/${shot.view}.jpg`,
          takenAt: new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }),
        }))
      : buildPhotoShots(),
    timerSeconds: 2,
    readyMessage: mode === 'post-workout' ? 'Фото после тренировки помогут увидеть динамику восстановления.' : 'Фото нужны только для личного прогресса.',
    privacyNote: 'Фото сохраняются только в профиль текущего пользователя и не используются для сравнения с другими.',
  }
}

function buildBuilderWorkoutSummary(builderData: WorkoutBuilderData, exercises: RuntimeExercisePlan[]): RuntimeWorkoutSummaryState {
  const totalSets = exercises.reduce((sum, exercise) => sum + exercise.plan.length, 0)

  return {
    outcome: 'partial',
    title: 'Тренировка запланирована',
    subtitle: `${builderData.info.name} · ${builderData.info.duration} · ${exercises.length} упражнений`,
    metrics: [
      { label: 'длительность', value: builderData.info.duration, hint: 'по плану' },
      { label: 'упражнений', value: `${exercises.length}`, hint: 'из конструктора' },
      { label: 'подходов', value: `${totalSets}`, hint: 'запланировано' },
    ],
    exercises: exercises.map((exercise) => ({
      name: exercise.name,
      result: `${exercise.plan.length} подхода`,
      status: 'moved',
    })),
    muscleLoad: buildMuscleLoad(exercises),
    recommendation: 'Начните с первого упражнения и следуйте параметрам, сохранённым в конструкторе.',
    nextWorkout: '—',
    feeling: 'normal',
    discomfort: 'none',
  }
}

function buildMuscleLoad(exercises: RuntimeExercisePlan[]): MuscleCard[] {
  const uniqueMuscles = [...new Set(exercises.flatMap((exercise) => exercise.muscles))]
  return uniqueMuscles.map((name) => ({
    name,
    status: 'ready',
    score: 0,
  }))
}
