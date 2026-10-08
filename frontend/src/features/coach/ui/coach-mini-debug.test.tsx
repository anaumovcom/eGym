import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as Dialog from '@radix-ui/react-dialog'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/app-store'
import { machineScenarios } from '@/mocks/data'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import type { LocalAudioRuntimeSnapshot } from '../audio/local-audio-runtime'
import type { LocalAudioSnapshot } from '../audio/local-coach-audio-manager'
import { CoachLocalPreview, CoachMiniDebug, CoachNetworkDiagnostics } from './coach-mini-debug'

const mocks = vi.hoisted(() => ({
  target: null as HTMLElement | null,
  listeners: new Set<() => void>(),
  runtime: {
    subscribe: vi.fn(), getSnapshot: vi.fn(), refreshSavedPreferences: vi.fn(), getSavedPreferences: vi.fn(),
    setSavedCoachPreferences: vi.fn(), prepareTestClips: vi.fn(), playPreview: vi.fn(), stopPreview: vi.fn(),
  },
}))
vi.mock('../audio/local-audio-runtime', () => ({ localAudioRuntime: mocks.runtime }))
vi.mock('@/shared/ui/overlays/safety-dialog', async importOriginal => {
  const actual = await importOriginal<typeof import('@/shared/ui/overlays/safety-dialog')>()
  return { ...actual, useSafetyDockTarget: () => {
    const actualTarget = actual.useSafetyDockTarget()
    return mocks.target ?? actualTarget
  } }
})

const initialApp = useAppStore.getState()
const base: LocalAudioRuntimeSnapshot = {
  userId: 'actual-A', audio: null, prepared: { entries: 0, bytes: 0, loading: false },
  reason: 'disabled', previewAllowed: false, preferencesReady: false, preferencesLoading: false,
  paidRequests: 0, usage: { completeness: 'unavailable', tokens: null, costUsd: null, ledgerBound: false },
}
const audio: LocalAudioSnapshot = {
  pending: 1, active: 2, audible: 2, foreground: 'tone-3', startOrdinal: 3,
  utterances: [{ id: 'tone-3', scope: { schemaVersion: 1, userId: 'actual-A', runId: 'preview', exerciseId: 'test', setOrdinal: null, scopeEpoch: 0 },
    source: 'local', state: 'started', startOrdinal: 3, baseGain: 1, coefficient: .7, gain: .65, targetGain: .7, scheduledStartTime: 1 }],
  counters: { enqueued: 4, started: 3, finished: 1, cancelled: 0, rejected: 2 },
  lastActualSource: 'cache', contextState: 'running', volume: .63, muted: false, reason: 'started', disposed: false,
  timeline: Array.from({ length: 40 }, (_, index) => ({ atMs: index, reason: 'started' as const, startOrdinal: index, source: 'local' as const })),
}
function publish(snapshot: LocalAudioRuntimeSnapshot) {
  act(() => { mocks.runtime.getSnapshot.mockReturnValue(snapshot); mocks.listeners.forEach(listener => listener()) })
}
beforeEach(() => {
  vi.clearAllMocks(); mocks.target = null; mocks.listeners.clear()
  mocks.runtime.getSnapshot.mockReturnValue(base)
  mocks.runtime.getSavedPreferences.mockReturnValue(null)
  mocks.runtime.subscribe.mockImplementation((listener: () => void) => {
    mocks.listeners.add(listener); return () => { mocks.listeners.delete(listener) }
  })
  useAppStore.setState({ selectedUserId: 'actual-A' })
  vi.stubGlobal('fetch', vi.fn(() => { throw new Error('Diagnostics must not fetch') }))
})
afterEach(() => { cleanup(); useAppStore.setState(initialApp, true); vi.unstubAllGlobals() })

describe('CoachMiniDebug', () => {
  it.each([false, true])('anchors the native portal below the whole header, not the trigger row, compact=%s', hideNavigation => {
    render(<MemoryRouter><FormaShell machine={machineScenarios.ready} userName="Алексей" onStop={vi.fn()} hideNavigation={hideNavigation} /></MemoryRouter>)
    const trigger = screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' })
    const header = trigger.closest('header')!
    const measure = vi.spyOn(header, 'getBoundingClientRect').mockReturnValue(new DOMRect(24, 24, 600, 296))
    fireEvent.click(trigger)
    const popover = screen.getByRole('dialog', { name: 'Локальная диагностика AI-тренера' })
    expect(popover).toHaveStyle({ maxHeight: `${Math.min(640, window.innerHeight - 340)}px` })
    expect(header.contains(popover)).toBe(false)
    expect(popover.closest('[data-radix-popper-content-wrapper]')).not.toBeNull()
    measure.mockRestore()
  })
  it.each([false, true])('precedes motors in shell compact=%s and hydrates on mounted actual user changes only', async hideNavigation => {
    const user = userEvent.setup()
    const stop = vi.fn()
    render(<MemoryRouter><FormaShell machine={machineScenarios.ready} userName="Алексей" onStop={stop} hideNavigation={hideNavigation} /></MemoryRouter>)
    const trigger = screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' })
    const motor = screen.getByLabelText('Усилие на двигателях')
    expect(trigger.compareDocumentPosition(motor) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(mocks.runtime.refreshSavedPreferences).toHaveBeenCalledTimes(1)
    await user.click(trigger)
    expect(mocks.runtime.refreshSavedPreferences).toHaveBeenCalledTimes(1)
    act(() => useAppStore.setState({ selectedUserId: 'actual-B' }))
    expect(mocks.runtime.refreshSavedPreferences).toHaveBeenCalledTimes(2)
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'Аварийная остановка' }))
    expect(stop).toHaveBeenCalledOnce()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('opens read-only with keyboard, restores focus on Escape, and never fetches, hydrates, prepares or plays', async () => {
    const user = userEvent.setup()
    render(<CoachMiniDebug />)
    const trigger = screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' })
    trigger.focus(); await user.keyboard('{Enter}')
    const popover = screen.getByRole('dialog', { name: 'Локальная диагностика AI-тренера' })
    expect(within(popover).getByText(/Usage неизвестен/)).toBeVisible()
    expect(within(popover).queryByText(/0 tok|\$0|req/)).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
    expect(mocks.runtime.refreshSavedPreferences).not.toHaveBeenCalled()
    expect(mocks.runtime.prepareTestClips).not.toHaveBeenCalled()
    expect(mocks.runtime.playPreview).not.toHaveBeenCalled()
    expect(mocks.runtime.stopPreview).not.toHaveBeenCalled()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })
  it('subscribes to stable snapshots and shows actual counters, gains, source and only last 30 text-free timeline events', () => {
    render(<CoachMiniDebug />)
    fireEvent.click(screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' }))
    publish({ ...base, audio, reason: 'ready', previewAllowed: true, prepared: { entries: 2, bytes: 48000, loading: false } })
    expect(screen.getByText('Локальные старты').nextSibling).toHaveTextContent('3')
    expect(screen.getByText('CACHE')).toBeInTheDocument()
    expect(screen.getByText('2 / 2 / 1')).toBeInTheDocument()
    expect(screen.getByText('63% / нет')).toBeInTheDocument()
    expect(screen.getByText('2 / 48000')).toBeInTheDocument()
    expect(screen.getByText('4 / 1 / 0 / 2')).toBeInTheDocument()
    expect(screen.getByText(/base 1.000 · coef 0.700 · gain 0.650 → 0.700/)).toBeInTheDocument()
    const timeline = within(screen.getByRole('region', { name: 'Локальная шкала событий' })).getAllByRole('listitem')
    expect(timeline).toHaveLength(30)
    expect(timeline[0]).toHaveTextContent('10 мс · #10 · started')
    expect(timeline[29]).toHaveTextContent('39 мс · #39 · started')
    expect(timeline.every(item => !item.textContent?.includes('LOCAL'))).toBe(true)
    publish({ ...base, audio: { ...audio, lastActualSource: null } })
    expect(screen.queryByText('LOCAL')).not.toBeInTheDocument()
    expect(screen.queryByText('CACHE')).not.toBeInTheDocument()
    cleanup(); expect(mocks.listeners.size).toBe(0)
  })
  it('closes and disables during an active safety modal without portalling into its dock', () => {
    const view = render(<CoachMiniDebug />)
    fireEvent.click(screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    mocks.target = document.createElement('div'); document.body.append(mocks.target)
    view.rerender(<CoachMiniDebug />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const trigger = screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' })
    expect(trigger).toBeDisabled()
    fireEvent.click(trigger); expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mocks.target.childElementCount).toBe(0)
    mocks.target.remove(); mocks.target = null; view.rerender(<CoachMiniDebug />)
    expect(trigger).toBeEnabled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('permits read-only diagnostics when safety blocked without an active modal', () => {
    mocks.runtime.getSnapshot.mockReturnValue({ ...base, reason: 'safety' })
    render(<CoachMiniDebug />)
    fireEvent.click(screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' }))
    expect(screen.getByText('Блокировка безопасности')).toBeInTheDocument()
    expect(mocks.runtime.playPreview).not.toHaveBeenCalled()
  })
  it('keeps STOP in the real safety dialog dock, closes the coach popover and prevents reopening', async () => {
    const user = userEvent.setup()
    const stop = vi.fn()
    const fixture = (open: boolean) => <MemoryRouter>
      <FormaShell machine={machineScenarios.ready} userName="Алексей" onStop={stop} />
      <Dialog.Root open={open}><Dialog.Portal><SafetyDialogContent>
        <Dialog.Title>Безопасность</Dialog.Title><Dialog.Description>Проверка модального окна</Dialog.Description>
        <button type="button">Действие окна</button>
      </SafetyDialogContent></Dialog.Portal></Dialog.Root>
    </MemoryRouter>
    const view = render(fixture(false))
    await user.click(screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' }))
    view.rerender(fixture(true))
    expect(screen.queryByRole('dialog', { name: 'Локальная диагностика AI-тренера' })).not.toBeInTheDocument()
    const safety = screen.getByRole('dialog', { name: 'Безопасность' })
    const trigger = within(safety).getByRole('button', { name: 'AI-тренер: локальная диагностика' })
    expect(trigger).toBeDisabled()
    const stopButton = within(safety).getByRole('button', { name: 'Аварийная остановка' })
    expect(stopButton.closest('.forma-dialog-dock')).not.toBeNull()
    await user.click(stopButton); expect(stop).toHaveBeenCalledOnce()
    expect(mocks.runtime.playPreview).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
    view.rerender(fixture(false))
    expect(screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' })).toBeEnabled()
    expect(screen.queryByRole('dialog', { name: 'Локальная диагностика AI-тренера' })).not.toBeInTheDocument()
  })
  it.each(['audio_locked', 'suspended'] as const)('shows %s honestly rather than claiming playback', state => {
    mocks.runtime.getSnapshot.mockReturnValue({ ...base, reason: state === 'audio_locked' ? 'audio_locked' : 'ready',
      audio: state === 'suspended' ? { ...audio, contextState: 'suspended' } : null, previewAllowed: true })
    render(<CoachMiniDebug />)
    expect(screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' }).title).toContain('Звук заблокирован браузером')
  })
  it.each([
    [null, 'Выкл', 'off'], [{ enabled: true, mode: 'local' }, 'Local', 'local'],
    [{ enabled: true, mode: 'hybrid' }, 'Live', 'idle'], [{ enabled: true, mode: 'text-only' }, 'Text', 'idle'],
  ] as const)('shows the saved coach mode %o in the header', (saved, label, tone) => {
    mocks.runtime.getSavedPreferences.mockReturnValue(saved)
    render(<CoachMiniDebug />)
    const mode = screen.getByText(`AI · ${label}`)
    expect(mode).toHaveAttribute('data-tone', tone)
    expect(screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' }).title).toMatch(/^Режим: /)
  })
  it('shows today\'s paid requests and spend from the server ledger since local midnight when the coach is enabled', async () => {
    vi.stubEnv('VITE_COACH_ENABLED', 'true')
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ since: 0, requests: 7, settledMicros: 12_000, pendingMicros: 400, totalMicros: 12_400 }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    try {
      render(<CoachMiniDebug />)
      expect(await screen.findByText('7 запр.')).toBeInTheDocument()
      expect(screen.getByText('$0.012')).toBeInTheDocument()
      const trigger = screen.getByRole('button', { name: 'AI-тренер: локальная диагностика' })
      expect(trigger.title).toContain('Сегодня: 7 платн. запр. на $0.012 (из них в расчёте <$0.001)')
      const [url] = fetchMock.mock.calls[0] as unknown as [string]
      const midnight = new Date(); midnight.setHours(0, 0, 0, 0)
      expect(url).toBe(`/api/coach/usage/today?since=${(midnight.getTime() / 1000).toFixed(3)}`)
    } finally { vi.unstubAllEnvs() }
  })
})

describe('CoachLocalPreview', () => {
  it('disables preparation and previews according to runtime while keeping stop available', () => {
    render(<CoachLocalPreview />)
    for (const name of ['Подготовить тестовые клипы', 'Тестовый тон', 'Перекрытие трёх тонов']) {
      const button = screen.getByRole('button', { name }); expect(button).toBeDisabled(); fireEvent.click(button)
    }
    expect(mocks.runtime.prepareTestClips).not.toHaveBeenCalled()
    expect(mocks.runtime.playPreview).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Остановить тест' }))
    expect(mocks.runtime.stopPreview).toHaveBeenCalledOnce()
  })
  it('calls preview synchronously in the gesture handler; prepare never calls play and state updates can revoke admission', () => {
    mocks.runtime.getSnapshot.mockReturnValue({ ...base, reason: 'ready', previewAllowed: true })
    render(<CoachLocalPreview />)
    let inGesture = false
    mocks.runtime.playPreview.mockImplementation(() => { expect(inGesture).toBe(true); return Promise.resolve(true) })
    fireEvent.click(screen.getByRole('button', { name: 'Подготовить тестовые клипы' }))
    expect(mocks.runtime.prepareTestClips).toHaveBeenCalledOnce()
    expect(mocks.runtime.playPreview).not.toHaveBeenCalled()
    inGesture = true
    fireEvent.click(screen.getByRole('button', { name: 'Тестовый тон' }))
    fireEvent.click(screen.getByRole('button', { name: 'Перекрытие трёх тонов' }))
    inGesture = false
    expect(mocks.runtime.playPreview.mock.calls).toEqual([['single'], ['overlap']])
    publish({ ...base, reason: 'safety' })
    expect(screen.getByRole('button', { name: 'Тестовый тон' })).toBeDisabled()
    expect(screen.getAllByText(/не выбранный голос/)).toHaveLength(2)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('network diagnostics show ledger usage and decisions and copy a redacted report', async () => {
    const writeText = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    render(<CoachNetworkDiagnostics snapshot={{ state: 'ready', reason: null, mode: 'hybrid', voiceId: 'ash', text: true, voice: true,
      degraded: false, eventsSent: 3, streams: 1, spoken: 1, failed: 0, firstAudioMs: 640, lastText: 'Отличный подход',
      reasons: { pipeline_busy: 1 }, usage: { requests: 2, settledMicros: 12_340, pendingMicros: 0, capMicros: 2_000_000, limitKind: 'strict-reservations' },
      decisions: [{ atMs: 1, triggerId: 'T21', action: 'silence', reason: 'pipeline_busy', text: null }] }} />)
    expect(screen.getByText('$0.0123 / $0.0000 / $2.0000 · 2 запр.')).toBeVisible()
    expect(screen.getByText(/T21 · silence · Тренер уже говорит/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Скопировать отчёт' }))
    expect(writeText).toHaveBeenCalledOnce()
    const report = (writeText.mock.calls[0] as unknown as [string])[0]
    expect(report).not.toContain('Отличный подход')
    expect(await screen.findByRole('status')).toHaveTextContent('Отчёт скопирован')
  })
})