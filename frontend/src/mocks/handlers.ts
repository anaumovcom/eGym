import { http, HttpResponse } from 'msw'
import {
  buildDashboardScenario,
  dashboardStoryScenarios,
  type DashboardScenarioName,
  machineScenarios,
  type KnownUserId,
  type MachineScenarioName,
  mockUsers,
} from '@/mocks/data'
import { getQuickStartData, getTodayWorkoutData, getWorkoutCalendarData } from '@/mocks/stage2-data'

function isDashboardScenario(value: string | null): value is DashboardScenarioName {
  return value !== null && value in dashboardStoryScenarios
}

function isMachineScenario(value: string | null): value is MachineScenarioName {
  return value !== null && value in machineScenarios
}

function getKnownUserId(value: string | null): KnownUserId {
  if (value === 'alexey' || value === 'elena' || value === 'guest') {
    return value
  }

  return 'alexey'
}

function getPreferenceList(value: string | null) {
  return value ? value.split(',').map((item) => item.trim()).filter(Boolean) : undefined
}

export const handlers = [
  http.get('/api/users', () => HttpResponse.json({ users: mockUsers })),
  http.get('/api/machine/status', ({ request }) => {
    const url = new URL(request.url)
    const scenario = url.searchParams.get('scenario')

    if (isMachineScenario(scenario)) {
      return HttpResponse.json(machineScenarios[scenario])
    }

    if (isDashboardScenario(scenario)) {
      return HttpResponse.json(buildDashboardScenario('alexey', scenario).machine)
    }

    return HttpResponse.json(machineScenarios.ready)
  }),
  http.get('/api/dashboard', ({ request }) => {
    const url = new URL(request.url)
    const scenario = url.searchParams.get('scenario')
    const userId = getKnownUserId(url.searchParams.get('userId'))

    return HttpResponse.json(buildDashboardScenario(userId, isDashboardScenario(scenario) ? scenario : 'default'))
  }),
  http.get('/api/quick-start', ({ request }) => {
    const url = new URL(request.url)
    const userId = getKnownUserId(url.searchParams.get('userId'))

    return HttpResponse.json(
      getQuickStartData(userId, url.searchParams.get('selected'), {
        favorites: getPreferenceList(url.searchParams.get('favorites')),
        blacklist: getPreferenceList(url.searchParams.get('blacklist')),
      }),
    )
  }),
  http.get('/api/today', ({ request }) => {
    const url = new URL(request.url)
    const userId = getKnownUserId(url.searchParams.get('userId'))
    const scenario = url.searchParams.get('scenario')

    return HttpResponse.json(
      getTodayWorkoutData(
        userId,
        scenario === 'planned' || scenario === 'in-progress' || scenario === 'completed' || scenario === 'blocked' || scenario === 'recovery'
          ? scenario
          : 'planned',
        url.searchParams.get('selected') ?? undefined,
        {
          favorites: getPreferenceList(url.searchParams.get('favorites')),
          blacklist: getPreferenceList(url.searchParams.get('blacklist')),
        },
      ),
    )
  }),
  http.get('/api/calendar', ({ request }) => {
    const url = new URL(request.url)
    const mode = url.searchParams.get('mode') === 'week' ? 'week' : 'month'
    return HttpResponse.json(getWorkoutCalendarData(mode, url.searchParams.get('selectedDayId') ?? '2026-05-14'))
  }),
  http.post('/api/runtime/exercises', async ({ request }) => {
    const payload = await request.json() as { exerciseSlug?: string; exerciseName?: string; targetSets?: number; sets?: Array<{ setNumber: number; plannedValue: number; actualValue: number; setType?: string; targetMinReps?: number; targetMaxReps?: number; reps?: number; weightKg?: number; rir?: number; subjectiveEffort?: number; discomfortLevel?: number; pain?: boolean; techniqueBreakdown?: boolean; comment?: string; amplitudePercent?: number; tempoLabel?: string; syncLabel?: string }> }
    const sets = payload.sets ?? []
    const totalReps = sets.reduce((sum, item) => sum + (item.reps ?? item.actualValue ?? 0), 0)
    const totalVolume = sets.reduce((sum, item) => sum + ((item.weightKg ?? 0) * (item.reps ?? item.actualValue ?? 0)), 0)
    const resultLine = sets.filter((item) => item.setType !== 'warmup').map((item) => item.reps ?? item.actualValue).join(' / ')

    return HttpResponse.json({
      exerciseSessionId: 1,
      outcome: 'completed',
      exerciseId: `${payload.exerciseSlug ?? 'exercise'}-1`,
      title: 'Упражнение завершено',
      subtitle: `${payload.exerciseName ?? 'Упражнение'} · ${sets.length} подхода выполнено`,
      setResults: sets.map((item) => ({ ...item, volumeKg: (item.weightKg ?? 0) * (item.reps ?? item.actualValue ?? 0), tempoLabel: item.tempoLabel ?? 'хорошо' })),
      totals: {
        setsCompleted: `${sets.length} из ${payload.targetSets ?? sets.length}`,
        repsOrTime: `${totalReps} повторов`,
        volume: `${Math.round(totalVolume)} кг`,
        bestSet: sets.length ? `Подход ${sets[0].setNumber}: ${sets[0].weightKg ?? 0} кг × ${sets[0].reps ?? sets[0].actualValue}` : '—',
        averageAmplitude: undefined,
        tempo: 'стабильный',
      },
      planVsFact: [
        { label: 'Подходы', plan: `${payload.targetSets ?? sets.length}`, fact: `${sets.length}`, delta: `${sets.length - (payload.targetSets ?? sets.length)}` },
        { label: 'Повторы', plan: `${sets.reduce((sum, item) => sum + item.plannedValue, 0)}`, fact: `${totalReps}`, delta: `${totalReps - sets.reduce((sum, item) => sum + item.plannedValue, 0)}` },
        { label: 'Вес', plan: sets[0]?.weightKg ? `${sets[0].weightKg} кг` : '—', fact: sets.at(-1)?.weightKg ? `${sets.at(-1)?.weightKg} кг` : '—', delta: '—' },
      ],
      recommendation: sets.some((item) => item.pain || item.techniqueBreakdown)
        ? `Ты выполнил ${resultLine}. Ты отметил боль или потерю техники. Не увеличивай вес на следующей тренировке.`
        : `Ты выполнил ${resultLine}. Пока оставь текущий вес и добирай повторы в заданном диапазоне.`,
      nextStepLabel: 'Открыть итог тренировки',
    })
  }),
]