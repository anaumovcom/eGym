import { memo, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  PROVENANCE_LABEL,
  formatValue,
  motorApi,
  type CalibrationSpec,
  type CalibrationStatus,
  type ParamItem,
  type WorkingWindow,
} from '@/features/motor/api/motor-api'
import { ApiError } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { CalibrationRunControls } from './calibration-run-controls'
import { CalibrationRecordView } from './calibration-record'
import { SPEC_STATUS } from './calibration-status'
import { ScenarioPicker, scenarios } from './calibration-scenarios'
import { participation, SetupRoute, setupSteps } from './first-setup'
import { CalibrationGuide } from './calibration-guide'
import { CalibrationCatalogContext, PriorityLegend, PriorityMark, priorityLabel } from './calibration-priority'
import { SpeedStudy } from './speed-study'
import { FaultRehearsal } from './fault-rehearsal'
import { useCalibrationRun } from './use-calibration-run'

const card = 'cal-surface'

function errorText(error: unknown): string {
  return error instanceof ApiError || error instanceof Error ? error.message : 'Ошибка запроса'
}

function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function dateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
}

const SIDE_PATH = /^(left|right)\./

function isDone(status: CalibrationStatus | undefined): boolean {
  return status === 'actual' || status === 'stale'
}

/** Physical prerequisites and the accepted automatic check before a person takes the bar. */
function blockers(spec: CalibrationSpec, byCode: Map<string, CalibrationSpec>): CalibrationSpec[] {
  return spec.requires
    .map((code) => byCode.get(code))
    .filter((item): item is CalibrationSpec => Boolean(item && (spec.code === 'G3' && (item.code === 'G2' || item.code === 'F11')
      ? item.status !== 'actual' : item.produces.length && !isDone(item.status))))
}

const RUN_STATUS: Record<string, { label: string; className: string }> = {
  running: { label: 'выполняется', className: 'bg-[#b5852f]/25 text-[#f2cf87]' },
  saved: { label: 'сохранена', className: 'bg-[#79de83]/15 text-[#79de83]' },
  done: { label: 'завершена', className: 'bg-[#f2cf87]/15 text-[#f2cf87]' },
  discarded: { label: 'отклонена', className: 'bg-white/6 text-white/50' },
  aborted: { label: 'прервана', className: 'bg-[#f2cf87]/15 text-[#f2cf87]' },
  failed: { label: 'ошибка', className: 'bg-[#ff8f84]/15 text-[#ff8f84]' },
}

function Badge({ label, className }: { label: string; className: string }) {
  return <span className={cn('whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium', className)}>{label}</span>
}

function ProcedureList({ items, selected, disabled, onSelect }: { items: CalibrationSpec[]; selected: string; disabled: boolean; onSelect: (code: string) => void }) {
  return <ol className="cal-procedures" aria-label="Процедуры">
    {items.map(spec => <li key={spec.code}><button type="button" onClick={() => onSelect(spec.code)} aria-pressed={selected === spec.code} disabled={disabled}>
      <span className="cal-code">{spec.code === 'WIZARD' ? 'Мастер' : spec.code}</span>
      <span><strong>{spec.title}</strong><span className="cal-procedure-meta"><PriorityMark code={spec.code} />
        <small>{SPEC_STATUS[spec.status].label}{spec.durationS ? ` · ~${clock(spec.durationS)}` : ''}</small></span></span>
      <i aria-hidden="true" className={SPEC_STATUS[spec.status].dot} />
    </button></li>)}
  </ol>
}

// ------------------------------------------------------------------ details panel
function StatusBadge({ status }: { status: CalibrationStatus }) {
  return <Badge label={SPEC_STATUS[status].label} className={SPEC_STATUS[status].className} />
}

function Callout({ tone, title, children }: { tone: 'warn' | 'bad' | 'info'; title: string; children: React.ReactNode }) {
  const color = { warn: 'border-[#f2cf87]/40 bg-[#f2cf87]/8 text-[#f8e6bd]', bad: 'border-[#ff8f84]/40 bg-[#ff8f84]/8 text-[#ffd2cd]', info: 'border-[#7fb8ff]/35 bg-[#7fb8ff]/8 text-[#d6e8ff]' }[tone]
  return (
    <div className={cn('rounded-[18px] border px-4 py-3 text-sm', color)} role={tone === 'bad' ? 'alert' : undefined}>
      <p className="font-semibold">{title}</p>
      <div className="mt-0.5 text-white/75">{children}</div>
    </div>
  )
}

function ProducedValues({ spec, params }: { spec: CalibrationSpec; params: Map<string, ParamItem> }) {
  const keys = [...new Set(spec.produces.map((path) => path.replace(SIDE_PATH, '')))]
  const items = keys.map((key) => params.get(key)).filter((item): item is ParamItem => Boolean(item))
  if (!items.length) return null
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/35">Определяет · текущие значения</h4>
      <div className="overflow-x-auto rounded-[18px] border border-white/8">
        <table className="w-full text-sm">
          <tbody>
            {items.map((item) => (
              <tr key={item.key} className="border-t border-white/6 first:border-t-0">
                <td className="px-3 py-2 text-white/70">{item.label}</td>
                {item.values
                  ? (['left', 'right'] as const).map((side) => <ParamValue key={side} item={item} info={item.values![side]} side={side} />)
                  : item.value ? <ParamValue item={item} info={item.value} side={null} colSpan={2} /> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ParamValue({ item, info, side, colSpan }: { item: ParamItem; info: NonNullable<ParamItem['value']>; side: 'left' | 'right' | null; colSpan?: number }) {
  const value = (item.kind === 'table' || item.kind === 'weight' && (info.points ?? 1) > 1) && info.points != null
    ? `карта, точек · ${info.points}` : formatValue(info.value, item.kind, item.unit)
  return (
    <td className="px-3 py-2" colSpan={colSpan}>
      {side ? <span className="mr-1 text-[11px] text-white/35">{side === 'left' ? 'Л' : 'П'}</span> : null}
      <span className="font-medium text-white">{value}</span>
      <span className={cn('ml-2 text-[11px]', info.provenance === 'measured' ? 'text-[#79de83]' : info.provenance === 'manual' ? 'text-[#7fb8ff]' : 'text-white/35')}>
        {PROVENANCE_LABEL[info.provenance]}
      </span>
    </td>
  )
}

const SpecDetails = memo(function SpecDetails({ spec, byCode, params, onSelect, showGuide = true }: {
  spec: CalibrationSpec
  byCode: Map<string, CalibrationSpec>
  params: Map<string, ParamItem>
  onSelect: (code: string) => void
  showGuide?: boolean
}) {
  const blocking = blockers(spec, byCode)
  const stages = (spec.stages?.length ?? 0) > 1 ? spec.stages!.map((code) => byCode.get(code)).filter((item): item is CalibrationSpec => Boolean(item)) : []
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-[#b5852f]/30 px-2 py-0.5 font-mono text-sm text-[#f4dfb4]">{spec.code === 'WIZARD' ? '★' : spec.code}</span>
          <h2 className="text-xl font-semibold text-[#f4dfb4]">{spec.title}</h2>
          <StatusBadge status={spec.status} />
          {spec.participation && <span className="cal-mode-label">{participation(spec)}</span>}
          {spec.durationS ? <span className="text-xs text-white/40">~{clock(spec.durationS)}</span> : null}
        </div>
        {showGuide && <PriorityMark code={spec.code} explain />}
        <p className="mt-2 text-sm leading-relaxed text-white/70">{spec.description}</p>
      </div>
      {showGuide && <CalibrationGuide code={spec.code} title={spec.title} />}

      {spec.status === 'stale' && spec.staleReason ? <Callout tone="warn" title="Результат устарел">{spec.staleReason}.</Callout> : null}
      {spec.status === 'failed' && spec.lastCheck ? (
        <Callout tone="bad" title="Последняя проверка не пройдена">{dateTime(spec.lastCheck.finishedAt)} — подробности в истории ниже. Исправьте причину и повторите.</Callout>
      ) : null}
      {blocking.length ? (
        <Callout tone="warn" title="Сначала выполните">
          <span className="flex flex-wrap gap-2 pt-1">
            {blocking.map((item) => (
              <button key={item.code} type="button" onClick={() => onSelect(item.code)} className="rounded-lg border border-[#f2cf87]/40 px-2 py-0.5 text-xs text-[#f8e6bd] hover:bg-[#f2cf87]/15">
                {item.code} · {item.title}
              </button>
            ))}
          </span>
        </Callout>
      ) : null}
      {spec.prepare ? <Callout tone="info" title="Перед запуском">{spec.prepare}</Callout> : null}

      {stages.length ? (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/35">Этапы мастера</h4>
          <ol className="grid gap-1.5 sm:grid-cols-2">
            {stages.map((stage, index) => (
              <li key={stage.code}>
                <button type="button" onClick={() => onSelect(stage.code)} className="flex w-full items-baseline gap-2 rounded-[14px] border border-white/8 bg-white/3 px-3 py-2 text-left text-sm hover:border-white/20">
                  <span className="text-xs text-white/35">{index + 1}</span>
                  <span className="font-mono text-xs text-white/50">{stage.code}</span>
                  <span className="min-w-0 flex-1 text-white/80">{stage.title}
                    <span className="cal-procedure-meta"><PriorityMark code={stage.code} /><StatusBadge status={stage.status} /></span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      ) : spec.steps.length ? (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/35">Как проходит</h4>
          <ol className="space-y-1.5">
            {spec.steps.map((step, index) => (
              <li key={step} className="flex gap-3 text-sm text-white/75">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/8 text-[11px] text-white/60">{index + 1}</span>
                {step}
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {spec.code !== 'WIZARD' ? <ProducedValues spec={spec} params={params} /> : null}

      {spec.requires.length || spec.uses?.length ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-white/45">
          {spec.requires.length ? <span>Требует:</span> : null}
          {spec.requires.map((code) => {
            const item = byCode.get(code)
            return (
              <button key={code} type="button" onClick={() => onSelect(code)} title={item?.title} className={cn('rounded-lg border px-2 py-0.5 font-mono', SPEC_STATUS[item?.status ?? 'missing'].dot)}>
                {code}
              </button>
            )
          })}
          {spec.uses?.length ? <span className="ml-2">Устаревает после повтора: {spec.uses.join(', ')}</span> : null}
        </div>
      ) : null}
      {!spec.produces.length && spec.code !== 'WIZARD' ? <p className="text-xs text-white/40">Проверка: параметры профиля не меняет, статус — по последнему запуску.</p> : null}
    </div>
  )
})

function RunHistory({ code }: { code: string }) {
  const [onlySelected, setOnlySelected] = useState(false)
  const [opened, setOpened] = useState<string | null>(null)
  const runs = useQuery({ queryKey: ['motor', 'runs', onlySelected ? code : 'all'], queryFn: () => motorApi.runs(30, onlySelected ? code : undefined) })
  return <section className="cal-surface" aria-label="История калибровок">
    <div className="cal-workspace-heading"><h3>История запусков</h3>
      <label><input type="checkbox" checked={onlySelected} onChange={e => setOnlySelected(e.target.checked)} /> Только {code === 'WIZARD' ? 'мастер' : code}</label>
    </div>
    {runs.isError ? <p role="alert">Не удалось получить историю.</p> : !runs.data ? <p>Загрузка истории…</p> : runs.data.length ? (
      <ul className="cal-history">{runs.data.map(item => <li key={item.id}>
        <button type="button" aria-expanded={opened === item.id} onClick={() => setOpened(opened === item.id ? null : item.id)}>
          <time>{dateTime(item.startedAt)}</time><strong>{item.code} · {item.title ?? 'Запуск'}</strong>
          <Badge {...(RUN_STATUS[item.status] ?? { label: item.status, className: '' })} />
          <PriorityMark code={item.code} />
          {item.savedVersion != null ? <small>v{item.savedVersion}</small> : null}
        </button>
        {item.reason ? <p>{item.reason}</p> : null}
        {opened === item.id ? <CalibrationRecordView key={item.id} runId={item.id} item={item} /> : null}
      </li>)}</ul>
    ) : <p>Запусков пока не было.</p>}
  </section>
}

function WorkingZonePicker({ spec, middle, zone, travel, onChange }: {
  spec: CalibrationSpec; middle: boolean; zone?: WorkingWindow | null; travel: number | null; onChange: (middle: boolean) => void
}) {
  return <div className="cal-zone">
    <div className="cal-workspace-heading"><h3>Участок измерения</h3>
      {spec.middleZone === 'preferred' ? <select aria-label="Участок измерения" value={middle ? 'middle' : 'standard'} onChange={e => onChange(e.target.value === 'middle')}>
        <option value="middle">Середина хода</option><option value="standard">Штатный участок</option>
      </select> : null}
    </div>
    {middle ? <>
      {zone ? <>
        <strong>{Math.round(zone.lowMm)}–{Math.round(zone.highMm)} мм</strong>
        {travel !== null && travel >= zone.highMm && travel > 0 && <div className="cal-zone-scale" role="img" aria-label={`Измерительный участок от ${Math.round(zone.lowMm)} до ${Math.round(zone.highMm)} мм при полном ходе ${Math.round(travel)} мм`}>
          <div><i style={{ left: `${100 * zone.lowMm / travel}%`, width: `${100 * (zone.highMm - zone.lowMm) / travel}%` }} /></div>
          <small><span>0 мм · нижние упоры</span><span>{Math.round(travel)} мм · верх</span></small>
        </div>}
        <p>Подъезд с нижних упоров и посадка входят в запись.</p>
      </> : <p>Границы появятся после проверки нуля B7, хода B8, поддержки C3 и программных пределов.</p>}
    </> : <p>Будет использован штатный участок, указанный в описании процедуры.</p>}
  </div>
}

export const CalibrationsTab = memo(function CalibrationsTab({ serviceMode, onLock }: { serviceMode: boolean; onLock: (locked: boolean) => void }) {
  const queryClient = useQueryClient()
  const [url, setUrl] = useSearchParams()
  const [search, setSearch] = useState('')
  const catalog = useQuery({ queryKey: ['motor', 'calibrations'], queryFn: motorApi.calibrations })
  const parameters = useQuery({ queryKey: ['motor', 'parameters'], queryFn: motorApi.parameters, staleTime: 30_000 })
  const byCode = useMemo(() => new Map((catalog.data ?? []).map(item => [item.code, item])), [catalog.data])
  const params = useMemo(() => {
    const map = new Map<string, ParamItem>()
    for (const group of parameters.data?.groups ?? []) for (const item of group.items) if (item.scope === 'side' || item.scope === 'machine') map.set(item.key, item)
    return map
  }, [parameters.data])
  const requested = url.get('code')
  const firstOpen = setupSteps.find(s => byCode.has(s.code) && byCode.get(s.code)?.status !== 'actual')
  const code = requested ?? firstOpen?.code ?? setupSteps.filter(s => byCode.has(s.code)).at(-1)?.code ?? 'WIZARD'
  useEffect(() => {
    if (requested || !catalog.data) return
    const selected = new URLSearchParams(url)
    selected.set('code', code)
    selected.set('scenario', 'setup')
    setUrl(selected, { replace: true })
  }, [requested, catalog.data, code, url, setUrl])
  const spec = byCode.get(code) ?? null
  const latest = useQuery({ queryKey: ['motor', 'runs', 'latest', code], queryFn: () => motorApi.runs(1, code), enabled: Boolean(spec) })
  const previousAttempt = latest.data?.[0]
  const scenarioId = url.get('scenario') ?? scenarios.find(s => s.codes.includes(code))?.id ?? 'all'
  const scenario = scenarios.find(s => s.id === scenarioId)
  const all = useMemo(() => [...byCode.values()].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)), [byCode])
  const options = scenario ? scenario.codes.map(c => byCode.get(c)).filter((s): s is CalibrationSpec => !!s) : all
  const term = search.trim().toLocaleLowerCase('ru-RU')
  const visible = term ? all.filter(s => [s.code, s.title, s.groupTitle, priorityLabel(s.priority)].join(' ').toLocaleLowerCase('ru-RU').includes(term)) : options
  const middle = spec?.middleZone === 'required' || (spec?.middleZone === 'preferred' && url.get('zone') !== 'standard')
  const run = useCalibrationRun({ code, spec, enabled: serviceMode, workingZone: middle ? 'middle' : undefined })
  const measuredTravel = params.get('travel_mm')?.value
  const travel = parameters.data?.version === run.state.data?.profileVersion && measuredTravel?.provenance === 'measured'
    && typeof measuredTravel.value === 'number' ? measuredTravel.value : null
  const locked = run.running || run.ownsRun || run.starting
  useEffect(() => { onLock(locked); return () => onLock(false) }, [onLock, locked])

  const finishedId = run.session && !run.running ? run.session.id : null
  useEffect(() => {
    if (!finishedId) return
    void queryClient.invalidateQueries({ queryKey: ['motor', 'runs'] })
    void queryClient.invalidateQueries({ queryKey: ['motor', 'calibrations'] })
  }, [finishedId, queryClient])

  const select = (next: string, group = scenarioId) => {
    if (locked) return
    setUrl({ tab: 'calibrations', scenario: group, code: next })
  }
  const pick = (id: string) => {
    const group = scenarios.find(s => s.id === id)
    const steps = group ? group.codes.map(c => byCode.get(c)).filter((s): s is CalibrationSpec => !!s) : all
    const first = id === 'all' && spec ? spec : steps.find(s => s.runnable && s.status !== 'actual') ?? steps[0]
    setSearch('')
    if (first) select(first.code, id)
  }
  const selectFromList = (next: string) => {
    if (term) {
      setSearch('')
      select(next, 'all')
    } else select(next)
  }
  const recommended = options.find(s => s.runnable && s.status !== 'actual')
  const advance = recommended && (blockers(recommended, byCode)[0] ?? recommended)
  const inSetup = scenarioId === 'setup'
  const setupComplete = inSetup && options.length === setupSteps.length && options.every(item => item.status === 'actual')
  const checkpoint = inSetup ? setupSteps.find(s => s.code === code) : undefined
  const activeRouteCode = run.session?.code ?? code
  const index = setupSteps.findIndex(s => s.code === activeRouteCode)
  const nextCheckpoint = inSetup && index >= 0 ? setupSteps.slice(index + 1).find(s => byCode.has(s.code) && byCode.get(s.code)?.status !== 'actual') : undefined

  return <CalibrationCatalogContext.Provider value={byCode}><div className="cal-lab">
    {catalog.isError ? <p role="alert">Каталог недоступен. {errorText(catalog.error)}</p> : !catalog.data ? <p>Загрузка калибровок…</p> : null}
    {catalog.data || run.session || run.starting ? <>
      {!run.running && <ScenarioPicker specs={byCode} active={scenarioId} disabled={locked} onPick={pick} />}
      <div className={run.running ? 'cal-monitor' : 'cal-workspace'}>
        {!run.running && <aside className="cal-surface cal-sidebar">
          <div className="cal-workspace-heading"><h2>{scenario?.title ?? 'Все процедуры'}</h2>
            {scenario && <button type="button" className="cal-link" disabled={locked} onClick={() => pick('all')}>Все процедуры</button>}
          </div>
          {scenario ? <p>{scenario.description}</p> : null}
          <input type="search" aria-label="Поиск по всем калибровкам" placeholder="Название, код или важность" value={search} disabled={locked} onChange={e => setSearch(e.target.value)} />
          <PriorityLegend />
          {inSetup && !term ? <SetupRoute specs={byCode} selected={activeRouteCode} disabled={locked} onSelect={selectFromList} /> : visible.length ? <ProcedureList items={spec && !term && !options.includes(spec) ? [spec, ...visible] : visible} selected={code} disabled={locked} onSelect={selectFromList} /> : <p>По запросу ничего не найдено.</p>}
          {!!scenario && !inSetup && !term && advance && advance.code !== code && <button type="button" className="cal-next" disabled={locked} onClick={() => select(advance.code)}>Следующий шаг · {advance.code} {advance.title}</button>}
          {options.length > 0 && options.every(s => s.status === 'actual') && <p data-tone="good">Все измерения этого сценария актуальны.</p>}
        </aside>}
        <div className="cal-detail">
          {setupComplete && !run.running && <section className="cal-surface cal-setup-complete" aria-label="Итог первичной настройки">
            <h2>Первичная настройка пройдена</h2>
            <p>Проверены ход, шкала веса, повторяемость и ощущение грифа под рукой. Записи всех этапов доступны в истории.</p>
            <button type="button" className="cal-link" disabled={locked} onClick={() => pick('speed')}>Открыть расчёт скорости и торможения</button>
          </section>}
          {scenarioId === 'speed' && !run.session && <SpeedStudy version={run.state.data?.profileVersion} />}
          {scenarioId === 'protection' && !run.session && <FaultRehearsal version={parameters.data?.version} />}
          {spec && !run.session ? <>
            <section className={card} aria-label="Калибровка">
              {checkpoint ? <>
                <div className="cal-checkpoint-heading"><span>{participation(spec)}{spec.durationS ? ` · около ${Math.max(1, Math.round(spec.durationS / 60))} мин` : ''}</span>
                  <h2>{checkpoint.title}</h2><p>{checkpoint.task}</p>
                  <PriorityMark code={spec.code} explain />
                </div>
                {previousAttempt && (previousAttempt.status === 'failed' || previousAttempt.status === 'aborted') && <p className="cal-previous-attempt">
                  Последняя попытка · {dateTime(previousAttempt.startedAt)} · {RUN_STATUS[previousAttempt.status].label}.
                  {previousAttempt.reason && ` ${previousAttempt.reason}`}
                </p>}
                {blockers(spec, byCode).length > 0 && <p className="cal-route-help">Сначала выполните {blockers(spec, byCode).map(s => s.title).join(', ')}.</p>}
                <details className="cal-technical"><summary>{(spec.stages?.length ?? 0) > 1 ? `Что будет измерено · ${spec.stages!.length} замеров` : 'Подробности измерения'}</summary>
                  <SpecDetails spec={spec} byCode={byCode} params={params} onSelect={select} showGuide={false} /></details>
              </> : <SpecDetails spec={spec} byCode={byCode} params={params} onSelect={select} />}
              {checkpoint && <CalibrationGuide code={spec.code} title={spec.title} />}
              {spec.middleZone && !locked ? <WorkingZonePicker spec={spec} middle={middle} zone={run.state.data?.workingZone} travel={travel} onChange={useMiddle => {
                const changed = new URLSearchParams(url)
                if (useMiddle) changed.delete('zone'); else changed.set('zone', 'standard')
                setUrl(changed)
              }} /> : null}
            </section>
          </> : !spec && !run.session ? <p>Процедура {code} отсутствует в каталоге. Выберите процедуру слева.</p> : null}
          <CalibrationRunControls key={code} run={run} onNext={nextCheckpoint ? () => select(nextCheckpoint.code, 'setup') : undefined} />
          {!serviceMode && !run.session && spec?.runnable ? <p>Включите сервисный режим в панели состояния тренажёра.</p> : null}
          {run.error && <p role="alert" data-tone="bad">{run.error}</p>}
        </div>
      </div>
    </> : null}
    {!run.running && <RunHistory code={run.session?.code ?? code} />}
  </div></CalibrationCatalogContext.Provider>
})
