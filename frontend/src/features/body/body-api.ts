import { queryOptions, type QueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPost } from '@/shared/api/client'
import type { BodyMeasurement, BodyMetricKey } from './body-metrics'

export const bodyMeasurementsQuery = (userId: string) => queryOptions({
  queryKey: ['body-measurements', userId],
  queryFn: async () => (await apiGet<{ measurements: BodyMeasurement[] }>(`/api/body-measurements?userId=${encodeURIComponent(userId)}`)).measurements,
})

export const bodyApi = {
  create: (userId: string, measuredAt: string, values: Partial<Record<BodyMetricKey, number | null>>) => apiPost('/api/body-measurements', { userId, measuredAt, ...values }),
  remove: (userId: string, id: number) => apiDelete(`/api/body-measurements/${id}?userId=${encodeURIComponent(userId)}&confirm=true`),
}

/** Body data is shown on profile, progress and scale screens; refresh all of them together. */
export async function invalidateBody(client: QueryClient, userId: string) {
  await Promise.all([['body-measurements', userId], ['user-profile-screen', userId], ['progress-screen', userId], ['scales', 'history', userId], ['scales', 'latest', userId]].map((queryKey) => client.invalidateQueries({ queryKey })))
}
