import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { JournalRow } from '../lib/diagnostics-api'
import { CoachRequestsTab, CoachSpendTab, errorText, groupRows, money } from './coach-requests-panel'

const now = Date.now() / 1000
function row(overrides: Partial<JournalRow>): JournalRow {
  return { id: 'a1', group: 'g1', runId: 'run-1', createdAt: now - 30, finishedAt: now - 29, stage: 'text', kind: 'text', purpose: 'live',
    model: 'gpt-6-luna', triggerId: 'T36', task: 'rest/full-feedback', exerciseLabel: 'Тяга сверху', setOrdinal: 2, status: 'ok',
    ledgerStatus: 'settled', outcome: 'speech', errorCode: null, httpStatus: null, durationMs: 1800, firstByteMs: null, retry: false,
    costMicros: 700, costSettled: true, ...overrides }
}
const totals = { total: 4, ok: 2, error: 1, cancelled: 0, refused: 1, pending: 0, settledMicros: 13_000, pendingMicros: 0,
  totalMicros: 13_000, p50Ms: 900, p95Ms: 2100, avgMicros: 4300 }
const rows = [
  row({ id: 'v1', stage: 'voice', kind: 'voice', model: 'drama-3', outcome: 'spoken', costMicros: 12_000, durationMs: 2500, firstByteMs: 450 }),
  row({ id: 't1' }),
  row({ id: 'e1', group: 'g2', createdAt: now - 10, status: 'error', outcome: 'error', errorCode: 'provider_error', httpStatus: 429,
    ledgerStatus: 'unsettled', costMicros: 300, triggerId: 'T21', task: 'active/support' }),
  row({ id: 'r1', group: 'r1', createdAt: now - 5, status: 'refused', outcome: 'refused', errorCode: 'budget', costMicros: 0, ledgerStatus: 'refused' }),
]

function respond(body: unknown) { return Promise.resolve(new Response(JSON.stringify(body), { status: 200 })) }
let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  fetchMock = vi.fn((url: string) => {
    if (url.startsWith('/api/coach/requests/e1')) return respond({ ...rows[2], errorDetail: 'rate_limit: Slow down', textPreview: null,
      reserveMicros: 900, settledMicros: null, completeness: 'unavailable', markupBytes: null, textBytes: null, pricingVersion: 'p1', usage: null })
    if (url.startsWith('/api/coach/requests')) return respond({ rows: url.includes('status=error') ? [rows[2]] : rows, nextCursor: null, totals })
    if (url.startsWith('/api/coach/usage/summary')) return respond({
      byKind: { voice: { requests: 1, micros: 12_000, errors: 0, p95Ms: 2500, avgMicros: 12_000 } }, byModel: {},
      byPurpose: { live: 12_000, summary: 700 }, limits: { day: { usedMicros: 2_000_000, capMicros: 20_000_000 },
        month: { usedMicros: 5_000_000, capMicros: 100_000_000 }, workout: { usedMicros: 1_900_000, capMicros: 2_000_000 } },
      budget: { tier: 3, liveAvailableMicros: 0, liveShare: 0.05, summaryReserveMicros: 200_000, byPurpose: {}, avgRequestMicros: 9000 },
      top: [rows[0]], totals })
    return Promise.reject(new Error(`unexpected ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('journal helpers', () => {
  it('groups a line\'s text and voice into one row with the summed cost and worst status', () => {
    const groups = groupRows(rows)
    expect(groups.map(group => group.key)).toEqual(['r1', 'run-1:g2', 'run-1:g1'])
    const line = groups[2]
    expect(line.steps.map(step => step.stage)).toEqual(['text', 'voice'])
    expect(line.costMicros).toBe(12_700)
    expect(line.durationMs).toBe(4300)
    expect(groupRows([rows[1], { ...rows[0], status: 'error' }])[0].status).toBe('error')
  })
  it('explains error codes in Russian', () => {
    expect(errorText('provider_error', 429)).toBe('Ошибка провайдера · HTTP 429')
    expect(errorText('validation_failed:number')).toBe('Текст отклонён проверкой: лишнее или неверное число')
    expect(errorText('http-402', 402)).toBe('Нет средств на счёте провайдера')
    expect(errorText(null)).toBeNull()
    expect(money(0)).toBe('$0'); expect(money(12_345)).toBe('$0.012'); expect(money(1_234)).toBe('$0.0012'); expect(money(1_234_000)).toBe('$1.23')
  })
})

describe('CoachRequestsTab', () => {
  it('lists requests newest first, marks errors red with their reason and opens the provider message', async () => {
    const onSeen = vi.fn()
    render(<CoachRequestsTab userId="alexey" runId="run-1" onSeen={onSeen} />)
    const list = await screen.findByRole('list')
    const items = await within(list).findAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveAttribute('data-status', 'refused')
    expect(items[1]).toHaveAttribute('data-status', 'error')
    expect(within(items[1]).getByText('Ошибка провайдера · HTTP 429')).toBeInTheDocument()
    expect(within(items[2]).getByText('Результат подхода')).toBeInTheDocument()
    expect(within(items[2]).getByText('$0.013')).toBeInTheDocument()
    expect(screen.getByText('Всего 4')).toBeInTheDocument()
    expect(onSeen).toHaveBeenCalled()
    fireEvent.click(within(items[1]).getByRole('button', { expanded: false }))
    expect(await screen.findByText('rate_limit: Slow down')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Скопировать ошибку' })).toBeInTheDocument()
    const [firstUrl] = fetchMock.mock.calls[0] as [string]
    expect(firstUrl).toContain('period=run') && expect(firstUrl).toContain('runId=run-1')
  })
  it('filters to errors from the summary button', async () => {
    render(<CoachRequestsTab userId="alexey" runId={null} />)
    fireEvent.click(await screen.findByRole('button', { name: '✕ 1' }))
    await act(async () => { await Promise.resolve() })
    const urls = fetchMock.mock.calls.map(call => call[0] as string)
    expect(urls.some(url => url.includes('status=error') && url.includes('period=today'))).toBe(true)
  })
})

describe('CoachSpendTab', () => {
  it('shows the three limits, the degradation tier and a forecast', async () => {
    render(<CoachSpendTab userId="alexey" runId="run-1" setsDone={4} setsLeft={4} />)
    expect(await screen.findByText('Только результаты')).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Тренировка' })).toHaveAttribute('aria-valuenow', '1900000')
    expect(screen.getByText('Сутки (все тренировки)')).toBeInTheDocument()
    expect(screen.getByText(/≈ \$3\.80 · выше лимита/)).toBeInTheDocument()
    expect(screen.getByText('Итоги')).toBeInTheDocument()
  })
})
