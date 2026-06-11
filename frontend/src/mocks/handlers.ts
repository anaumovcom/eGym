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
]