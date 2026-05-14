import type {
  RuntimeCalibrationState,
  RuntimeExerciseKind,
  RuntimeExerciseOutcome,
  RuntimeExercisePlan,
  RuntimeExerciseSessionState,
  RuntimeExerciseSummaryState,
  RuntimeFlowSource,
  RuntimePhotoMode,
  RuntimePhotoProgressState,
  RuntimePhotoShot,
  RuntimePhotoView,
  RuntimeRestState,
  RuntimeSetPlan,
  RuntimeSetResult,
  RuntimeWorkoutOutcome,
  RuntimeWorkoutSession,
  RuntimeWorkoutSummaryState,
} from '@/entities/runtime/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'
import { machineScenarios } from '@/mocks/data'
import { getExerciseDetails } from '@/mocks/stage2-data'

type ExerciseOverride = {
  name?: string
  secondaryName?: string
  muscles?: string[]
  kind?: RuntimeExerciseKind
  calibrationState?: RuntimeCalibrationState
  movementRangeLabel?: string
  movementRangeSaved?: boolean
  recommendation?: string
  plan?: RuntimeSetPlan[]
  groupMeta?: RuntimeExercisePlan['groupMeta']
}

const defaultPhotoHints: Record<RuntimePhotoView, string> = {
  front: 'Встаньте лицом к камере и совместите силуэт.',
  side: 'Повернитесь боком к камере и сохраните нейтральную позу.',
  back: 'Повернитесь спиной к камере и держите плечи ровно.',
}

const bodyweightSlugs = new Set(['push-up'])
const timedSlugs = new Set(['forearm-plank'])

function detectKind(slug: string, fallback?: RuntimeExerciseKind): RuntimeExerciseKind {
  if (fallback) {
    return fallback
  }

  if (bodyweightSlugs.has(slug)) {
    return 'bodyweight'
  }

  if (timedSlugs.has(slug)) {
    return 'timed'
  }

  return 'machine'
}

function buildPlan(kind: RuntimeExerciseKind, detailsSlug: string): RuntimeSetPlan[] {
  if (kind === 'timed' || detailsSlug === 'forearm-plank') {
    return [
      { targetSeconds: 45, weightLabel: 'собственный вес', restSeconds: 60 },
      { targetSeconds: 45, weightLabel: 'собственный вес', restSeconds: 60 },
      { targetSeconds: 45, weightLabel: 'собственный вес', restSeconds: 60 },
    ]
  }

  if (kind === 'bodyweight') {
    return [
      { targetReps: 12, weightLabel: 'собственный вес', restSeconds: 60 },
      { targetReps: 12, weightLabel: 'собственный вес', restSeconds: 60 },
      { targetReps: 12, weightLabel: 'собственный вес', restSeconds: 60 },
    ]
  }

  if (kind === 'group') {
    return [{ targetReps: 10, weightLabel: '45 кг', restSeconds: 30 }]
  }

  return [
    { targetReps: 10, weightLabel: '40 кг', restSeconds: 90 },
    { targetReps: 10, weightLabel: '40 кг', restSeconds: 90 },
    { targetReps: 10, weightLabel: '40 кг', restSeconds: 90 },
  ]
}

export function buildRuntimeExercisePlan(slug: string, order: number, override: ExerciseOverride = {}): RuntimeExercisePlan {
  const details = getExerciseDetails(slug)
  const kind = detectKind(slug, override.kind)
  const plan = override.plan ?? buildPlan(kind, slug)
  const name = override.name ?? (slug === 'push-up' ? 'Отжимания' : details.name)
  const secondaryName = override.secondaryName ?? (slug === 'push-up' ? 'Push-Ups' : details.secondaryName)
  const muscles = override.muscles ?? details.muscles
  const calibrationState = override.calibrationState ?? (kind === 'machine' ? 'saved' : 'not-needed')

  return {
    id: `${slug}-${order}`,
    slug,
    order,
    name,
    secondaryName,
    kind,
    muscles,
    summary: details,
    details: {
      ...details,
      name,
      secondaryName,
      muscles,
    },
    loadSettings: {
      ...details.loadSettings,
      weight: kind === 'machine' ? details.loadSettings.weight : 0,
      mode: kind === 'machine' ? details.loadSettings.mode : kind === 'timed' ? 'Темповый режим' : 'Без тренажёра',
      recommendation:
        override.recommendation ??
        (kind === 'machine'
          ? 'Оставить текущий вес. Можно увеличить на 2.5 кг при хорошем самочувствии.'
          : kind === 'timed'
            ? 'Сохраняйте стабильную линию корпуса и ровное дыхание.'
            : 'Текущий объём оптимален. Сохраняйте темп и амплитуду.'),
      calibration: calibrationState === 'saved' ? 'ready' : calibrationState === 'missing' ? 'required' : 'unavailable',
    },
    calibrationState,
    movementRangeLabel:
      override.movementRangeLabel ??
      (calibrationState === 'saved' ? '64–132 см' : calibrationState === 'missing' ? 'Калибровка не найдена' : 'Не требуется'),
    movementRangeSaved: override.movementRangeSaved ?? calibrationState === 'saved',
    plan,
    recommendation:
      override.recommendation ??
      (kind === 'machine'
        ? 'Подход выполнен уверенно. Можно оставить текущий вес.'
        : kind === 'timed'
          ? 'Сохраняйте дыхание и не проваливайтесь в пояснице.'
          : 'Сохраняйте стабильный темп и контролируйте технику.'),
    groupMeta: override.groupMeta,
  }
}

function buildPhotoShots(): RuntimePhotoShot[] {
  return [
    { view: 'front', status: 'pending', title: 'Спереди', hint: defaultPhotoHints.front },
    { view: 'side', status: 'pending', title: 'Сбоку', hint: defaultPhotoHints.side },
    { view: 'back', status: 'pending', title: 'Сзади', hint: defaultPhotoHints.back },
  ]
}

export function buildPhotoProgressState(mode: RuntimePhotoMode, completed = false): RuntimePhotoProgressState {
  return {
    mode,
    autoPrompt: mode !== 'manual',
    completed,
    currentView: completed ? 'back' : 'front',
    shots: completed
      ? buildPhotoShots().map((shot) => ({
          ...shot,
          status: 'ready',
          imageUrl: `/mock-assets/photo-progress/${shot.view}.jpg`,
          takenAt: '14 мая 2026',
        }))
      : buildPhotoShots(),
    timerSeconds: 5,
    readyMessage: mode === 'post-workout' ? 'Фото после тренировки помогут увидеть динамику восстановления.' : 'Фото нужны только для личного прогресса.',
    privacyNote: 'Фото сохраняются только в профиль текущего пользователя и не используются для сравнения с другими.',
  }
}

function buildWorkoutExercises(source: RuntimeFlowSource, slug?: string, calibrationState?: RuntimeCalibrationState) {
  if (source === 'quick-start' || source === 'catalog') {
    return [buildRuntimeExercisePlan(slug ?? 'barbell-floor-press', 1, { calibrationState: calibrationState ?? 'saved' })]
  }

  if (source === 'builder') {
    return [
      buildRuntimeExercisePlan('machine-pulldown', 1, {
        kind: 'group',
        name: 'Подтягивания + Присед',
        secondaryName: 'Alternating Group',
        muscles: ['Спина', 'Ноги'],
        calibrationState: 'not-needed',
        plan: [{ targetReps: 10, weightLabel: '45 кг', restSeconds: 30 }],
        groupMeta: {
          groupName: 'Подтягивания + Присед',
          currentRound: 1,
          totalRounds: 3,
          currentStep: 1,
          totalSteps: 6,
          nextStepLabel: 'Присед ×8',
        },
      }),
    ]
  }

  return [
    buildRuntimeExercisePlan('barbell-floor-press', 1, { calibrationState: 'saved' }),
    buildRuntimeExercisePlan('machine-pulldown', 2, { calibrationState: 'saved' }),
    buildRuntimeExercisePlan('push-up', 3, { calibrationState: 'not-needed' }),
    buildRuntimeExercisePlan('forearm-plank', 4, { calibrationState: 'not-needed' }),
    buildRuntimeExercisePlan('machine-pulldown', 5, {
      kind: 'group',
      name: 'Подтягивания + Присед',
      secondaryName: 'Alternating Group',
      muscles: ['Спина', 'Ноги'],
      calibrationState: 'not-needed',
      plan: [{ targetReps: 10, weightLabel: '45 кг', restSeconds: 30 }],
      groupMeta: {
        groupName: 'Подтягивания + Присед',
        currentRound: 1,
        totalRounds: 3,
        currentStep: 1,
        totalSteps: 6,
        nextStepLabel: 'Присед ×8',
      },
    }),
  ]
}

export function createRuntimeSession(options: {
  source: RuntimeFlowSource
  slug?: string
  photoMode?: RuntimePhotoMode | null
  calibrationState?: RuntimeCalibrationState
}): RuntimeWorkoutSession {
  const exercises = buildWorkoutExercises(options.source, options.slug, options.calibrationState)
  const firstExercise = exercises[0]
  const photoMode = options.photoMode ?? null

  return {
    id: `${options.source}-${Date.now()}`,
    source: options.source,
    view: photoMode ? 'photo-progress' : 'exercise-setup',
    machine: machineScenarios.ready,
    workoutTitle: options.source === 'quick-start' || options.source === 'catalog' ? firstExercise.name : 'Спина + бицепс',
    workoutSubtitle: options.source === 'quick-start' || options.source === 'catalog' ? 'Одиночное упражнение' : 'Полная тренировка на моках',
    currentExerciseId: firstExercise.id,
    currentSetIndex: 0,
    photoProgress: buildPhotoProgressState(photoMode ?? 'manual', false),
    exercises,
    completedSets: {},
    completedExerciseIds: [],
    workoutSummary: buildWorkoutSummary(effectsForWorkout(exercises, {}), options.source === 'quick-start' || options.source === 'catalog' ? 'completed' : 'partial'),
  }
}

function getCurrentExercise(session: RuntimeWorkoutSession) {
  return session.exercises.find((exercise) => exercise.id === session.currentExerciseId) ?? session.exercises[0]
}

export function buildExerciseSession(session: RuntimeWorkoutSession): RuntimeExerciseSessionState {
  const exercise = getCurrentExercise(session)
  const setPlan = exercise.plan[session.currentSetIndex] ?? exercise.plan[exercise.plan.length - 1]
  const targetValue = setPlan.targetReps ?? setPlan.targetSeconds ?? 0
  const currentValue = Math.max(0, targetValue - (exercise.kind === 'machine' ? 3 : exercise.kind === 'bodyweight' ? 4 : exercise.kind === 'timed' ? 13 : 0))

  return {
    exerciseId: exercise.id,
    kind: exercise.kind,
    setNumber: session.currentSetIndex + 1,
    totalSets: exercise.plan.length,
    targetLabel:
      exercise.kind === 'timed'
        ? `цель ${setPlan.targetSeconds} сек`
        : exercise.kind === 'group'
          ? `${exercise.groupMeta?.groupName ?? 'Группа'} · шаг ${exercise.groupMeta?.currentStep ?? 1} из ${exercise.groupMeta?.totalSteps ?? 1}`
          : `цель ${setPlan.targetReps} повторов`,
    currentValue,
    targetValue,
    weightLabel: setPlan.weightLabel,
    hints:
      exercise.kind === 'timed'
        ? ['Дышите спокойно', 'Сохраняйте ровную линию корпуса']
        : exercise.kind === 'bodyweight'
          ? ['Темп хороший', 'Амплитуда в норме']
          : exercise.kind === 'group'
            ? ['Короткий отдых, затем переходите к следующему шагу']
            : ['Темп хорошо', 'Амплитуда норма', 'Синхронность сторон стабильна'],
    machine: session.machine,
    metrics:
      exercise.kind === 'timed'
        ? [
            { label: 'Цель', value: `${targetValue} сек`, tone: 'neutral' },
            { label: 'Темп', value: 'стабильно', tone: 'good' },
            { label: 'Интенсивность', value: 'лёгкая', tone: 'good' },
          ]
        : exercise.kind === 'bodyweight'
          ? [
              { label: 'Темп', value: 'хорошо', tone: 'good' },
              { label: 'Амплитуда', value: 'норма', tone: 'good' },
              { label: 'Нагрузка', value: 'собственный вес', tone: 'neutral' },
            ]
          : exercise.kind === 'group'
            ? [
                { label: 'Круг', value: `${exercise.groupMeta?.currentRound ?? 1} из ${exercise.groupMeta?.totalRounds ?? 1}`, tone: 'neutral' },
                { label: 'Шаг', value: `${exercise.groupMeta?.currentStep ?? 1} из ${exercise.groupMeta?.totalSteps ?? 1}`, tone: 'neutral' },
                { label: 'Дальше', value: exercise.groupMeta?.nextStepLabel ?? 'Следующий шаг', tone: 'good' },
              ]
            : [
                { label: 'Амплитуда', value: '92%', tone: 'good' },
                { label: 'Темп', value: 'хорошо', tone: 'good' },
                { label: 'Положение грифа', value: '86 см', tone: 'neutral' },
                { label: 'Синхронность', value: 'норма', tone: 'good' },
              ],
    motionTrack:
      exercise.kind === 'machine'
        ? {
            minLabel: '64 см',
            maxLabel: '104 см',
            currentLabel: '86 см',
            points: [
              { phase: 'down', value: 64 },
              { phase: 'down', value: 68 },
              { phase: 'up', value: 74 },
              { phase: 'up', value: 82 },
              { phase: 'current', value: 86 },
              { phase: 'down', value: 80 },
              { phase: 'down', value: 72 },
              { phase: 'down', value: 66 },
            ],
          }
        : undefined,
    groupMeta: exercise.groupMeta,
  }
}

export function simulateSetResult(session: RuntimeWorkoutSession): RuntimeSetResult {
  const exercise = getCurrentExercise(session)
  const setNumber = session.currentSetIndex + 1
  const plan = exercise.plan[session.currentSetIndex] ?? exercise.plan[exercise.plan.length - 1]
  const plannedValue = plan.targetReps ?? plan.targetSeconds ?? 0

  if (exercise.kind === 'timed') {
    return {
      setNumber,
      plannedValue,
      actualValue: [45, 45, 32][session.currentSetIndex] ?? plannedValue,
      tempoLabel: 'стабильно',
    }
  }

  if (exercise.kind === 'bodyweight') {
    return {
      setNumber,
      plannedValue,
      actualValue: [12, 10, 9][session.currentSetIndex] ?? plannedValue,
      amplitudePercent: 91,
      tempoLabel: 'хорошо',
    }
  }

  if (exercise.kind === 'group') {
    return {
      setNumber,
      plannedValue,
      actualValue: 10,
      tempoLabel: 'норма',
    }
  }

  return {
    setNumber,
    plannedValue,
    actualValue: [10, 10, 9][session.currentSetIndex] ?? plannedValue,
    amplitudePercent: [92, 92, 88][session.currentSetIndex] ?? 90,
    tempoLabel: 'хорошо',
    syncLabel: 'норма',
  }
}

export function buildRestState(session: RuntimeWorkoutSession, result: RuntimeSetResult): RuntimeRestState {
  const exercise = getCurrentExercise(session)
  const hasNextSet = session.currentSetIndex < exercise.plan.length - 1

  if (exercise.kind === 'group') {
    return {
      mode: 'group-step',
      title: 'Отдых перед следующим шагом',
      subtitle: `Группа: ${exercise.groupMeta?.groupName ?? 'Группа'} · круг ${exercise.groupMeta?.currentRound ?? 1} из ${exercise.groupMeta?.totalRounds ?? 1}`,
      totalSeconds: 30,
      remainingSeconds: 30,
      completedSet: result,
      recommendation: 'Короткий отдых, затем переходите к следующему шагу.',
      nextActionLabel: 'Начать присед',
      nextExercise: { name: 'Присед', target: '× 8', restLabel: '30 сек' },
      groupProgress: exercise.groupMeta,
    }
  }

  return {
    mode: hasNextSet ? 'between-sets' : 'next-exercise',
    title: hasNextSet ? 'Отдых между подходами' : 'Отдых между упражнениями',
    subtitle: `${exercise.name} · подход ${result.setNumber} из ${exercise.plan.length} завершён`,
    totalSeconds: exercise.plan[session.currentSetIndex].restSeconds,
    remainingSeconds: exercise.plan[session.currentSetIndex].restSeconds,
    completedSet: result,
    recommendation: result.actualValue < result.plannedValue ? 'Можно оставить текущий объём или добавить немного отдыха.' : 'Оставить текущий вес. Подход выполнен уверенно.',
    nextActionLabel: hasNextSet ? 'Начать следующий подход' : 'Перейти к следующему упражнению',
    nextExercise: hasNextSet
      ? { name: exercise.name, target: exercise.kind === 'timed' ? `${exercise.plan[session.currentSetIndex + 1]?.targetSeconds ?? result.plannedValue} сек` : `${exercise.plan[session.currentSetIndex + 1]?.targetReps ?? result.plannedValue} повторов`, restLabel: `${exercise.plan[session.currentSetIndex + 1]?.restSeconds ?? 60} сек` }
      : session.exercises[exercise.order]
        ? { name: session.exercises[exercise.order].name, target: session.exercises[exercise.order].kind === 'timed' ? `${session.exercises[exercise.order].plan[0].targetSeconds ?? 45} сек` : `${session.exercises[exercise.order].plan[0].targetReps ?? 10} повторов`, restLabel: `${session.exercises[exercise.order].plan[0].restSeconds} сек` }
        : undefined,
  }
}

export function buildExerciseSummary(session: RuntimeWorkoutSession, outcome: RuntimeExerciseOutcome): RuntimeExerciseSummaryState {
  const exercise = getCurrentExercise(session)
  const results = session.completedSets[exercise.id] ?? []
  const totalValue = results.reduce((sum, item) => sum + item.actualValue, 0)
  const totalVolume = exercise.kind === 'machine' ? `${Math.round(totalValue * (exercise.loadSettings.weight || 40))} кг` : exercise.kind === 'timed' ? `${totalValue} сек` : `${totalValue} повторов`
  const averageAmplitude = results.some((item) => typeof item.amplitudePercent === 'number')
    ? `${Math.round(results.reduce((sum, item) => sum + (item.amplitudePercent ?? 0), 0) / results.length)}%`
    : undefined

  return {
    outcome,
    exerciseId: exercise.id,
    title: outcome === 'aborted' ? 'Упражнение завершено досрочно' : exercise.kind === 'group' ? 'Группа завершена' : 'Упражнение завершено',
    subtitle: `${exercise.name} · ${results.length} подхода выполнено`,
    setResults: results,
    totals: {
      setsCompleted: `${results.length} из ${exercise.plan.length}`,
      repsOrTime: exercise.kind === 'timed' ? `${totalValue} сек` : `${totalValue} повторов`,
      volume: totalVolume,
      averageAmplitude,
      tempo: 'стабильный',
    },
    planVsFact: [
      { label: 'Подходы', plan: `${exercise.plan.length}`, fact: `${results.length}`, delta: `${results.length - exercise.plan.length}` },
      { label: exercise.kind === 'timed' ? 'Секунды' : 'Повторы', plan: `${exercise.plan.reduce((sum, item) => sum + (item.targetSeconds ?? item.targetReps ?? 0), 0)}`, fact: `${totalValue}`, delta: `${totalValue - exercise.plan.reduce((sum, item) => sum + (item.targetSeconds ?? item.targetReps ?? 0), 0)}` },
      { label: 'Вес', plan: exercise.kind === 'machine' ? `${exercise.loadSettings.weight} кг` : '—', fact: exercise.kind === 'machine' ? `${exercise.loadSettings.weight} кг` : '—', delta: '—' },
    ],
    recommendation: exercise.recommendation,
    nextStepLabel: session.exercises[exercise.order] ? 'Перейти к следующему упражнению' : 'Открыть итог тренировки',
  }
}

function effectsForWorkout(exercises: RuntimeExercisePlan[], completedSets: Record<string, RuntimeSetResult[]>): MuscleCard[] {
  const machineLoad = Object.values(completedSets).flat().length
  return exercises.map((exercise) => {
    const score = exercise.kind === 'machine' ? 60 + machineLoad * 4 : exercise.kind === 'timed' ? 28 : 38
    return {
      name: exercise.muscles[0] ?? exercise.name,
      status: (score > 80 ? 'high' : score > 60 ? 'medium' : score > 40 ? 'light' : 'ready') as MuscleCard['status'],
      score: Math.min(100, score),
    }
  })
}

export function buildWorkoutSummary(muscleLoad: ReturnType<typeof effectsForWorkout>, outcome: RuntimeWorkoutOutcome): RuntimeWorkoutSummaryState {
  return {
    outcome,
    title: outcome === 'aborted' ? 'Тренировка завершена частично' : 'Тренировка завершена',
    subtitle: outcome === 'aborted' ? 'Спина + бицепс · 31 минута · 3 из 5 упражнений выполнено' : 'Спина + бицепс · 47 минут · 5 упражнений выполнено',
    metrics:
      outcome === 'aborted'
        ? [
            { label: 'длительность', value: '31 минута', hint: 'частично выполнено' },
            { label: 'упражнений', value: '3 / 5', hint: 'выполнено' },
            { label: 'подходов', value: '12 / 18', hint: 'выполнено' },
            { label: 'повторов', value: '96', hint: 'суммарно' },
            { label: 'объём', value: '3 840 кг', hint: 'выполнено' },
          ]
        : [
            { label: 'длительность', value: '47 минут', hint: 'итог тренировки' },
            { label: 'упражнений', value: '5 / 5', hint: 'выполнено' },
            { label: 'подходов', value: '18 / 18', hint: 'выполнено' },
            { label: 'повторов', value: '164', hint: 'суммарно' },
            { label: 'объём', value: '6 420 кг', hint: 'общий объём' },
          ],
    exercises:
      outcome === 'aborted'
        ? [
            { name: 'Тяга верхнего блока', result: '4 подхода • 48 повторов • 1 920 кг', status: 'done' },
            { name: 'Тяга горизонтального блока', result: '4 подхода • 32 повтора • 1 280 кг', status: 'done' },
            { name: 'Сгибание рук с гантелями', result: '4 подхода • 16 повторов • 640 кг', status: 'done' },
            { name: 'Тяга штанги в наклоне', result: 'перенесено', status: 'moved' },
            { name: 'Молотковые сгибания', result: 'перенесено', status: 'moved' },
          ]
        : [
            { name: 'Тяга сверху', result: '4 подхода • 40 повторов • 1 600 кг', status: 'done' },
            { name: 'Тяга к поясу', result: '4 подхода • 36 повторов • 1 440 кг', status: 'done' },
            { name: 'Сгибание рук', result: '4 подхода • 32 повтора • 960 кг', status: 'done' },
            { name: 'Тяга прямыми руками', result: '3 подхода • 30 повторов • 720 кг', status: 'done' },
            { name: 'Планка', result: '3 подхода • 170 сек', status: 'done' },
          ],
    muscleLoad,
    recommendation:
      outcome === 'aborted'
        ? 'Сохранить результат как частично выполненный. Оставшиеся упражнения можно перенести на другой день.'
        : 'Следующую тяжёлую тренировку на спину лучше провести через 48 часов. Завтра можно сделать ноги, лёгкий кор или день отдыха.',
    nextWorkout: 'Пятница, 17 мая · Ноги + кор · ≈50 минут',
    feeling: 'normal',
    discomfort: outcome === 'aborted' ? 'minor' : 'none',
  }
}

export function rebuildSessionSnapshots(session: RuntimeWorkoutSession, outcome: RuntimeWorkoutOutcome = 'completed') {
  const muscleLoad = effectsForWorkout(session.exercises, session.completedSets)
  return {
    sessionState: buildExerciseSession(session),
    workoutSummary: buildWorkoutSummary(muscleLoad, outcome),
  }
}