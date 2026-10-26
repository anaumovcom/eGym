import * as Popover from '@radix-ui/react-popover'
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useSafetyDockTarget } from '@/shared/ui/overlays/safety-dialog'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import { localAudioRuntime, type LocalAudioRuntimeSnapshot } from '../audio/local-audio-runtime'
import type { LocalAudioSnapshot } from '../audio/local-coach-audio-manager'
import { coachLiveRuntime, coachNetworkClient, type LiveRuntimeSnapshot } from '../live/coach-live-runtime'
import { redactedNetworkReport, type NetworkSnapshot } from '../live/coach-network-client'
import { coachSettingsApi, type DailyUsage } from '../lib/settings-api'
import type { CoachPreferences } from '../model/preferences'
import { CoachRequestsTab, CoachSpendTab, errorText, money, useUnseenErrors } from './coach-requests-panel'
import { networkStates, reasonLabel } from './coach-labels'
import { CoachOverview, CoachStatusTab, coachOverview, type Tile } from './coach-panel-overview'
import './coach-mini-debug.css'

const modeLabels: Readonly<Record<CoachPreferences['mode'], string>> = { local: 'Local', hybrid: 'Live', 'text-only': 'Text' }
const modeTitles: Readonly<Record<CoachPreferences['mode'], string>> = { local: 'локальные клипы', hybrid: 'гибрид, живой голос', 'text-only': 'только текст' }
type ModeTone = 'off' | 'local' | 'idle' | 'pending' | 'live' | 'error'
const networkTones: Readonly<Record<NetworkSnapshot['state'], ModeTone>> = {
  off: 'idle', creating: 'pending', connecting: 'pending', retrying: 'pending', ready: 'live', refused: 'error',
}
/** Saved coach mode plus, for network modes, the live connection state as a tone. */
function coachMode(saved: CoachPreferences | null, network: NetworkSnapshot | null | undefined) {
  if (!saved?.enabled) return { label: 'Выкл', tone: 'off' as ModeTone, title: 'Режим: выключен' }
  const title = `Режим: ${modeLabels[saved.mode]} (${modeTitles[saved.mode]})`
  if (saved.mode === 'local') return { label: modeLabels.local, tone: 'local' as ModeTone, title }
  const state = network?.state ?? 'off'
  return { label: modeLabels[saved.mode], tone: networkTones[state], title: `${title} · сеть: ${networkStates[state]}` }
}
const usd = (micros: number) => `$${(micros / 1_000_000).toFixed(4)}`
const dayUsd = (micros: number) => micros === 0 ? '$0' : micros < 1_000 ? '<$0.001' : `$${(micros / 1_000_000).toFixed(micros < 10_000_000 ? 3 : 2)}`
const DAILY_USAGE_EVERY_MS = 60_000

/** Today's paid requests (since local midnight) from the server ledger; refreshed on live usage changes and every minute. */
function useDailyUsage(refreshKey: string): DailyUsage | null {
  const [usage, setUsage] = useState<DailyUsage | null>(null)
  useEffect(() => {
    if (import.meta.env.VITE_COACH_ENABLED !== 'true') return
    const controller = new AbortController()
    const load = () => {
      const midnight = new Date()
      midnight.setHours(0, 0, 0, 0)
      coachSettingsApi.dailyUsage(midnight.getTime(), controller.signal).then(setUsage, () => undefined)
    }
    load()
    const timer = setInterval(load, DAILY_USAGE_EVERY_MS)
    return () => { controller.abort(); clearInterval(timer) }
  }, [refreshKey])
  return usage
}

/** E10/E11 live network path: connection, decisions, usage from the ledger. Never shows tokens. */
export function CoachNetworkDiagnostics({ snapshot }: { snapshot: NetworkSnapshot }) {
  const [notice, setNotice] = useState<string | null>(null)
  const copy = () => {
    const report = redactedNetworkReport(snapshot)
    void navigator.clipboard?.writeText(report).then(() => setNotice('Отчёт скопирован (без текстов и ID)'), () => setNotice('Буфер обмена недоступен'))
  }
  const forget = () => {
    void coachNetworkClient.forgetMemory().then(cleared => setNotice(cleared === null ? 'Не удалось очистить память' : `Память разговора очищена (${cleared})`))
  }
  const usage = snapshot.usage
  return <section className="coach-local-diagnostics" aria-label="Сетевой тренер">
    <h4>Сеть · E10</h4>
    <dl className="coach-local-metrics">
      <div><dt>Состояние</dt><dd>{networkStates[snapshot.state]}{snapshot.reason ? ` · ${reasonLabel(snapshot.reason)}` : ''}</dd></div>
      <div><dt>Режим / голос</dt><dd>{snapshot.mode ?? '—'} / {snapshot.voiceId ?? '—'}{snapshot.degraded ? ' · деградация' : ''}</dd></div>
      <div><dt>События / потоки / сказано / сбои</dt><dd>{`${snapshot.eventsSent} / ${snapshot.streams} / ${snapshot.spoken} / ${snapshot.failed}`}</dd></div>
      <div><dt>Голос → первый PCM</dt><dd>{snapshot.firstAudioMs === null ? '—' : `${snapshot.firstAudioMs} мс (последний)`}</dd></div>
      {Object.entries(snapshot.latencies).filter(([key]) => key.startsWith('eventToPlaybackStart:')).map(([key, metric]) =>
        <div key={key} title={key}><dt>Событие → старт · {key.split(':')[1]} · p95</dt><dd>{`${metric.p95} мс · n=${metric.count}`}</dd></div>)}
      <div><dt>Расход (settled / pending / cap)</dt><dd>{usage ? `${usd(usage.settledMicros)} / ${usd(usage.pendingMicros)} / ${usd(usage.capMicros)} · ${usage.requests} запр.` : '—'}</dd></div>
      {snapshot.lastText && <div><dt>Последний текст</dt><dd>{snapshot.lastText}</dd></div>}
    </dl>
    {!!snapshot.decisions.length && <ol className="coach-local-timeline">{snapshot.decisions.slice(-10).map((item, index) =>
      <li key={index}>{item.triggerId ?? '—'} · {item.action}{item.reason ? ` · ${reasonLabel(item.reason)}` : ''}</li>)}</ol>}
    <div className="coach-local-actions">
      <button type="button" className="rt-button" onClick={copy}>Скопировать отчёт</button>
      <button type="button" className="rt-button" disabled={snapshot.state === 'off'} onClick={forget}>Забыть разговор</button>
    </div>
    {notice && <p className="coach-local-note" role="status">{notice}</p>}
  </section>
}

/** E06 interpreter: phase, latest cue and recent skips. Local only, no provider. */
export function CoachLiveDiagnostics({ snapshot }: { snapshot: LiveRuntimeSnapshot }) {
  const interpreter = snapshot.interpreter
  return <section className="coach-local-diagnostics" aria-label="Интерпретатор тренировки">
    <h4>Интерпретатор · E06</h4>
    <dl className="coach-local-metrics">
      <div><dt>Фаза</dt><dd>{interpreter?.phase ?? 'не запущен'}</dd></div>
      <div><dt>Источник свежий</dt><dd>{interpreter ? interpreter.fresh ? 'да' : 'нет' : '—'}</dd></div>
      <div><dt>Блокировки</dt><dd>{interpreter?.latches.map(reasonLabel).join(', ') || (interpreter?.pain ? 'боль' : '—')}</dd></div>
      <div><dt>Последняя фраза</dt><dd>{snapshot.lastCue ? `${snapshot.lastCue.triggerId} · ${snapshot.lastCue.clipId ?? '—'} · ${reasonLabel(snapshot.lastCue.reason)}` : '—'}</dd></div>
      <div><dt>Поводы / приняты / нет клипа / подавлены</dt><dd>{`${snapshot.counters.cues} / ${snapshot.counters.admitted} / ${snapshot.counters.missingClip} / ${snapshot.counters.suppressed}`}</dd></div>
    </dl>
    {!!interpreter?.skips.length && <ol className="coach-local-timeline">{interpreter.skips.slice(-10).map((item, index) => <li key={index}>{item.triggerId} · {reasonLabel(item.reason)}</li>)}</ol>}
  </section>
}

/** Only runtime/manager observations; never lifecycle event.source or provider estimates. */
export function CoachLocalDiagnostics({ snapshot, audio = snapshot.audio, reason = snapshot.reason, live = false }: {
  snapshot: LocalAudioRuntimeSnapshot; audio?: LocalAudioSnapshot | null; reason?: string; live?: boolean
}) {
  const foreground = audio?.utterances.find(item => item.id === audio.foreground)?.startOrdinal
  return <div className="coach-local-diagnostics">
    <p className="coach-local-reason">{reasonLabel(reason)} <code>{reason}</code></p>
    <dl className="coach-local-metrics">
      <div><dt>Последний фактический источник</dt><dd>{audio?.lastActualSource?.toUpperCase() ?? '—'}</dd></div>
      <div><dt>{live ? 'Старты тренировочного микшера' : 'Локальные старты'}</dt><dd>{audio?.counters.started ?? 0}</dd></div>
      <div><dt>Активные / слышимые / ожидающие</dt><dd>{audio ? `${audio.active} / ${audio.audible} / ${audio.pending}` : '—'}</dd></div>
      <div><dt>Передний план · номер старта</dt><dd>{foreground ?? '—'}</dd></div>
      <div><dt>AudioContext</dt><dd>{audio?.contextState ?? 'Не наблюдался'}</dd></div>
      <div><dt>Громкость / mute</dt><dd>{audio ? `${Math.round(audio.volume * 100)}% / ${audio.muted ? 'да' : 'нет'}` : '—'}</dd></div>
      <div><dt>Подготовленные клипы / байты</dt><dd>{snapshot.prepared.entries} / {snapshot.prepared.bytes}{snapshot.prepared.loading ? ' · декодирование…' : ''}</dd></div>
      <div><dt>Сохранённые настройки</dt><dd>{snapshot.preferencesLoading ? 'Загрузка' : snapshot.preferencesReady ? 'Получены' : 'Не получены'}</dd></div>
      <div><dt>Enqueued / finished / cancelled / rejected</dt><dd>{audio ? `${audio.counters.enqueued} / ${audio.counters.finished} / ${audio.counters.cancelled} / ${audio.counters.rejected}` : '—'}</dd></div>
      <div><dt>Причина менеджера</dt><dd>{audio?.reason ?? '—'}</dd></div>
    </dl>
    <p className="coach-local-note">{live ? 'Микшер тренировки: live-речь и локальные фразы. Расход показан в разделе «Сеть».' : 'Платная генерация отсутствует в локальном тесте. Usage неизвестен для локальных клипов; расход live-тренера показан в разделе «Сеть».'}</p>
    <p className="coach-local-note">{live ? 'Старты наблюдаются по времени AudioContext, не подтверждают звук на устройстве.' : 'Старты наблюдаются по времени AudioContext, не подтверждают звук на устройстве. Только тестовые тоны, не выбранный голос.'}</p>
    {audio && audio.utterances.length > 0 && <section aria-label="Коэффициенты микшера">
      <h4>Коэффициенты микшера</h4>
      <ul>{audio.utterances.map((item, index) => <li key={item.id}>#{item.startOrdinal ?? `ожидание ${index + 1}`} · {item.state} · base {item.baseGain.toFixed(3)} · coef {item.coefficient.toFixed(3)} · gain {item.gain.toFixed(3)} → {item.targetGain.toFixed(3)}</li>)}</ul>
    </section>}
    <section aria-label="Локальная шкала событий">
      <h4>Последние события · до 30</h4>
      <ol className="coach-local-timeline">{audio?.timeline.slice(-30).map((event, index) => <li key={index}>{Math.round(event.atMs)} мс · #{event.startOrdinal} · {event.reason}</li>)}</ol>
      {!audio?.timeline.length && <p className="coach-local-note">Событий менеджера пока нет.</p>}
    </section>
  </div>
}

export function CoachLocalPreview() {
  const snapshot = useSyncExternalStore(localAudioRuntime.subscribe, localAudioRuntime.getSnapshot, localAudioRuntime.getSnapshot)
  return <section className="coach-local-preview" aria-label="Локальный тест звука">
    <h3>Локальный тест звука · E05</h3>
    <p className="coach-local-note">Бесплатные тестовые тоны, не выбранный голос. Подготовка только декодирует клипы: без воспроизведения и без платных запросов. Допуск определяется сохранёнными, а не черновыми настройками.</p>
    <div className="coach-local-actions">
      <button type="button" className="rt-button" disabled={!snapshot.previewAllowed || snapshot.prepared.loading} onClick={() => { void localAudioRuntime.prepareTestClips() }}>Подготовить тестовые клипы</button>
      <button type="button" className="rt-button" disabled={!snapshot.previewAllowed} onClick={() => { void localAudioRuntime.playPreview('single') }}>Тестовый тон</button>
      <button type="button" className="rt-button" disabled={!snapshot.previewAllowed} onClick={() => { void localAudioRuntime.playPreview('overlap') }}>Перекрытие трёх тонов</button>
      <button type="button" className="rt-button" onClick={() => localAudioRuntime.stopPreview()}>Остановить тест</button>
    </div>
    <CoachLocalDiagnostics snapshot={snapshot} />
  </section>
}

type PanelTab = 'requests' | 'spend' | 'status'
const TAB_KEY = 'coach-panel-tab'
const TABS: ReadonlyArray<readonly [PanelTab, string]> = [['requests', 'Запросы'], ['spend', 'Расход'], ['status', 'Состояние']]
function readTab(): PanelTab {
  try { const value = localStorage.getItem(TAB_KEY); return value === 'spend' || value === 'status' ? value : 'requests' } catch { return 'requests' }
}

/** Workout progress for the spend forecast: sets saved so far and sets still planned. */
function useSetProgress(): { done: number; left: number } {
  const session = useRuntimeStore(state => state.session)
  if (!session) return { done: 0, left: 0 }
  const done = Object.values(session.completedSets).reduce((sum, list) => sum + list.length, 0)
  const planned = session.exercises.reduce((sum, exercise) => sum + exercise.plan.length, 0)
  return { done, left: Math.max(0, planned - done) }
}

export function CoachMiniDebug() {
  const snapshot = useSyncExternalStore(localAudioRuntime.subscribe, localAudioRuntime.getSnapshot, localAudioRuntime.getSnapshot)
  const live = useSyncExternalStore(coachLiveRuntime.subscribe, coachLiveRuntime.getSnapshot, coachLiveRuntime.getSnapshot)
  const userId = useAppStore(state => state.selectedUserId)
  const runUsage = live.network?.usage
  const runId = live.network?.runId ?? null
  const usageKey = runUsage ? `${runUsage.requests}:${runUsage.settledMicros}:${runUsage.pendingMicros}` : ''
  const daily = useDailyUsage(usageKey)
  const coachEnabled = import.meta.env.VITE_COACH_ENABLED === 'true'
  const errors = useUnseenErrors(userId, runId, coachEnabled, usageKey)
  const progress = useSetProgress()
  const dailyText = daily ? `Сегодня: ${daily.requests} платн. запр. на ${dayUsd(daily.totalMicros)}${daily.pendingMicros ? ` (из них в расчёте ${dayUsd(daily.pendingMicros)})` : ''}` : null
  const workoutSpend = runUsage && runId ? runUsage.settledMicros + runUsage.pendingMicros : null
  const workoutText = runUsage && workoutSpend !== null ? `Тренировка: ${runUsage.requests} запр. на ${money(workoutSpend)} из ${money(runUsage.capMicros)}` : null
  const share = runUsage && workoutSpend !== null && runUsage.capMicros > 0 ? Math.min(1, workoutSpend / runUsage.capMicros) : null
  const target = useSafetyDockTarget()
  const [open, setOpen] = useState(false)
  const [tab, setTabState] = useState<PanelTab>(readTab)
  const setTab = (value: PanelTab) => { setTabState(value); try { localStorage.setItem(TAB_KEY, value) } catch { /* convenience only */ } }
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [availableHeight, setAvailableHeight] = useState(0)
  const anchorRef = useRef({
    getBoundingClientRect: () => {
      const trigger = triggerRef.current
      const dockElement = trigger?.closest('.forma-system-dock')
      const dock = dockElement?.getBoundingClientRect()
      const header = trigger?.closest('header')?.getBoundingClientRect()
      // Normal headers use display: contents for the dock, so its own rect
      // can be empty. Include all controls as well as the enclosing header.
      const controls = [...(dockElement?.children ?? [])].map(element => element.getBoundingClientRect())
      const bottom = Math.max(dock?.bottom ?? 0, header?.bottom ?? trigger?.getBoundingClientRect().bottom ?? 0, ...controls.map(rect => rect.bottom))
      const panelWidth = Math.min(560, window.innerWidth - 24)
      // Reserve the ENTIRE wrapped header/dock, not just the AI trigger's row.
      // Clamp the end-aligned virtual anchor horizontally before Radix places it.
      const right = Math.min(window.innerWidth - 12, Math.max(panelWidth + 12, dock?.right || header?.right || window.innerWidth - 12))
      return new DOMRect(right, bottom, 0, 0)
    },
  })
  useLayoutEffect(() => {
    if (!open || target !== null) return
    const update = () => setAvailableHeight(Math.max(0, window.innerHeight - anchorRef.current.getBoundingClientRect().bottom - 20))
    update()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    const trigger = triggerRef.current
    for (const element of [trigger?.closest('.forma-system-dock'), trigger?.closest('header')]) {
      if (element) observer?.observe(element)
    }
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [open, target])
  useEffect(() => { if (target !== null) setOpen(false) }, [target])
  const locked = snapshot.reason === 'audio_locked' || (snapshot.previewAllowed && snapshot.audio?.contextState === 'suspended')
  const mode = coachMode(localAudioRuntime.getSavedPreferences(), live.network)
  const latestError = errors.latest ? `Последняя ошибка: ${errorText(errors.latest.errorCode, errors.latest.httpStatus)}` : null
  const title = [mode.title, reasonLabel(locked ? 'audio_locked' : snapshot.reason), workoutText, dailyText, latestError].filter(Boolean).join(' · ')
  const journal = coachEnabled && !!userId
  const activeTab: PanelTab = journal ? tab : 'status'
  const markSeen = errors.markSeen
  const technical = <>
    <CoachLocalDiagnostics snapshot={snapshot} audio={live.audio ?? snapshot.audio} reason={live.audio ? live.reason : snapshot.reason} live={!!live.audio} />
    <CoachLiveDiagnostics snapshot={live} />
    {live.network && <CoachNetworkDiagnostics snapshot={live.network} />}
  </>
  const overview = coachOverview({ liveBuild: coachEnabled, saved: localAudioRuntime.getSavedPreferences(), network: live.network,
    reason: locked ? 'audio_locked' : live.audio ? live.reason : snapshot.reason, workout: !!runId || !!live.audio,
    latches: live.interpreter?.latches })
  const inWorkout = !!(runUsage && runId)
  const tiles: Tile[] = journal ? [
    { label: inWorkout ? 'запросов за тренировку' : 'запросов сегодня', value: String(inWorkout ? runUsage.requests : daily?.requests ?? 0),
      onClick: () => setTab('requests') },
    { label: inWorkout ? 'потрачено за тренировку' : 'потрачено сегодня', onClick: () => setTab('spend'),
      value: inWorkout && workoutSpend !== null ? money(workoutSpend) : daily ? dayUsd(daily.totalMicros) : '$0',
      hint: inWorkout ? `лимит ${money(runUsage.capMicros)}` : undefined,
      tone: share !== null && share > 0.9 ? 'error' : share !== null && share > 0.7 ? 'warn' : undefined },
    { label: errors.unseen ? 'новых ошибок' : 'ошибок нет', value: String(errors.unseen), tone: errors.unseen ? 'error' : 'ok',
      hint: errors.latest ? errorText(errors.latest.errorCode, errors.latest.httpStatus) ?? undefined : undefined, onClick: () => setTab('requests') },
  ] : []
  return <Popover.Root open={open && target === null} onOpenChange={value => setOpen(target === null && value)}>
    <Popover.Trigger asChild>
      <button ref={triggerRef} type="button" className="coach-mini-debug-trigger" disabled={target !== null} aria-label="AI-тренер: состояние и расход" title={title}
        data-budget={share === null ? undefined : share > 0.9 ? 'high' : share > 0.7 ? 'mid' : 'low'}
        style={share === null ? undefined : { ['--coach-budget' as string]: String(share) }}>
        <span className="coach-mini-debug-mode" data-tone={mode.tone}>AI · {mode.label}</span>
        {coachEnabled && <>
          <span className="coach-mini-debug-requests">
            {runUsage && runId ? `${runUsage.requests} запр.` : daily ? `${daily.requests} запр.` : '—'}
            {errors.unseen > 0 && <span className="coach-mini-debug-errors" aria-label={`Новых ошибок: ${errors.unseen}`}>⚠ {errors.unseen}</span>}
          </span>
          <span>{workoutSpend !== null && runUsage ? `${money(workoutSpend)} / ${money(runUsage.capMicros)}` : daily ? dayUsd(daily.totalMicros) : '—'}</span>
        </>}
      </button>
    </Popover.Trigger>
    {/* Register after Trigger: its initial implicit anchor must not overwrite
      the virtual anchor before Radix recognizes the custom anchor. */}
    <Popover.Anchor virtualRef={anchorRef} />
    <Popover.Portal>
        {/* Never flip/shift into the protected header. Width and remaining height
          are constrained instead; Radix still owns placement, portal and focus. */}
        <Popover.Content className="coach-mini-debug-popover" style={{ maxHeight: Math.min(760, availableHeight) }} aria-label="Панель AI-тренера" side="bottom" align="end" sideOffset={8} avoidCollisions={false} updatePositionStrategy="always" onCloseAutoFocus={event => { if (target !== null) event.preventDefault() }}>
        <header><h3>AI-тренер</h3><Popover.Close aria-label="Закрыть панель AI-тренера">×</Popover.Close></header>
        <CoachOverview overview={overview} tiles={tiles} />
        {journal && <div className="coach-panel-tabs" role="tablist" aria-label="Разделы диагностики">
          {TABS.map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={activeTab === id} id={`coach-tab-${id}`}
            onClick={() => setTab(id)}>{label}{id === 'requests' && errors.unseen > 0 ? <span className="coach-mini-debug-errors">⚠ {errors.unseen}</span> : null}</button>)}
        </div>}
        <div role={journal ? 'tabpanel' : undefined} aria-labelledby={journal ? `coach-tab-${activeTab}` : undefined}>
          {activeTab === 'requests' && userId && <CoachRequestsTab userId={userId} runId={runId} onSeen={markSeen} />}
          {activeTab === 'spend' && userId && <CoachSpendTab userId={userId} runId={runId} setsDone={progress.done} setsLeft={progress.left} />}
          {activeTab === 'status' && <CoachStatusTab local={snapshot} live={live} liveBuild={coachEnabled} technical={technical} />}
        </div>
      </Popover.Content>
    </Popover.Portal>
  </Popover.Root>
}
