import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import {
  coachJournalApi, type JournalDetail, type JournalPeriod, type JournalRow, type JournalTotals, type RequestKind,
  type RequestStatus, type UsageSummary,
} from '../lib/diagnostics-api'

/** VD journal tab: every Coach request of the user, newest first; errors in red with their reason. */
export const TRIGGER_LABELS: Readonly<Record<string, string>> = {
  T01: 'Приветствие', T02: 'Возвращение после перерыва', T03: 'Первая тренировка', T04: 'Вступление к упражнению',
  T05: 'Вступление к упражнению', T11: 'Смена группы мышц', T15: 'Поддержка в подходе', T19: 'Темп подхода',
  T20: 'Темп подхода', T21: 'Поддержка в подходе', T31: 'Поддержка по таймеру', T36: 'Результат подхода',
  T37: 'Частичный подход', T39: 'Прогресс подхода', T40: 'Повтор результата', T42: 'Лучший подход сегодня',
  T43: 'Личный рекорд', T44: 'Темп подхода', T45: 'Отдых', T46: 'Пауза отдыха', T47: 'Совет на отдыхе',
  T54: 'Следующее упражнение', T55: 'Итог упражнения', T56: 'Итог упражнения', T58: 'Итог тренировки',
  T59: 'Итог тренировки', T61: 'Хайлайт тренировки', T67: 'Начало акта', T68: 'Финальный босс', T69: 'Финальный подход',
  T70: 'Зачем это упражнение', T71: 'Разбор подхода', T72: 'Счётчик сценария',
}
const TASK_LABELS: Readonly<Record<string, string>> = {
  'scenario/propose': 'Выбор сценария', 'scenario/bible': 'Мир сценария', 'episode/workout': 'Эпизод тренировки',
  'judge/pick': 'Выбор лучшей реплики', 'prebuild/line': 'Заготовка реплики',
}
export const KIND_LABELS: Readonly<Record<RequestKind, string>> = {
  text: 'Текст', voice: 'Голос', prebuild: 'Заготовка', pack: 'Набор фраз', scenario: 'Сценарий', summary: 'Итог',
  episode: 'Эпизод', judge: 'Судья',
}
const STATUS_LABELS: Readonly<Record<RequestStatus, string>> = {
  ok: 'Успешно', error: 'Ошибка', cancelled: 'Отменён', refused: 'Отказ', pending: 'В работе',
}
const STATUS_ICONS: Readonly<Record<RequestStatus, string>> = { ok: '✓', error: '✕', cancelled: '⦸', refused: '⊘', pending: '…' }
const ERRORS: Readonly<Record<string, string>> = {
  provider_error: 'Ошибка провайдера', provider_timeout: 'Провайдер не ответил вовремя', provider_malformed: 'Некорректный ответ провайдера',
  provider_refusal: 'Модель отказалась отвечать', provider_incomplete: 'Ответ провайдера не завершён', provider_unavailable: 'Провайдер недоступен',
  usage_unsettled: 'Расход не подтверждён провайдером', validation_failed: 'Текст отклонён проверкой', first_audio_timeout: 'Голос не начал звучать вовремя',
  watchdog: 'Поток голоса оборвался', budget: 'Лимит бюджета тренировки', budget_bucket: 'Лимит статьи бюджета',
  operator_budget: 'Дневной или месячный лимит', strict_cap_unprovable: 'Цена модели не подтверждена', owner_mismatch: 'Тренировкой владеет другая вкладка',
  stale_attempt: 'Попытка устарела', paid_adapter_unavailable: 'Платный провайдер выключен или нет ключа', scope_changed: 'Контекст тренировки изменился',
  cancelled: 'Отменено', no_useful_content: 'Нечего сказать', insufficient_facts: 'Мало данных', restricted_content: 'Ограничено настройками',
  duplicate_attempt: 'Повторная попытка', pipeline_busy: 'Тренер уже говорил', invalid_text: 'Пустой или длинный текст',
  'http-400': 'Некорректный запрос', 'http-401': 'Неверный ключ API', 'http-402': 'Нет средств на счёте провайдера',
  'http-403': 'Доступ к модели запрещён', 'http-404': 'Модель или голос не найдены', 'http-429': 'Превышен лимит запросов провайдера',
  'http-500': 'Сбой на стороне провайдера', 'http-502': 'Сбой на стороне провайдера', 'http-503': 'Провайдер перегружен',
}
const VALIDATION: Readonly<Record<string, string>> = {
  number: 'лишнее или неверное число', claim: 'запрещённое утверждение', comparison: 'сравнение без данных', length: 'слишком длинно',
  topic_repeat: 'повтор темы', fact_repeat: 'повтор факта', diversity: 'однообразная подача', humor_streak: 'слишком много шуток подряд',
  injection: 'подозрительный текст', language: 'не русский текст', question: 'вопрос пользователю', shouting: 'крик капсом',
  schema: 'нарушена схема ответа', voice: 'неверные голосовые пометки', facts: 'неразрешённые факты', unreviewed_tip: 'непроверенный совет',
  tip_repeat: 'повтор совета', name: 'имя без разрешения',
}
const OUTCOME_LABELS: Readonly<Record<string, string>> = {
  speech: 'Реплика готова', silence: 'Тренер решил промолчать', rejected: 'Реплика отклонена проверкой', error: 'Ошибка',
  cancelled: 'Отменено', stale: 'Устарело до озвучки', spoken: 'Озвучено', refused: 'Запрос не отправлен',
}
const SEVERITY: Readonly<Record<RequestStatus, number>> = { error: 4, refused: 3, pending: 2, cancelled: 1, ok: 0 }
const POLL_MS = 4_000
const SUMMARY_POLL_MS = 10_000

export function errorText(code: string | null, http: number | null = null): string | null {
  if (!code) return http ? `HTTP ${http}` : null
  const [base, sub] = code.split(':', 2)
  const label = ERRORS[base] ?? (base.startsWith('http-5') ? 'Сбой на стороне провайдера' : base.replace(/_/g, ' '))
  return [label + (sub ? `: ${VALIDATION[sub] ?? sub.replace(/_/g, ' ')}` : ''), http && !base.startsWith('http-') ? `HTTP ${http}` : null]
    .filter(Boolean).join(' · ')
}
export function money(micros: number, precise = false): string {
  if (micros <= 0) return '$0'
  if (micros < 100) return '<$0.0001'
  const usd = micros / 1_000_000
  return `$${usd.toFixed(precise || usd < 0.01 ? 4 : usd < 1 ? 3 : 2)}`
}
function seconds(ms: number | null): string { return ms === null ? '—' : ms < 1000 ? `${Math.round(ms)} мс` : `${(ms / 1000).toFixed(1)} с` }
function relative(epochS: number, nowMs: number): string {
  const delta = Math.max(0, nowMs / 1000 - epochS)
  if (delta < 5) return 'только что'
  if (delta < 60) return `${Math.round(delta)} с назад`
  if (delta < 3600) return `${Math.floor(delta / 60)} мин назад`
  return new Date(epochS * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}
const clock = (epochS: number) => new Date(epochS * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const shortModel = (model: string) => model.replace(/^gpt-6-/, '').replace(/^gpt-realtime-2\.1-/, 'realtime-').replace(/^fake-/, 'fake ')
function purposeLabel(row: JournalRow): string {
  return (row.triggerId && TRIGGER_LABELS[row.triggerId]) || (row.task && TASK_LABELS[row.task]) || KIND_LABELS[row.kind] || 'Запрос'
}

export type RequestGroup = Readonly<{ key: string; steps: readonly JournalRow[]; status: RequestStatus; createdAt: number
  costMicros: number; durationMs: number | null; first: JournalRow }>
/** A line's text and voice attempts share one opportunity: show them as one row with the summed cost. */
export function groupRows(rows: readonly JournalRow[]): RequestGroup[] {
  const groups = new Map<string, JournalRow[]>()
  for (const row of rows) {
    const key = row.status === 'refused' || row.kind === 'pack' ? row.id : `${row.runId}:${row.group}`
    groups.set(key, [...(groups.get(key) ?? []), row])
  }
  return [...groups].map(([key, steps]) => {
    const ordered = [...steps].sort((a, b) => a.createdAt - b.createdAt || (a.stage === 'text' ? -1 : 1))
    const status = ordered.reduce<RequestStatus>((worst, row) => SEVERITY[row.status] > SEVERITY[worst] ? row.status : worst, 'ok')
    const durations = ordered.map(row => row.durationMs).filter((value): value is number => value !== null)
    return { key, steps: ordered, status, createdAt: ordered[0].createdAt, first: ordered[0],
      costMicros: ordered.reduce((sum, row) => sum + row.costMicros, 0), durationMs: durations.length ? durations.reduce((a, b) => a + b, 0) : null }
  }).sort((a, b) => b.createdAt - a.createdAt || b.key.localeCompare(a.key))
}

function Summary({ totals, onErrors }: { totals: JournalTotals | null; onErrors: () => void }) {
  if (!totals) return <p className="coach-journal-summary" aria-live="polite">Загрузка…</p>
  return <p className="coach-journal-summary" aria-live="polite">
    <span>Всего {totals.total}</span>
    <span className="is-ok">✓ {totals.ok}</span>
    <button type="button" className="is-error" disabled={!totals.error} onClick={onErrors} title="Показать только ошибки">✕ {totals.error}</button>
    {totals.cancelled > 0 && <span>⦸ {totals.cancelled}</span>}
    {totals.refused > 0 && <span className="is-refused">⊘ {totals.refused}</span>}
    <span>{money(totals.totalMicros)}{totals.pendingMicros > 0 ? ` (в расчёте ${money(totals.pendingMicros)})` : ''}</span>
    {totals.p95Ms !== null && <span title="95-й перцентиль длительности запроса">p95 {seconds(totals.p95Ms)}</span>}
  </p>
}

function Detail({ userId, row, nowMs }: { userId: string; row: JournalRow; nowMs: number }) {
  const [detail, setDetail] = useState<JournalDetail | null>(null)
  const [failed, setFailed] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    coachJournalApi.detail(userId, row.id, controller.signal).then(setDetail, () => { if (!controller.signal.aborted) setFailed(true) })
    return () => controller.abort()
  }, [userId, row.id])
  const copy = (value: string, done: string) => {
    void navigator.clipboard?.writeText(value).then(() => setNotice(done), () => setNotice('Буфер обмена недоступен'))
  }
  const d = detail
  const error = errorText(row.errorCode, row.httpStatus)
  return <div className="coach-journal-detail">
    {error && <p className={row.status === 'error' ? 'coach-journal-error' : 'coach-journal-warning'}>
      <strong>{error}</strong>{row.errorCode && <code>{row.errorCode}</code>}
      {d?.errorDetail && <span className="coach-journal-provider">{d.errorDetail}</span>}
    </p>}
    <dl className="coach-local-metrics">
      <div><dt>Итог</dt><dd>{(row.outcome && OUTCOME_LABELS[row.outcome]) ?? STATUS_LABELS[row.status]}</dd></div>
      <div><dt>Время</dt><dd title={new Date(row.createdAt * 1000).toLocaleString('ru-RU')}>{clock(row.createdAt)} · {relative(row.createdAt, nowMs)}</dd></div>
      <div><dt>Модель · статья</dt><dd>{row.model} · {row.purpose}{row.retry ? ' · повтор' : ''}</dd></div>
      {row.firstByteMs !== null && <div><dt>Первый звук</dt><dd>{seconds(row.firstByteMs)}</dd></div>}
      <div><dt>Длительность</dt><dd>{seconds(row.durationMs)}</dd></div>
      <div><dt>Стоимость</dt><dd>{money(row.costMicros, true)}{row.costSettled ? '' : ' · в расчёте'}{d ? ` · резерв ${money(d.reserveMicros, true)}` : ''}</dd></div>
      {d?.usage && row.stage === 'text' && <div><dt>Токены вход / кеш / выход / рассужд.</dt>
        <dd>{[d.usage.inputTokens, d.usage.cachedInputTokens, d.usage.outputTokens, d.usage.reasoningTokens].map(v => v ?? '—').join(' / ')}</dd></div>}
      {d?.textBytes !== null && d?.textBytes !== undefined && <div><dt>Байты текста / разметки</dt>
        <dd>{d.textBytes} / {d.markupBytes ?? 0}{d.markupBytes ? ` (${Math.round(100 * d.markupBytes / (d.textBytes + d.markupBytes))}%)` : ''}</dd></div>}
    </dl>
    {d?.textPreview && <blockquote className="coach-journal-text">«{d.textPreview}»</blockquote>}
    {failed && <p className="coach-local-note">Подробности недоступны.</p>}
    <div className="coach-local-actions">
      {error && <button type="button" className="rt-button" onClick={() => copy(
        [clock(row.createdAt), row.model, row.errorCode, row.httpStatus ? `HTTP ${row.httpStatus}` : null, d?.errorDetail].filter(Boolean).join(' | '),
        'Ошибка скопирована (без текста реплики)')}>Скопировать ошибку</button>}
      <button type="button" className="rt-button" onClick={() => copy(row.id, 'ID попытки скопирован')}>Скопировать ID</button>
    </div>
    {notice && <p className="coach-local-note" role="status">{notice}</p>}
  </div>
}

function GroupRow({ group, userId, nowMs, open, fresh, onToggle, onKey }: {
  group: RequestGroup; userId: string; nowMs: number; open: boolean; fresh: boolean
  onToggle: () => void; onKey: (event: KeyboardEvent<HTMLButtonElement>) => void
}) {
  const [step, setStep] = useState<string | null>(null)
  const head = group.first
  const failing = group.steps.find(row => row.status === group.status && row.errorCode) ?? group.steps.find(row => row.errorCode)
  const reason = group.status !== 'ok' ? errorText(failing?.errorCode ?? null, failing?.httpStatus ?? null) : null
  const where = [head.exerciseLabel, head.setOrdinal ? `подход ${head.setOrdinal}` : null].filter(Boolean).join(' · ')
  const shown = group.steps.find(row => row.id === step) ?? failing ?? group.steps[group.steps.length - 1]
  return <li className="coach-journal-item" data-status={group.status} data-fresh={fresh || undefined}>
    <button type="button" className="coach-journal-row" aria-expanded={open} onClick={onToggle} onKeyDown={onKey}>
      <span className="coach-journal-icon" aria-label={STATUS_LABELS[group.status]}>{STATUS_ICONS[group.status]}</span>
      <span className="coach-journal-main">
        <span className="coach-journal-title">{purposeLabel(head)}{group.steps.some(row => row.retry) ? ' · повтор' : ''}</span>
        <span className="coach-journal-sub">{[where, group.steps.map(row => `${row.stage === 'text' ? 'текст' : 'голос'} ${shortModel(row.model)}`).join(' → ')]
          .filter(Boolean).join(' · ')}</span>
        {reason && <span className="coach-journal-reason">{reason}</span>}
      </span>
      <span className="coach-journal-meta">
        <span title={new Date(group.createdAt * 1000).toLocaleString('ru-RU')}>{relative(group.createdAt, nowMs)}</span>
        <span>{seconds(group.durationMs)}</span>
        <span>{money(group.costMicros)}</span>
      </span>
    </button>
    {open && <div className="coach-journal-expanded">
      {group.steps.length > 1 && <div className="coach-journal-steps" role="group" aria-label="Шаги запроса">
        {group.steps.map(row => <button key={row.id} type="button" data-status={row.status} aria-pressed={row.id === shown.id}
          onClick={() => setStep(row.id)}>{row.stage === 'text' ? 'Текст' : 'Голос'} · {STATUS_LABELS[row.status]} · {money(row.costMicros)}</button>)}
      </div>}
      <Detail key={shown.id} userId={userId} row={shown} nowMs={nowMs} />
    </div>}
  </li>
}

function moveFocus(event: KeyboardEvent<HTMLButtonElement>) {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  const items = [...(event.currentTarget.closest('ol')?.querySelectorAll<HTMLButtonElement>('.coach-journal-row') ?? [])]
  const next = items[items.indexOf(event.currentTarget) + (event.key === 'ArrowDown' ? 1 : -1)]
  if (next) { event.preventDefault(); next.focus() }
}

function localMidnight(): number { const date = new Date(); date.setHours(0, 0, 0, 0); return date.getTime() }

export function CoachRequestsTab({ userId, runId, onSeen }: { userId: string; runId: string | null; onSeen?: () => void }) {
  const [period, setPeriod] = useState<JournalPeriod>(runId ? 'run' : 'today')
  const [status, setStatus] = useState<RequestStatus | 'all'>('all')
  const [kind, setKind] = useState<RequestKind | 'all'>('all')
  const [rows, setRows] = useState<JournalRow[]>([])
  const [totals, setTotals] = useState<JournalTotals | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [incoming, setIncoming] = useState<JournalRow[]>([])
  const [fresh, setFresh] = useState<ReadonlySet<string>>(new Set())
  const [open, setOpen] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const listRef = useRef<HTMLOListElement>(null)
  const loaded = useRef(new Set<string>())
  const effective: JournalPeriod = period === 'run' && !runId ? 'today' : period
  useEffect(() => { onSeen?.() }, [onSeen])
  const fetchPage = useCallback((signal: AbortSignal, after: string | null = null) => coachJournalApi.requests({
    userId, period: effective, runId, status, kind, cursor: after, limit: 50, sinceMs: localMidnight() }, signal), [userId, effective, runId, status, kind])
  // Filter change: start over.
  useEffect(() => {
    const controller = new AbortController()
    setRows([]); setTotals(null); setCursor(null); setIncoming([]); setOpen(null); loaded.current = new Set()
    fetchPage(controller.signal).then(page => {
      loaded.current = new Set(page.rows.map(row => row.id))
      setRows([...page.rows]); setTotals(page.totals); setCursor(page.nextCursor); setFailed(false)
    }, () => { if (!controller.signal.aborted) setFailed(true) })
    return () => controller.abort()
  }, [fetchPage])
  // Live refresh: new rows go on top, unless the user scrolled away — then a "N new" button instead of a jump.
  useEffect(() => {
    const controller = new AbortController()
    const timer = setInterval(() => {
      setNowMs(Date.now())
      fetchPage(controller.signal).then(page => {
        setTotals(page.totals)
        const updates = new Map(page.rows.map(row => [row.id, row]))
        setRows(current => current.map(row => updates.get(row.id) ?? row))
        const added = page.rows.filter(row => !loaded.current.has(row.id))
        if (!added.length) return
        if ((listRef.current?.closest('.coach-mini-debug-popover')?.scrollTop ?? 0) > 60) {
          setIncoming(current => [...added.filter(row => !current.some(item => item.id === row.id)), ...current])
          return
        }
        for (const row of added) loaded.current.add(row.id)
        setRows(current => [...added, ...current])
        setFresh(new Set(added.map(row => row.id)))
      }, () => undefined)
    }, POLL_MS)
    return () => { controller.abort(); clearInterval(timer) }
  }, [fetchPage])
  useEffect(() => {
    if (!fresh.size) return
    const timer = setTimeout(() => setFresh(new Set()), 2_000)
    return () => clearTimeout(timer)
  }, [fresh])
  const showIncoming = () => {
    for (const row of incoming) loaded.current.add(row.id)
    setRows(current => [...incoming, ...current]); setFresh(new Set(incoming.map(row => row.id))); setIncoming([])
    listRef.current?.closest('.coach-mini-debug-popover')?.scrollTo({ top: 0 })
  }
  const more = () => {
    if (!cursor) return
    const controller = new AbortController()
    fetchPage(controller.signal, cursor).then(page => {
      for (const row of page.rows) loaded.current.add(row.id)
      setRows(current => [...current, ...page.rows.filter(row => !current.some(item => item.id === row.id))]); setCursor(page.nextCursor)
    }, () => setFailed(true))
  }
  const groups = useMemo(() => groupRows(rows), [rows])
  const freshGroups = useMemo(() => new Set(groups.filter(group => group.steps.some(row => fresh.has(row.id))).map(group => group.key)), [groups, fresh])
  return <section className="coach-journal" aria-label="Журнал запросов">
    {!failed && <Summary totals={totals} onErrors={() => setStatus('error')} />}
    <div className="coach-journal-filters">
      <label>Период<select className="rt-input" value={effective} onChange={event => setPeriod(event.target.value as JournalPeriod)}>
        {runId && <option value="run">Тренировка</option>}<option value="today">Сегодня</option><option value="7d">7 дней</option></select></label>
      <label>Статус<select className="rt-input" value={status} onChange={event => setStatus(event.target.value as RequestStatus | 'all')}>
        <option value="all">Все</option><option value="error">Ошибки</option><option value="ok">Успешные</option>
        <option value="refused">Отказы</option><option value="cancelled">Отменённые</option></select></label>
      <label>Тип<select className="rt-input" value={kind} onChange={event => setKind(event.target.value as RequestKind | 'all')}>
        <option value="all">Все</option>{(Object.keys(KIND_LABELS) as RequestKind[]).map(item => <option key={item} value={item}>{KIND_LABELS[item]}</option>)}</select></label>
    </div>
    {incoming.length > 0 && <button type="button" className="coach-journal-incoming" onClick={showIncoming}>↑ {incoming.length} новых</button>}
    {failed && <p className="coach-local-note" role="alert">Журнал недоступен: сервер не отвечает или живой тренер на нём выключен (COACH_ENABLED).</p>}
    {totals && !groups.length && !failed && <p className="coach-local-note">{status === 'error' ? 'Ошибок нет за выбранный период.' : 'Запросов ещё не было.'}</p>}
    <ol ref={listRef} className="coach-journal-list">
      {groups.map(group => <GroupRow key={group.key} group={group} userId={userId} nowMs={nowMs} open={open === group.key}
        fresh={freshGroups.has(group.key)} onToggle={() => setOpen(current => current === group.key ? null : group.key)} onKey={moveFocus} />)}
    </ol>
    {cursor && <button type="button" className="rt-button coach-journal-more" onClick={more}>Показать ещё</button>}
  </section>
}

const TIER_LABELS = ['Всё включено', 'Экономия: без вариантов', 'Экономия: короткие реплики', 'Только результаты', 'Только итог и локальные фразы']
const PURPOSE_LABELS: Readonly<Record<string, string>> = { live: 'Реплики', summary: 'Итоги', scenario: 'Сценарий', prebuild: 'Заготовки', judge: 'Судья', episode: 'Эпизод' }

function Bar({ label, used, cap }: { label: string; used: number; cap: number }) {
  const share = cap > 0 ? Math.min(1, used / cap) : 0
  return <div className="coach-spend-bar" data-level={share > 0.9 ? 'high' : share > 0.7 ? 'mid' : 'low'}>
    <span>{label}</span><span>{money(used)} / {money(cap)}</span>
    <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={cap} aria-valuenow={used}><i style={{ width: `${share * 100}%` }} /></div>
  </div>
}

function Table({ title, entries, labels }: { title: string; entries: Readonly<Record<string, { requests: number; micros: number; errors: number; p95Ms: number | null }>>; labels?: Readonly<Record<string, string>> }) {
  const sorted = Object.entries(entries).sort((a, b) => b[1].micros - a[1].micros)
  if (!sorted.length) return null
  return <><h4>{title}</h4><table className="coach-spend-table"><thead><tr><th>{title.split(' ')[1] ?? ''}</th><th>Запр.</th><th>Ошибки</th><th>p95</th><th>Сумма</th></tr></thead>
    <tbody>{sorted.map(([key, entry]) => <tr key={key}><td>{labels?.[key] ?? key}</td><td>{entry.requests}</td><td data-error={entry.errors > 0 || undefined}>{entry.errors}</td>
      <td>{seconds(entry.p95Ms)}</td><td>{money(entry.micros)}</td></tr>)}</tbody></table></>
}

export function CoachSpendTab({ userId, runId, setsDone, setsLeft }: { userId: string; runId: string | null; setsDone: number; setsLeft: number }) {
  const [summary, setSummary] = useState<UsageSummary | null>(null)
  const [failed, setFailed] = useState(false)
  const [period, setPeriod] = useState<JournalPeriod>(runId ? 'run' : 'today')
  const effective: JournalPeriod = period === 'run' && !runId ? 'today' : period
  useEffect(() => {
    const controller = new AbortController()
    const load = () => coachJournalApi.summary({ userId, period: effective, runId, sinceMs: localMidnight() }, controller.signal)
      .then(value => { setSummary(value); setFailed(false) }, () => { if (!controller.signal.aborted) setFailed(true) })
    load()
    const timer = setInterval(load, SUMMARY_POLL_MS)
    return () => { controller.abort(); clearInterval(timer) }
  }, [userId, effective, runId])
  if (!summary) return <p className="coach-local-note" role={failed ? 'alert' : undefined}>{failed ? 'Расход недоступен: сервер не отвечает или живой тренер на нём выключен (COACH_ENABLED).' : 'Загрузка…'}</p>
  const workout = summary.limits.workout
  const forecast = workout && setsDone > 0 ? workout.usedMicros + workout.usedMicros / setsDone * setsLeft : null
  return <section className="coach-spend" aria-label="Расход">
    <label className="coach-spend-period">Период<select className="rt-input" value={effective} onChange={event => setPeriod(event.target.value as JournalPeriod)}>
      {runId && <option value="run">Тренировка</option>}<option value="today">Сегодня</option><option value="7d">7 дней</option></select></label>
    {workout && <Bar label="Тренировка" used={workout.usedMicros} cap={workout.capMicros} />}
    <Bar label="Сутки (все тренировки)" used={summary.limits.day.usedMicros} cap={summary.limits.day.capMicros} />
    <Bar label="Месяц" used={summary.limits.month.usedMicros} cap={summary.limits.month.capMicros} />
    {summary.budget && <dl className="coach-local-metrics">
      <div><dt>Режим бюджета</dt><dd data-tier={summary.budget.tier}>{TIER_LABELS[summary.budget.tier]}</dd></div>
      <div><dt>Резерв на итог</dt><dd>{money(summary.budget.summaryReserveMicros)}</dd></div>
      {summary.budget.avgRequestMicros !== null && <div><dt>Средний запрос</dt><dd>{money(summary.budget.avgRequestMicros, true)}</dd></div>}
      {forecast !== null && <div><dt>Прогноз до конца тренировки</dt><dd>≈ {money(forecast)}{workout && forecast > workout.capMicros ? ' · выше лимита, включится экономия' : ''}</dd></div>}
    </dl>}
    {Object.keys(summary.byPurpose).length > 0 && <><h4>По статьям</h4><dl className="coach-local-metrics">
      {Object.entries(summary.byPurpose).sort((a, b) => b[1] - a[1]).map(([key, micros]) =>
        <div key={key}><dt>{PURPOSE_LABELS[key] ?? key}</dt><dd>{money(micros)}</dd></div>)}</dl></>}
    <Table title="По типам" entries={summary.byKind} labels={KIND_LABELS} />
    <Table title="По моделям" entries={summary.byModel} />
    {summary.top.length > 0 && <><h4>Самые дорогие запросы</h4><ol className="coach-local-timeline">
      {summary.top.map(row => <li key={row.id}>{clock(row.createdAt)} · {purposeLabel(row)} · {row.stage === 'text' ? 'текст' : 'голос'} · {money(row.costMicros, true)}</li>)}</ol></>}
  </section>
}

const SEEN_KEY = (userId: string) => `coach-errors-seen:${userId}`
const ERROR_WINDOW_S = 15 * 60
const ERRORS_POLL_MS = 30_000
function readSeen(userId: string): number {
  try { return Number(localStorage.getItem(SEEN_KEY(userId))) || 0 } catch { return 0 }
}

/** Header badge: errors of the current workout (or the last 15 minutes) the user has not looked at yet. */
export function useUnseenErrors(userId: string | null, runId: string | null, enabled: boolean, refreshKey: string) {
  const [errors, setErrors] = useState<readonly JournalRow[]>([])
  const [seen, setSeen] = useState(() => userId ? readSeen(userId) : 0)
  useEffect(() => { setSeen(userId ? readSeen(userId) : 0) }, [userId])
  useEffect(() => {
    if (!enabled || !userId) { setErrors([]); return }
    const controller = new AbortController()
    const load = () => coachJournalApi.requests({ userId, period: 'today', status: 'error', limit: 50, sinceMs: localMidnight() }, controller.signal)
      .then(page => setErrors(page.rows), () => undefined)
    load()
    const timer = setInterval(load, ERRORS_POLL_MS)
    return () => { controller.abort(); clearInterval(timer) }
  }, [enabled, userId, refreshKey])
  const markSeen = useCallback(() => {
    if (!userId) return
    const now = Date.now() / 1000
    setSeen(now)
    try { localStorage.setItem(SEEN_KEY(userId), String(now)) } catch { /* per-viewer convenience only */ }
  }, [userId])
  const now = Date.now() / 1000
  const unseen = errors.filter(row => row.createdAt > seen && (row.runId === runId || row.createdAt > now - ERROR_WINDOW_S))
  return { unseen: unseen.length, latest: unseen[0] ?? null, markSeen }
}
