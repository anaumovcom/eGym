import * as Popover from '@radix-ui/react-popover'
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useSafetyDockTarget } from '@/shared/ui/overlays/safety-dialog'
import { localAudioRuntime, type LocalAudioRuntimeSnapshot } from '../audio/local-audio-runtime'
import { coachLiveRuntime, coachNetworkClient, type LiveRuntimeSnapshot } from '../live/coach-live-runtime'
import { redactedNetworkReport, type NetworkSnapshot } from '../live/coach-network-client'
import { coachSettingsApi, type DailyUsage } from '../lib/settings-api'
import type { CoachPreferences } from '../model/preferences'
import './coach-mini-debug.css'

const reasons: Readonly<Record<string, string>> = {
  ready: 'Локальный тест готов', disabled: 'Выключен', audio_locked: 'Звук заблокирован браузером',
  safety: 'Блокировка безопасности', hardware_active: 'Тренажёр активен', runtime_session: 'Идёт тренировка',
  mute: 'Звук выключен', hidden: 'Вкладка скрыта', no_user: 'Пользователь не выбран',
  preferences_loading: 'Ожидание сохранённых настроек', preferences_unavailable: 'Настройки недоступны',
  no_consent: 'Нет согласия', unavailable: 'Аудиоконтекст недоступен', decode_failed: 'Ошибка декодирования',
  cancelled: 'Тест остановлен', scope_changed: 'Контекст изменён', missing_clip: 'Фраза не подготовлена',
  admitted: 'Фраза принята', idle: 'Ожидание', stale_source: 'Данные тренажёра устарели', mock_source: 'Не реальный источник',
  owner_mismatch: 'Тренажёр у другого пользователя', expired: 'Опоздало', no_source: 'Нет источника',
  pipeline_busy: 'Тренер уже говорит', provider_unavailable: 'Провайдер недоступен', stale_run: 'Настройки изменились, переподключение',
  local_mode: 'Сервер в локальном режиме', coach_disabled: 'Тренер выключен на сервере (COACH_ENABLED)', run_not_found: 'Ledger не найден', budget: 'Лимит бюджета', degraded: 'Только локальные клипы',
  no_useful_content: 'Нечего сказать', validation_failed: 'Текст отклонён проверкой', closed: 'Соединение закрыто', network: 'Сеть недоступна',
}
const reasonLabel = (reason: string) => reasons[reason] ?? reason

const networkStates: Readonly<Record<NetworkSnapshot['state'], string>> = {
  off: 'Выключена', creating: 'Создание ledger', connecting: 'Подключение', ready: 'Подключена', retrying: 'Переподключение', refused: 'Отклонена сервером',
}
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
      <div><dt>Первый звук провайдера</dt><dd>{snapshot.firstAudioMs === null ? '—' : `${snapshot.firstAudioMs} мс`}</dd></div>
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
      <div><dt>Блокировки</dt><dd>{interpreter?.latches.join(', ') || (interpreter?.pain ? 'боль' : '—')}</dd></div>
      <div><dt>Последняя фраза</dt><dd>{snapshot.lastCue ? `${snapshot.lastCue.triggerId} · ${snapshot.lastCue.clipId ?? '—'} · ${reasonLabel(snapshot.lastCue.reason)}` : '—'}</dd></div>
      <div><dt>Поводы / приняты / нет клипа / подавлены</dt><dd>{`${snapshot.counters.cues} / ${snapshot.counters.admitted} / ${snapshot.counters.missingClip} / ${snapshot.counters.suppressed}`}</dd></div>
    </dl>
    {!!interpreter?.skips.length && <ol className="coach-local-timeline">{interpreter.skips.slice(-10).map((item, index) => <li key={index}>{item.triggerId} · {reasonLabel(item.reason)}</li>)}</ol>}
  </section>
}

/** Only runtime/manager observations; never lifecycle event.source or provider estimates. */
export function CoachLocalDiagnostics({ snapshot }: { snapshot: LocalAudioRuntimeSnapshot }) {
  const audio = snapshot.audio
  const foreground = audio?.utterances.find(item => item.id === audio.foreground)?.startOrdinal
  return <div className="coach-local-diagnostics">
    <p className="coach-local-reason">{reasonLabel(snapshot.reason)} <code>{snapshot.reason}</code></p>
    <dl className="coach-local-metrics">
      <div><dt>Последний фактический источник</dt><dd>{audio?.lastActualSource?.toUpperCase() ?? '—'}</dd></div>
      <div><dt>Локальные старты</dt><dd>{audio?.counters.started ?? 0}</dd></div>
      <div><dt>Активные / слышимые / ожидающие</dt><dd>{audio ? `${audio.active} / ${audio.audible} / ${audio.pending}` : '—'}</dd></div>
      <div><dt>Передний план · номер старта</dt><dd>{foreground ?? '—'}</dd></div>
      <div><dt>AudioContext</dt><dd>{audio?.contextState ?? 'Не наблюдался'}</dd></div>
      <div><dt>Громкость / mute</dt><dd>{audio ? `${Math.round(audio.volume * 100)}% / ${audio.muted ? 'да' : 'нет'}` : '—'}</dd></div>
      <div><dt>Подготовленные клипы / байты</dt><dd>{snapshot.prepared.entries} / {snapshot.prepared.bytes}{snapshot.prepared.loading ? ' · декодирование…' : ''}</dd></div>
      <div><dt>Сохранённые настройки</dt><dd>{snapshot.preferencesLoading ? 'Загрузка' : snapshot.preferencesReady ? 'Получены' : 'Не получены'}</dd></div>
      <div><dt>Enqueued / finished / cancelled / rejected</dt><dd>{audio ? `${audio.counters.enqueued} / ${audio.counters.finished} / ${audio.counters.cancelled} / ${audio.counters.rejected}` : '—'}</dd></div>
      <div><dt>Причина менеджера</dt><dd>{audio?.reason ?? '—'}</dd></div>
    </dl>
    <p className="coach-local-note">Платная генерация отсутствует в локальном тесте. Usage неизвестен для локальных клипов; расход live-тренера показан в разделе «Сеть».</p>
    <p className="coach-local-note">Старты наблюдаются по времени AudioContext, не подтверждают звук на устройстве. Только тестовые тоны, не выбранный голос.</p>
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

export function CoachMiniDebug() {
  const snapshot = useSyncExternalStore(localAudioRuntime.subscribe, localAudioRuntime.getSnapshot, localAudioRuntime.getSnapshot)
  const live = useSyncExternalStore(coachLiveRuntime.subscribe, coachLiveRuntime.getSnapshot, coachLiveRuntime.getSnapshot)
  const runUsage = live.network?.usage
  const daily = useDailyUsage(runUsage ? `${runUsage.requests}:${runUsage.settledMicros}:${runUsage.pendingMicros}` : '')
  const dailyText = daily ? `Сегодня: ${daily.requests} платн. запр. на ${dayUsd(daily.totalMicros)}${daily.pendingMicros ? ` (из них в расчёте ${dayUsd(daily.pendingMicros)})` : ''}` : null
  const target = useSafetyDockTarget()
  const [open, setOpen] = useState(false)
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
      const panelWidth = Math.min(460, window.innerWidth - 24)
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
  const coachEnabled = import.meta.env.VITE_COACH_ENABLED === 'true'
  const title = [mode.title, reasonLabel(locked ? 'audio_locked' : snapshot.reason), dailyText].filter(Boolean).join(' · ')
  return <Popover.Root open={open && target === null} onOpenChange={value => setOpen(target === null && value)}>
    <Popover.Trigger asChild>
      <button ref={triggerRef} type="button" className="coach-mini-debug-trigger" disabled={target !== null} aria-label="AI-тренер: локальная диагностика" title={title}>
        <span className="coach-mini-debug-mode" data-tone={mode.tone}>AI · {mode.label}</span>
        {coachEnabled && <>
          <span>{daily ? `${daily.requests} запр.` : '—'}</span>
          <span>{daily ? dayUsd(daily.totalMicros) : '—'}</span>
        </>}
      </button>
    </Popover.Trigger>
    {/* Register after Trigger: its initial implicit anchor must not overwrite
      the virtual anchor before Radix recognizes the custom anchor. */}
    <Popover.Anchor virtualRef={anchorRef} />
    <Popover.Portal>
        {/* Never flip/shift into the protected header. Width and remaining height
          are constrained instead; Radix still owns placement, portal and focus. */}
        <Popover.Content className="coach-mini-debug-popover" style={{ maxHeight: Math.min(640, availableHeight) }} aria-label="Локальная диагностика AI-тренера" side="bottom" align="end" sideOffset={8} avoidCollisions={false} updatePositionStrategy="always" onCloseAutoFocus={event => { if (target !== null) event.preventDefault() }}>
        <header><h3>AI · Локальная диагностика</h3><Popover.Close aria-label="Закрыть диагностику AI">×</Popover.Close></header>
        {dailyText && <p className="coach-local-note">{dailyText}</p>}
        <CoachLocalDiagnostics snapshot={snapshot} />
        <CoachLiveDiagnostics snapshot={live} />
        {live.network && <CoachNetworkDiagnostics snapshot={live.network} />}
      </Popover.Content>
    </Popover.Portal>
  </Popover.Root>
}