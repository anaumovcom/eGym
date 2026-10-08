import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  formatValue,
  kgfHint,
  motorApi,
  type CalibrationChange,
  type CalibrationSessionPayload,
  type CalibrationSpec,
  type CalibrationStage,
  type CalibrationState,
  type Precondition,
  type ReportLine,
  type RunnableCode,
} from '@/features/motor/api/motor-api'
import { ApiError } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { SessionChart } from './session-chart'

const KEEPALIVE_MS = 150
const REFERENCE_KG = { min: 2, max: 60 }
const card = 'rounded-[24px] border border-white/8 bg-white/4 p-5'

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

const SPEC_STATUS: Record<CalibrationSpec['status'], { label: string; className: string }> = {
  actual: { label: 'актуальна', className: 'bg-[#79de83]/15 text-[#79de83]' },
  missing: { label: 'не выполнена', className: 'bg-[#f2cf87]/15 text-[#f2cf87]' },
  planned: { label: 'в разработке', className: 'bg-white/6 text-white/40' },
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

function StageIcon({ status }: { status: CalibrationStage['status'] }) {
  const base = 'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold'
  if (status === 'done') return <span className={cn(base, 'bg-[#79de83]/20 text-[#79de83]')}>✓</span>
  if (status === 'running') return <span className={cn(base, 'animate-pulse bg-[#b5852f]/40 text-[#f4dfb4]')}>●</span>
  if (status === 'aborted' || status === 'failed') return <span className={cn(base, 'bg-[#ff8f84]/20 text-[#ff8f84]')}>✕</span>
  return <span className={cn(base, 'border border-white/15 text-white/30')}>·</span>
}

function ProgressBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn('h-2 overflow-hidden rounded-full bg-white/8', className)} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)}>
      <div className="h-full rounded-full bg-linear-to-r from-[#b5852f] to-[#f2cf87] transition-[width] duration-300" style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }} />
    </div>
  )
}

// ------------------------------------------------------------------ catalog
function CatalogList({ specs, selected, onSelect }: { specs: CalibrationSpec[]; selected: string; onSelect: (code: string) => void }) {
  const groups = useMemo(() => {
    const result: { title: string; items: CalibrationSpec[] }[] = []
    for (const spec of specs) {
      const group = result.find((item) => item.title === spec.groupTitle)
      if (group) group.items.push(spec)
      else result.push({ title: spec.groupTitle, items: [spec] })
    }
    return result
  }, [specs])

  return (
    <nav aria-label="Каталог калибровок" className="space-y-5">
      {groups.map((group) => (
        <section key={group.title} className="space-y-2">
          <h3 className="px-1 text-xs font-semibold uppercase tracking-[0.14em] text-white/35">{group.title}</h3>
          {group.items.map((spec) => (
            <button
              key={spec.code}
              type="button"
              onClick={() => onSelect(spec.code)}
              aria-pressed={selected === spec.code}
              className={cn(
                'flex w-full items-start gap-3 rounded-[20px] border px-4 py-3 text-left transition',
                selected === spec.code ? 'border-[#b5852f]/70 bg-[#b5852f]/15' : 'border-white/8 bg-white/4 hover:border-white/20',
                !spec.runnable && 'opacity-70',
              )}
            >
              <span className={cn('mt-0.5 rounded-lg px-2 py-0.5 font-mono text-xs', spec.runnable ? 'bg-[#b5852f]/30 text-[#f4dfb4]' : 'bg-white/8 text-white/45')}>
                {spec.code === 'WIZARD' ? '★' : spec.code}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-white">{spec.title}</span>
                {spec.measuredAt ? <span className="block text-xs text-white/35">измерено {dateTime(spec.measuredAt)}</span> : null}
              </span>
              <Badge {...SPEC_STATUS[spec.status]} />
            </button>
          ))}
        </section>
      ))}
    </nav>
  )
}

// ------------------------------------------------------------------ preconditions / hold button
function Preconditions({ items }: { items: Precondition[] }) {
  return (
    <ul className="grid gap-1.5 sm:grid-cols-2" aria-label="Условия запуска">
      {items.map((item) => (
        <li key={item.id} className="flex items-start gap-2 text-sm">
          <span className={cn('mt-0.5 font-bold', item.ok ? 'text-[#79de83]' : 'text-[#ff8f84]')}>{item.ok ? '✓' : '✕'}</span>
          <span>
            <span className={item.ok ? 'text-white/70' : 'text-white'}>{item.label}</span>
            {item.detail ? <span className="block text-xs text-white/40">{item.detail}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

function HoldButton({ disabled, holding, running, onPress, onRelease }: {
  disabled: boolean
  holding: boolean
  running: boolean
  onPress: () => void
  onRelease: () => void
}) {
  const down = (event: PointerEvent<HTMLButtonElement>) => {
    if (disabled || (event.pointerType === 'mouse' && event.button !== 0)) return
    event.currentTarget.setPointerCapture?.(event.pointerId)
    onPress()
  }
  const keyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if ((event.key === ' ' || event.key === 'Enter') && !event.repeat && !disabled) { event.preventDefault(); onPress() }
  }
  const keyUp = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); onRelease() }
  }

  return (
    <button
      type="button"
      disabled={disabled && !holding}
      onPointerDown={down}
      onPointerUp={onRelease}
      onPointerCancel={onRelease}
      onLostPointerCapture={onRelease}
      onKeyDown={keyDown}
      onKeyUp={keyUp}
      onBlur={onRelease}
      onContextMenu={(event) => event.preventDefault()}
      style={{ touchAction: 'none' }}
      className={cn(
        'relative w-full select-none overflow-hidden rounded-[28px] px-6 py-7 text-center transition',
        'disabled:cursor-not-allowed disabled:opacity-40',
        holding
          ? 'bg-linear-to-r from-[#b5852f] via-[#d6b05f] to-[#aa7b26] text-[#1b1303] shadow-[0_0_40px_rgba(214,176,95,0.45)] ring-4 ring-[#f2cf87]/40'
          : 'border border-[#b5852f]/60 bg-[#b5852f]/15 text-[#f4dfb4] hover:bg-[#b5852f]/25',
      )}
    >
      <span className="block text-lg font-bold">
        {holding ? (running ? 'Калибровка идёт — держите' : 'Запуск…') : 'Нажмите и удерживайте для запуска'}
      </span>
      <span className={cn('mt-1 block text-xs', holding ? 'text-[#1b1303]/70' : 'text-white/45')}>
        Отпустите кнопку, чтобы немедленно прервать: приводы вернутся в поддержку
      </span>
    </button>
  )
}

// ------------------------------------------------------------------ live progress
function LiveProgress({ session, durationS }: { session: CalibrationSessionPayload; durationS: number | null }) {
  const current = session.stages.find((stage) => stage.code === session.currentStage)
  return (
    <div className="space-y-4" aria-live="polite">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-white/40">Сейчас выполняется</p>
          <p className="text-lg font-semibold text-[#f4dfb4]">{current ? `${current.code} · ${current.title}` : session.title}</p>
          <p className="text-sm text-white/70">{session.note || 'подготовка…'}</p>
        </div>
        <div className="text-right">
          <p className="font-display text-3xl font-bold text-white">{Math.round(session.progress * 100)}%</p>
          <p className="text-xs text-white/45">{clock(session.elapsedS)}{durationS ? ` из ~${clock(durationS)}` : ''}</p>
        </div>
      </div>
      <ProgressBar value={session.progress} className="h-3" />
      <StageList stages={session.stages} />
      <SessionChart log={session.log} />
    </div>
  )
}

function StageList({ stages }: { stages: CalibrationStage[] }) {
  if (stages.length < 2) return null
  return (
    <ol className="grid gap-2 sm:grid-cols-3" aria-label="Этапы">
      {stages.map((stage) => (
        <li key={stage.code} className={cn('rounded-[18px] border p-3', stage.status === 'running' ? 'border-[#b5852f]/60 bg-[#b5852f]/10' : 'border-white/8 bg-white/3')}>
          <div className="flex items-center gap-2">
            <StageIcon status={stage.status} />
            <span className="min-w-0 text-sm"><span className="font-mono text-white/50">{stage.code}</span> <span className="text-white">{stage.title}</span></span>
          </div>
          {stage.status === 'running' ? <ProgressBar value={stage.progress} className="mt-2" /> : null}
          {stage.reason ? <p className="mt-1 text-xs text-[#ff8f84]">{stage.reason}</p> : null}
        </li>
      ))}
    </ol>
  )
}

// ------------------------------------------------------------------ result
function stageReport(stage: CalibrationStage): ReportLine[] {
  const report = stage.result?.report
  return Array.isArray(report) ? (report as ReportLine[]) : []
}

function ReportTable({ stages }: { stages: CalibrationStage[] }) {
  const blocks = stages.map((stage) => ({ stage, lines: stageReport(stage) })).filter((block) => block.lines.length)
  if (!blocks.length) return null
  return (
    <div className="space-y-3" aria-label="Отчёт измерения">
      {blocks.map(({ stage, lines }) => (
        <div key={stage.code} className="rounded-[18px] border border-white/8 bg-black/15 p-3">
          {blocks.length > 1 ? <p className="mb-2 text-xs text-white/40"><span className="font-mono">{stage.code}</span> {stage.title}</p> : null}
          <ul className="divide-y divide-white/6">
            {lines.map((line, index) => (
              <li key={`${line.label}-${index}`} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-0.5 py-1.5 text-sm">
                <span className="text-white/60">{line.label}</span>
                <span className={cn('text-right', line.ok === false ? 'text-[#ff8f84]' : line.ok ? 'text-[#79de83]' : 'text-white')}>
                  {line.ok === false ? '✕ ' : line.ok ? '✓ ' : ''}{line.value}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

function ChangeValue({ change, which }: { change: CalibrationChange; which: 'old' | 'new' }) {
  const info = change[which]
  if (!info) return <span className="text-white/30">—</span>
  const hint = kgfHint(info.value, change.unit)
  return (
    <span>
      <span className={which === 'new' ? 'font-semibold text-white' : 'text-white/55'}>{formatValue(info.value, change.kind, change.unit)}</span>
      {info.ci95 ? <span className="text-xs text-white/40"> ± {formatValue(info.ci95, change.kind, '')}</span> : null}
      {hint ? <span className="block text-xs text-white/35">{hint}</span> : null}
    </span>
  )
}

function ChangesTable({ changes }: { changes: CalibrationChange[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-[0.1em] text-white/35">
            <th className="py-2 pr-3 font-medium">Параметр</th>
            <th className="py-2 pr-3 font-medium">Сторона</th>
            <th className="py-2 pr-3 font-medium">Было</th>
            <th className="py-2 pr-3 font-medium">Стало</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change) => {
            const same = change.old?.value === change.new?.value
            return (
              <tr key={`${change.key}-${change.side ?? ''}`} className="border-t border-white/6 align-top">
                <td className="py-2 pr-3 text-white/80">{change.label}</td>
                <td className="py-2 pr-3 text-white/50">{change.side === 'left' ? 'Левая' : change.side === 'right' ? 'Правая' : '—'}</td>
                <td className="py-2 pr-3"><ChangeValue change={change} which="old" /></td>
                <td className="py-2 pr-3">
                  <ChangeValue change={change} which="new" />
                  {same && change.changed ? <span className="block text-xs text-[#79de83]">подтверждено измерением</span> : null}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ResultPanel({ session, busy, onAccept, onDiscard }: {
  session: CalibrationSessionPayload
  busy: boolean
  onAccept: () => void
  onDiscard: () => void
}) {
  const head = session.status === 'done'
    ? { title: 'Калибровка завершена', className: 'text-[#79de83]' }
    : session.status === 'aborted'
      ? { title: 'Калибровка прервана', className: 'text-[#f2cf87]' }
      : { title: 'Калибровка не удалась', className: 'text-[#ff8f84]' }
  const pending = session.status === 'done' && session.hasChanges && session.savedVersion === null

  return (
    <section className={cn(card, 'space-y-4')} aria-label="Результат калибровки">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className={cn('text-lg font-semibold', head.className)}>{head.title}</h3>
          <p className="text-sm text-white/55">{session.title} · {dateTime(session.startedAt)} · {clock(session.elapsedS)}</p>
          {session.reason ? <p className="mt-1 text-sm text-white/80">Причина: {session.reason}</p> : null}
        </div>
        {session.savedVersion !== null ? <Badge label={`сохранено · профиль v${session.savedVersion}`} className="bg-[#79de83]/15 text-[#79de83]" /> : null}
      </div>
      <StageList stages={session.stages} />
      <ReportTable stages={session.stages} />
      {session.status === 'done' && session.changes.length ? (
        <>
          <p className="text-sm text-white/60">
            {pending ? 'Новые значения ещё не применены. Сохраните их в профиль, чтобы тренажёр начал их использовать.' : 'Измеренные значения:'}
          </p>
          <ChangesTable changes={session.changes} />
        </>
      ) : null}
      {session.status !== 'done' ? <p className="text-sm text-white/55">Профиль не изменён. Приводы в поддержке. Можно повторить запуск.</p> : null}
      {session.status === 'done' && !session.changes.length ? <p className="text-sm text-white/55">Проверка пройдена, параметры профиля не меняются.</p> : null}
      <details className="text-sm text-white/50">
        <summary className="cursor-pointer select-none">График записи</summary>
        <div className="mt-3"><SessionChart log={session.log} /></div>
      </details>
      <div className="flex flex-wrap gap-3">
        {pending ? <Button onClick={onAccept} disabled={busy}>Сохранить новые значения</Button> : null}
        <Button variant={pending ? 'ghost' : 'secondary'} onClick={onDiscard} disabled={busy}>{pending ? 'Отклонить' : 'Закрыть'}</Button>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ details panel
function SpecDetails({ spec, labels }: { spec: CalibrationSpec; labels: Map<string, string> }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-semibold text-[#f4dfb4]">{spec.title}</h2>
          <Badge {...SPEC_STATUS[spec.status]} />
        </div>
        <p className="mt-2 text-sm leading-relaxed text-white/70">{spec.description}</p>
      </div>
      {spec.steps.length ? (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/35">Как проходит{spec.durationS ? ` · ~${clock(spec.durationS)}` : ''}</h4>
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
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-white/45">
        {spec.requires.length ? <span>Требует: {spec.requires.join(', ')}</span> : null}
        {spec.produces.length ? (
          <span>Определяет: {[...new Set(spec.produces.map((path) => labels.get(path.replace(/^(left|right)\./, '')) ?? path.replace(/^(left|right)\./, '')))].join(', ')}</span>
        ) : null}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ tab
export function CalibrationsTab({ serviceMode }: { serviceMode: boolean }) {
  const queryClient = useQueryClient()
  const [code, setCode] = useState<string>('WIZARD')
  const [userPicked, setUserPicked] = useState(false)
  const [holding, setHolding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [referenceKg, setReferenceKg] = useState('')
  const holdingRef = useRef(false)
  const timerRef = useRef<number | null>(null)

  const catalog = useQuery({ queryKey: ['motor', 'calibrations'], queryFn: motorApi.calibrations })
  const parameters = useQuery({ queryKey: ['motor', 'parameters'], queryFn: motorApi.parameters, staleTime: 30_000 })
  const runs = useQuery({ queryKey: ['motor', 'runs'], queryFn: () => motorApi.runs(15) })
  const state = useQuery({
    queryKey: ['motor', 'session', code],
    queryFn: () => motorApi.session(code),
    refetchInterval: (query) => (holdingRef.current || query.state.data?.session?.status === 'running' ? 250 : 1500),
  })
  const session = state.data?.session ?? null
  const running = session?.status === 'running'
  const spec = catalog.data?.find((item) => item.code === code) ?? null
  const needsReference = spec?.inputs?.includes('referenceKg') ?? false
  const referenceValue = Number(referenceKg.replace(',', '.'))
  const referenceValid = referenceKg.trim() !== '' && Number.isFinite(referenceValue) && referenceValue >= REFERENCE_KG.min && referenceValue <= REFERENCE_KG.max

  const labels = useMemo(() => {
    const map = new Map<string, string>()
    for (const group of parameters.data?.groups ?? []) for (const item of group.items) map.set(item.key, item.label)
    return map
  }, [parameters.data])

  useEffect(() => {
    if (session && !userPicked && session.code !== code) setCode(session.code)
  }, [session, userPicked, code])

  const finishedId = session && !running ? session.id : null
  useEffect(() => {
    if (!finishedId) return
    void queryClient.invalidateQueries({ queryKey: ['motor', 'runs'] })
    void queryClient.invalidateQueries({ queryKey: ['motor', 'calibrations'] })
  }, [finishedId, queryClient])

  const refresh = useCallback(() => queryClient.invalidateQueries({ queryKey: ['motor', 'session'] }), [queryClient])

  const stopKeepalive = () => {
    if (timerRef.current !== null) { window.clearInterval(timerRef.current); timerRef.current = null }
  }

  const release = useCallback(async (abort = true) => {
    if (!holdingRef.current) return
    holdingRef.current = false
    setHolding(false)
    stopKeepalive()
    if (abort) {
      try { await motorApi.abort() } catch (err) { setError(errorText(err)) }
    }
    await refresh()
  }, [refresh])

  const press = async () => {
    if (holdingRef.current || !spec?.runnable || (needsReference && !referenceValid)) return
    holdingRef.current = true
    setHolding(true)
    setError(null)
    try {
      const next = await motorApi.start(code as RunnableCode, needsReference ? { referenceKg: referenceValue } : {})
      queryClient.setQueryData<CalibrationState>(['motor', 'session', code], next)
    } catch (err) {
      holdingRef.current = false
      setHolding(false)
      setError(errorText(err))
      await refresh()
      return
    }
    if (!holdingRef.current) {
      // released while the start request was in flight
      await motorApi.abort().catch(() => undefined)
      await refresh()
      return
    }
    timerRef.current = window.setInterval(() => {
      motorApi.keepalive()
        .then((result) => { if (!result.running) void release(false) })
        .catch(() => { void release(false) })
    }, KEEPALIVE_MS)
  }

  useEffect(() => {
    const lost = () => { void release() }
    const hidden = () => { if (document.hidden) void release() }
    window.addEventListener('blur', lost)
    document.addEventListener('visibilitychange', hidden)
    return () => {
      window.removeEventListener('blur', lost)
      document.removeEventListener('visibilitychange', hidden)
      void release()
    }
  }, [release])

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      await Promise.all([
        refresh(),
        queryClient.invalidateQueries({ queryKey: ['motor', 'runs'] }),
        queryClient.invalidateQueries({ queryKey: ['motor', 'calibrations'] }),
        queryClient.invalidateQueries({ queryKey: ['motor', 'parameters'] }),
      ])
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const select = (next: string) => {
    if (running || holdingRef.current) return
    setUserPicked(true)
    setCode(next)
  }

  const preconditions = state.data?.preconditions ?? []
  const blocked = preconditions.some((item) => !item.ok)

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(280px,380px)_minmax(0,1fr)]">
      <aside className="space-y-4">
        {catalog.isError ? <p className="text-sm text-[#ff8f84]">Каталог недоступен: {errorText(catalog.error)}</p> : null}
        {catalog.data ? <CatalogList specs={catalog.data} selected={code} onSelect={select} /> : <p className="text-sm text-white/40">Загрузка…</p>}
      </aside>

      <div className="min-w-0 space-y-6">
        {spec ? (
          <section className={cn(card, 'space-y-5')} aria-label="Калибровка">
            <SpecDetails spec={spec} labels={labels} />

            {spec.runnable ? (
              <>
                {running && session ? (
                  <LiveProgress session={session} durationS={catalog.data?.find((item) => item.code === session.code)?.durationS ?? null} />
                ) : (
                  <div className="space-y-3 rounded-[20px] border border-white/8 bg-black/15 p-4">
                    <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-white/35">Перед запуском</h4>
                    <Preconditions items={preconditions} />
                    {needsReference ? (
                      <label className="block space-y-1.5 pt-1">
                        <span className="block text-sm text-white/80">Масса эталонного груза на грифе, кг</span>
                        <input
                          type="number"
                          inputMode="decimal"
                          min={REFERENCE_KG.min}
                          max={REFERENCE_KG.max}
                          step={0.1}
                          value={referenceKg}
                          onChange={(event) => setReferenceKg(event.target.value)}
                          placeholder="например, 20"
                          className={cn(
                            'w-40 rounded-xl border bg-black/30 px-3 py-2 text-white outline-none focus:border-[#b5852f]',
                            referenceKg && !referenceValid ? 'border-[#ff8f84]/70' : 'border-white/15',
                          )}
                        />
                        <span className="block text-xs text-white/40">
                          Половина на каждую сторону, масса взвешена на весах. Допустимо {REFERENCE_KG.min}–{REFERENCE_KG.max} кг.
                        </span>
                      </label>
                    ) : null}
                    {!serviceMode ? <p className="text-xs text-white/45">Включите сервисный режим кнопкой вверху страницы.</p> : null}
                  </div>
                )}
                <HoldButton
                  disabled={blocked || busy || (needsReference && !referenceValid)}
                  holding={holding}
                  running={running}
                  onPress={() => { void press() }}
                  onRelease={() => { void release() }}
                />
                {running ? (
                  <Button variant="danger" className="w-full" onClick={() => { void act(async () => { holdingRef.current = false; setHolding(false); stopKeepalive(); await motorApi.abort() }) }}>
                    Прервать
                  </Button>
                ) : null}
                {session && !running && session.code === code ? (
                  <p className="text-xs text-white/40">Новый запуск заменит текущий несохранённый результат.</p>
                ) : null}
              </>
            ) : (
              <p className="rounded-[18px] bg-white/4 px-4 py-3 text-sm text-white/50">Запуск этой калибровки из интерфейса пока не реализован.</p>
            )}
            {error ? <p role="alert" className="rounded-[18px] bg-[#ff8f84]/10 px-4 py-3 text-sm text-[#ff8f84]">{error}</p> : null}
          </section>
        ) : null}

        {session && !running ? (
          <ResultPanel
            session={session}
            busy={busy}
            onAccept={() => { if (window.confirm('Сохранить новые значения в профиль и применить их?')) void act(motorApi.accept) }}
            onDiscard={() => { void act(motorApi.discard) }}
          />
        ) : null}

        <section className={cn(card, 'space-y-3')} aria-label="История калибровок">
          <h3 className="text-sm font-semibold text-white/80">История</h3>
          {runs.data?.length ? (
            <ul className="divide-y divide-white/6">
              {runs.data.map((run) => (
                <li key={run.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2 text-sm">
                  <span className="w-28 text-white/45">{dateTime(run.startedAt)}</span>
                  <span className="min-w-0 flex-1 text-white/80"><span className="font-mono text-white/45">{run.code}</span> {run.title ?? ''}</span>
                  {run.reason ? <span className="text-xs text-white/40">{run.reason}</span> : null}
                  {run.savedVersion ? <span className="text-xs text-white/45">v{run.savedVersion}</span> : null}
                  <Badge {...(RUN_STATUS[run.status] ?? { label: run.status, className: 'bg-white/6 text-white/50' })} />
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-white/40">Запусков пока не было.</p>}
        </section>
      </div>
    </div>
  )
}
