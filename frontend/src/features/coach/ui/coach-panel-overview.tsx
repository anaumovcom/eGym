import { useState, type ReactNode } from 'react'
import type { LocalAudioRuntimeSnapshot } from '../audio/local-audio-runtime'
import type { LocalAudioSnapshot } from '../audio/local-coach-audio-manager'
import { coachNetworkClient, type LiveRuntimeSnapshot } from '../live/coach-live-runtime'
import { redactedNetworkReport, type NetworkSnapshot } from '../live/coach-network-client'
import type { CoachPreferences } from '../model/preferences'
import { latchLabel, reasonLabel } from './coach-labels'
import { TRIGGER_LABELS } from './coach-requests-panel'

/** The panel's first screen: what the coach is doing right now, in one sentence, and what to do about it. */
export type OverviewTone = 'ok' | 'info' | 'warn' | 'error' | 'off'
export type Overview = Readonly<{ tone: OverviewTone; title: string; detail: string }>
export type OverviewInput = Readonly<{
  /** VITE_COACH_ENABLED: the live (network) coach is part of this build. */
  liveBuild: boolean
  saved: CoachPreferences | null
  /** Why local speech is or is not allowed right now (local runtime or the workout mixer). */
  reason: string
  network: NetworkSnapshot | null | undefined
  workout: boolean
  /** Machine latches the interpreter saw (safety reasons), when known. */
  latches?: readonly string[]
  /** What the machine reports while the coach keeps talking (D-V12.7). */
  machineNotices?: readonly string[]
}>

const ICONS: Readonly<Record<OverviewTone, string>> = { ok: '●', info: 'ℹ', warn: '⚠', error: '✕', off: '○' }

export function coachOverview(input: OverviewInput): Overview {
  const overview = baseOverview(input)
  const errors = input.machineNotices ?? []
  if (!errors.length || overview.tone === 'error' || overview.tone === 'off') return overview
  // D-V12.7: what the machine reports is worth knowing, but the coach keeps talking through it.
  return { tone: 'warn', title: overview.title,
    detail: `${overview.detail} Тренажёр сообщает: ${[...new Set(errors.map(latchLabel))].join(', ')} — тренер при этом продолжает говорить.` }
}

function baseOverview({ liveBuild, saved, reason, network, workout, latches = [] }: OverviewInput): Overview {
  // What blocks speech outright comes first: the user must know why the coach is silent.
  if (reason === 'safety') {
    const causes = latches.map(latchLabel)
    const cause = causes.length ? `Причина: ${causes.join(', ')}.` : 'Аварийная остановка или кнопка «Стоп» на панели.'
    return { tone: 'warn', title: 'Тренер молчит: аварийная остановка', detail: `${cause} Когда защита снимется, тренер снова заговорит.` }
  }
  if (reason === 'no_user') return { tone: 'off', title: 'Пользователь не выбран', detail: 'Выберите профиль — у каждого свои настройки тренера.' }
  if (reason === 'preferences_loading') return { tone: 'info', title: 'Загружаю настройки тренера…', detail: 'Это займёт пару секунд.' }
  if (reason === 'preferences_unavailable') return { tone: 'error', title: 'Не удалось загрузить настройки тренера',
    detail: 'Сервер не ответил. Проверьте, что бэкенд запущен, и обновите страницу.' }
  if (!saved?.enabled) return { tone: 'off', title: 'Тренер выключен', detail: 'Включите его в настройках AI-тренера.' }
  if (reason === 'no_consent') return { tone: 'off', title: 'Нужно согласие', detail: 'Подтвердите согласие в настройках AI-тренера, чтобы он заговорил.' }
  if (reason === 'audio_locked') return { tone: 'warn', title: 'Браузер не разрешил звук', detail: 'Нажмите в любом месте страницы — после этого тренер сможет говорить.' }
  if (reason === 'mute') return { tone: 'info', title: 'Звук тренера выключен', detail: 'Тренер следит за тренировкой, но не говорит. Включите звук в шапке или настройках.' }
  if (reason === 'hidden') return { tone: 'info', title: 'Вкладка скрыта', detail: 'Пока вкладка в фоне, тренер молчит.' }
  if (saved.mode === 'local') return { tone: 'ok', title: workout ? 'Тренер работает локально' : 'Тренер готов (локально)',
    detail: 'Звучат заранее подготовленные фразы — без платных запросов.' }
  if (!liveBuild) return { tone: 'info', title: 'Живой тренер не подключён в этой сборке',
    detail: 'Звучат только локальные фразы. Живому голосу нужны COACH_ENABLED на сервере и VITE_COACH_ENABLED в интерфейсе.' }
  const state = network?.state ?? 'off'
  if (state === 'refused') return { tone: 'error', title: 'Сервер не принял подключение тренера',
    detail: network?.reason ? reasonLabel(network.reason) : 'Причина не сообщена. Звучат локальные фразы.' }
  if (state === 'creating' || state === 'connecting') return { tone: 'info', title: 'Подключаю живого тренера…', detail: 'Пока звучат локальные фразы.' }
  if (state === 'retrying') return { tone: 'warn', title: 'Связь с сервером прервалась, переподключаюсь',
    detail: network?.reason ? reasonLabel(network.reason) : 'Пока звучат локальные фразы.' }
  if (state === 'ready') {
    const spoken = network?.spoken ?? 0
    const failed = network?.failed ?? 0
    return { tone: network?.degraded ? 'warn' : 'ok', title: network?.degraded ? 'Тренер на связи, экономит бюджет' : 'Тренер на связи',
      detail: [`Сказано реплик: ${spoken}`, failed ? `сбоев: ${failed}` : null].filter(Boolean).join(' · ') }
  }
  return { tone: 'ok', title: 'Тренер готов', detail: workout ? 'Живой тренер подключится к тренировке.' : 'Начните тренировку — тренер подключится сам.' }
}

export type Tile = Readonly<{ label: string; value: string; hint?: string; tone?: OverviewTone; onClick?: () => void }>

export function CoachOverview({ overview, tiles }: { overview: Overview; tiles: readonly Tile[] }) {
  return <section className="coach-overview" aria-label="Состояние тренера">
    <div className="coach-overview-card" data-tone={overview.tone} role="status">
      <span className="coach-overview-icon" aria-hidden="true">{ICONS[overview.tone]}</span>
      <div><p className="coach-overview-title">{overview.title}</p><p className="coach-overview-detail">{overview.detail}</p></div>
    </div>
    {tiles.length > 0 && <div className="coach-overview-tiles">
      {tiles.map(tile => {
        const body = <><span className="coach-tile-value">{tile.value}</span><span className="coach-tile-label">{tile.label}</span>
          {tile.hint && <span className="coach-tile-hint">{tile.hint}</span>}</>
        return tile.onClick
          ? <button key={tile.label} type="button" className="coach-tile" data-tone={tile.tone} onClick={tile.onClick}>{body}</button>
          : <div key={tile.label} className="coach-tile" data-tone={tile.tone}>{body}</div>
      })}
    </div>}
  </section>
}

const AUDIO_STATES: Readonly<Record<string, string>> = {
  running: 'работает', suspended: 'ждёт нажатия на страницу', closed: 'закрыт', interrupted: 'прерван системой', unavailable: 'недоступен в браузере',
}
const CONNECTION: Readonly<Record<NetworkSnapshot['state'], string>> = {
  off: 'подключится, когда начнётся тренировка', creating: 'создаю сессию', connecting: 'подключаюсь', ready: 'на связи',
  retrying: 'переподключаюсь', refused: 'сервер отказал',
}
const PHASES: Readonly<Record<string, string>> = {
  disabled: 'тренировка не идёт', setup: 'подготовка', 'waiting-start': 'ждём начала подхода', 'active-set': 'идёт подход',
  'paused-set': 'пауза в подходе', 'finalizing-set': 'сохраняю подход', rest: 'отдых', 'exercise-summary': 'итог упражнения',
  'workout-summary': 'итог тренировки', suspended: 'приостановлено',
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>
}

function soundNow(audio: LocalAudioSnapshot | null): string {
  if (!audio) return '—'
  if (!audio.active && !audio.pending) return 'тишина'
  return [audio.audible ? `звучит ${audio.audible}` : null, audio.pending ? `в очереди ${audio.pending}` : null].filter(Boolean).join(', ') || 'готовится'
}

/** «Состояние»: the same observations in plain words; raw counters stay in a collapsed developer block. */
export function CoachStatusTab({ local, live, liveBuild, technical }: {
  local: LocalAudioRuntimeSnapshot; live: LiveRuntimeSnapshot; liveBuild: boolean; technical: ReactNode
}) {
  const [notice, setNotice] = useState<string | null>(null)
  const audio = live.audio ?? local.audio
  const interpreter = live.interpreter
  // Without the live coach in this build the overview already says so: no empty «server» section.
  const network = liveBuild || (live.network && live.network.state !== 'off') ? live.network : null
  const lastCue = live.lastCue
  const copy = () => {
    if (!network) return
    void navigator.clipboard?.writeText(redactedNetworkReport(network)).then(() => setNotice('Отчёт скопирован (без текстов и ID)'), () => setNotice('Буфер обмена недоступен'))
  }
  const forget = () => {
    void coachNetworkClient.forgetMemory().then(cleared => setNotice(cleared === null ? 'Не удалось очистить память' : 'Память разговора очищена'))
  }
  return <section className="coach-panel-status" aria-label="Состояние подробно">
    <h4>Звук</h4>
    <dl className="coach-local-metrics">
      <Row label="Звук в браузере">{audio ? AUDIO_STATES[audio.contextState] ?? audio.contextState : 'включится при первой фразе'}</Row>
      {audio && <>
        <Row label="Громкость">{audio.muted ? 'выключен' : `${Math.round(audio.volume * 100)}%`}</Row>
        <Row label="Сейчас">{soundNow(audio)}</Row>
        <Row label="Прозвучало фраз">{audio.counters.finished}</Row>
      </>}
    </dl>
    <h4>Тренировка</h4>
    <dl className="coach-local-metrics">
      <Row label="Этап">{interpreter ? PHASES[interpreter.phase] ?? interpreter.phase : 'тренировка не идёт'}</Row>
      {interpreter && <Row label="Данные тренажёра">{interpreter.fresh ? 'свежие' : 'устарели — тренер ждёт новых'}</Row>}
      {!!interpreter?.latches.length && <Row label="Что мешает говорить">{interpreter.latches.map(latchLabel).join(', ')}</Row>}
      {!!interpreter?.machineNotices.length && <Row label="Тренажёр сообщает (тренер говорит)">{[...new Set(interpreter.machineNotices.map(latchLabel))].join(', ')}</Row>}
      {lastCue && <Row label="Последний повод">{TRIGGER_LABELS[lastCue.triggerId] ?? lastCue.triggerId} · {reasonLabel(lastCue.reason)}</Row>}
    </dl>
    {network && <>
      <h4>Связь с сервером</h4>
      <dl className="coach-local-metrics">
        <Row label="Подключение">{CONNECTION[network.state]}{network.reason ? ` · ${reasonLabel(network.reason)}` : ''}</Row>
        {network.state !== 'off' && <Row label="Живых реплик">{network.spoken}{network.failed ? ` · сбоев ${network.failed}` : ''}</Row>}
        {network.firstAudioMs !== null && <Row label="Голос начинает звучать через">{network.firstAudioMs < 1000 ? `${network.firstAudioMs} мс` : `${(network.firstAudioMs / 1000).toFixed(1)} с`}</Row>}
        {network.degraded && <Row label="Бюджет">режим экономии</Row>}
      </dl>
      {network.state !== 'off' && <div className="coach-local-actions">
        <button type="button" className="rt-button" onClick={copy}>Скопировать отчёт</button>
        <button type="button" className="rt-button" onClick={forget}>Забыть разговор</button>
      </div>}
      {notice && <p className="coach-local-note" role="status">{notice}</p>}
    </>}
    <details className="coach-technical">
      <summary>Технические подробности (для разработчика)</summary>
      {technical}
    </details>
  </section>
}
