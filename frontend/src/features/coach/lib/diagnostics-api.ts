/** VD request journal client: the Coach requests of one user, their outcome, cost and a sanitized error.
 * The server never returns keys, prompts or provider bodies; parsing still treats every field as untrusted. */
export type RequestStatus = 'ok' | 'error' | 'cancelled' | 'refused' | 'pending'
export type RequestKind = 'text' | 'voice' | 'prebuild' | 'pack' | 'scenario' | 'summary' | 'episode' | 'judge'
export type JournalPeriod = 'run' | 'today' | '7d'
export type JournalRow = Readonly<{
  id: string; group: string; runId: string; createdAt: number; finishedAt: number | null; stage: 'text' | 'voice'
  kind: RequestKind; purpose: string; model: string; triggerId: string | null; task: string | null
  exerciseLabel: string | null; setOrdinal: number | null; status: RequestStatus; ledgerStatus: string
  outcome: string | null; errorCode: string | null; httpStatus: number | null; durationMs: number | null
  firstByteMs: number | null; retry: boolean; costMicros: number; costSettled: boolean
}>
export type JournalDetail = JournalRow & Readonly<{
  errorDetail: string | null; textPreview: string | null; reserveMicros: number; settledMicros: number | null
  completeness: string | null; markupBytes: number | null; textBytes: number | null; pricingVersion: string | null
  usage: Readonly<Record<string, number | null>> | null
}>
export type JournalTotals = Readonly<{
  total: number; ok: number; error: number; cancelled: number; refused: number; pending: number
  settledMicros: number; pendingMicros: number; totalMicros: number; p50Ms: number | null; p95Ms: number | null; avgMicros: number | null
}>
export type JournalPage = Readonly<{ rows: readonly JournalRow[]; nextCursor: string | null; totals: JournalTotals }>
export type SpendEntry = Readonly<{ requests: number; micros: number; errors: number; p95Ms: number | null; avgMicros: number | null }>
export type Limit = Readonly<{ usedMicros: number; capMicros: number }>
export type BudgetState = Readonly<{ tier: number; liveAvailableMicros: number; liveShare: number; summaryReserveMicros: number
  byPurpose: Readonly<Record<string, number>>; avgRequestMicros: number | null }>
export type UsageSummary = Readonly<{
  byKind: Readonly<Record<string, SpendEntry>>; byModel: Readonly<Record<string, SpendEntry>>; byPurpose: Readonly<Record<string, number>>
  limits: Readonly<{ day: Limit; month: Limit; workout?: Limit }>; budget: BudgetState | null; top: readonly JournalRow[]; totals: JournalTotals
}>
export type JournalQuery = Readonly<{ userId: string; period: JournalPeriod; runId?: string | null; status?: RequestStatus | 'all'
  kind?: RequestKind | 'all'; cursor?: string | null; limit?: number; sinceMs?: number }>

const STATUSES = new Set(['ok', 'error', 'cancelled', 'refused', 'pending'])
const KINDS = new Set(['text', 'voice', 'prebuild', 'pack', 'scenario', 'summary', 'episode', 'judge'])
const ID = /^[a-zA-Z0-9_-]{1,128}$/

export class JournalError extends Error {}

const obj = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new JournalError('invalid_response')
  return value as Record<string, unknown>
}
const text = (value: unknown, max = 300): string | null => typeof value === 'string' && value.length <= max ? value : null
const num = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null
const count = (value: unknown): number => { const n = num(value); return n !== null && n >= 0 ? n : 0 }

function row(value: unknown): JournalRow {
  const r = obj(value)
  const id = text(r.id, 64), status = text(r.status, 16), kind = text(r.kind, 16), createdAt = num(r.createdAt)
  if (!id || !status || !STATUSES.has(status) || !kind || !KINDS.has(kind) || createdAt === null || (r.stage !== 'text' && r.stage !== 'voice'))
    throw new JournalError('invalid_response')
  return { id, group: text(r.group, 32) ?? id, runId: text(r.runId, 64) ?? '', createdAt, finishedAt: num(r.finishedAt), stage: r.stage,
    kind: kind as RequestKind, purpose: text(r.purpose, 16) ?? 'live', model: text(r.model, 80) ?? '', triggerId: text(r.triggerId, 8),
    task: text(r.task, 40), exerciseLabel: text(r.exerciseLabel, 80), setOrdinal: num(r.setOrdinal), status: status as RequestStatus,
    ledgerStatus: text(r.ledgerStatus, 16) ?? '', outcome: text(r.outcome, 24), errorCode: text(r.errorCode, 64),
    httpStatus: num(r.httpStatus), durationMs: num(r.durationMs), firstByteMs: num(r.firstByteMs), retry: r.retry === true,
    costMicros: count(r.costMicros), costSettled: r.costSettled === true }
}
function totals(value: unknown): JournalTotals {
  const t = obj(value)
  return { total: count(t.total), ok: count(t.ok), error: count(t.error), cancelled: count(t.cancelled), refused: count(t.refused),
    pending: count(t.pending), settledMicros: count(t.settledMicros), pendingMicros: count(t.pendingMicros), totalMicros: count(t.totalMicros),
    p50Ms: num(t.p50Ms), p95Ms: num(t.p95Ms), avgMicros: num(t.avgMicros) }
}
function spend(value: unknown): Readonly<Record<string, SpendEntry>> {
  const entries = Object.entries(obj(value)).slice(0, 32).map(([key, raw]) => {
    const e = obj(raw)
    return [key.slice(0, 80), { requests: count(e.requests), micros: count(e.micros), errors: count(e.errors), p95Ms: num(e.p95Ms), avgMicros: num(e.avgMicros) }] as const
  })
  return Object.fromEntries(entries)
}
function limit(value: unknown): Limit { const l = obj(value); return { usedMicros: count(l.usedMicros), capMicros: count(l.capMicros) } }
function budget(value: unknown): BudgetState | null {
  if (value === null || value === undefined) return null
  const b = obj(value)
  const purposes = Object.fromEntries(Object.entries(obj(b.byPurpose ?? {})).slice(0, 16).map(([k, v]) => [k.slice(0, 16), count(v)]))
  return { tier: Math.min(4, Math.max(0, Math.round(count(b.tier)))), liveAvailableMicros: count(b.liveAvailableMicros), liveShare: count(b.liveShare),
    summaryReserveMicros: count(b.summaryReserveMicros), byPurpose: purposes, avgRequestMicros: num(b.avgRequestMicros) }
}
export const parseBudget = budget

async function get(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`/api/coach/${path}`, { method: 'GET', credentials: 'include', signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new JournalError(response.status === 404 ? 'not_found' : 'request_failed')
  return response.json()
}
function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  return search.toString()
}
function periodParams(q: Pick<JournalQuery, 'userId' | 'period' | 'runId' | 'sinceMs'>) {
  if (!ID.test(q.userId)) throw new JournalError('request_failed')
  return { userId: q.userId, period: q.period, runId: q.period === 'run' ? q.runId ?? null : null,
    since: q.period === 'today' && q.sinceMs !== undefined ? (q.sinceMs / 1000).toFixed(3) : null }
}

export const coachJournalApi = {
  requests: async (q: JournalQuery, signal: AbortSignal): Promise<JournalPage> => {
    const body = obj(await get(`requests?${query({ ...periodParams(q), status: q.status ?? 'all', kind: q.kind ?? 'all',
      cursor: q.cursor ?? null, limit: q.limit ?? 50 })}`, signal))
    const rows = Array.isArray(body.rows) ? body.rows.slice(0, 200).map(row) : []
    return { rows, nextCursor: text(body.nextCursor, 120), totals: totals(body.totals) }
  },
  detail: async (userId: string, id: string, signal: AbortSignal): Promise<JournalDetail> => {
    if (!ID.test(userId) || !ID.test(id)) throw new JournalError('request_failed')
    const raw = obj(await get(`requests/${encodeURIComponent(id)}?${query({ userId })}`, signal))
    const usage = raw.usage && typeof raw.usage === 'object' && !Array.isArray(raw.usage)
      ? Object.fromEntries(Object.entries(raw.usage as Record<string, unknown>).slice(0, 16).map(([k, v]) => [k.slice(0, 40), num(v)])) : null
    return { ...row(raw), errorDetail: text(raw.errorDetail), textPreview: text(raw.textPreview), reserveMicros: count(raw.reserveMicros),
      settledMicros: num(raw.settledMicros), completeness: text(raw.completeness, 16), markupBytes: num(raw.markupBytes),
      textBytes: num(raw.textBytes), pricingVersion: text(raw.pricingVersion, 80), usage }
  },
  summary: async (q: Pick<JournalQuery, 'userId' | 'period' | 'runId' | 'sinceMs'>, signal: AbortSignal): Promise<UsageSummary> => {
    const params = periodParams(q)
    const body = obj(await get(`usage/summary?${query({ ...params, runId: q.runId ?? null })}`, signal))
    const limits = obj(body.limits)
    return { byKind: spend(body.byKind ?? {}), byModel: spend(body.byModel ?? {}),
      byPurpose: Object.fromEntries(Object.entries(obj(body.byPurpose ?? {})).slice(0, 16).map(([k, v]) => [k.slice(0, 16), count(v)])),
      limits: { day: limit(limits.day), month: limit(limits.month), ...(limits.workout ? { workout: limit(limits.workout) } : {}) },
      budget: budget(body.budget), top: Array.isArray(body.top) ? body.top.slice(0, 5).map(row) : [], totals: totals(body.totals) }
  },
}
