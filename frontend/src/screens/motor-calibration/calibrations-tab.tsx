import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  PROVENANCE_LABEL,
  formatValue,
  kgfHint,
  motorApi,
  type CalibrationChange,
  type CalibrationPrompt,
  type CalibrationSessionPayload,
  type CalibrationSpec,
  type CalibrationStage,
  type CalibrationState,
  type CalibrationStatus,
  type ParamItem,
  type Precondition,
  type ReportLine,
  type RunnableCode,
} from '@/features/motor/api/motor-api'
import { ApiError } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { SessionChart } from './session-chart'

// the screen heartbeat: the backend aborts the run when it is missing for 1.5 s (closed / hidden page, lost network)
const KEEPALIVE_MS = 300
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

const SPEC_STATUS: Record<CalibrationStatus, { label: string; className: string; dot: string }> = {
  actual: { label: 'актуальна', className: 'bg-[#79de83]/15 text-[#79de83]', dot: 'border-[#79de83]/50 bg-[#79de83]/20 text-[#c9f5cd]' },
  stale: { label: 'устарела', className: 'bg-[#f2cf87]/15 text-[#f2cf87]', dot: 'border-[#f2cf87]/50 bg-[#f2cf87]/15 text-[#f8e6bd]' },
  failed: { label: 'не пройдена', className: 'bg-[#ff8f84]/15 text-[#ff8f84]', dot: 'border-[#ff8f84]/50 bg-[#ff8f84]/15 text-[#ffc9c3]' },
  missing: { label: 'не выполнена', className: 'bg-white/8 text-white/55', dot: 'border-white/12 bg-white/4 text-white/55' },
  planned: { label: 'в разработке', className: 'bg-white/6 text-white/40', dot: 'border-white/8 bg-transparent text-white/30' },
}

const SIDE_PATH = /^(left|right)\./

function isDone(status: CalibrationStatus | undefined): boolean {
  return status === 'actual' || status === 'stale'
}

/** Requirements that block the start (as on the backend: checks without parameters do not block). */
function blockers(spec: CalibrationSpec, byCode: Map<string, CalibrationSpec>): CalibrationSpec[] {
  return spec.requires
    .map((code) => byCode.get(code))
    .filter((item): item is CalibrationSpec => Boolean(item && item.produces.length && !isDone(item.status)))
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

// ------------------------------------------------------------------ commissioning path
function CommissioningPath({ specs, selected, onSelect }: { specs: CalibrationSpec[]; selected: string; onSelect: (code: string) => void }) {
  const byCode = useMemo(() => new Map(specs.map((spec) => [spec.code, spec])), [specs])
  const steps = useMemo(() => specs.filter((spec) => (spec.order ?? 0) > 0).sort((a, b) => (a.order ?? 0) - (b.order ?? 0)), [specs])
  const wizard = byCode.get('WIZARD')
  const done = steps.filter((spec) => spec.status === 'actual').length
  const next = steps.find((spec) => spec.status !== 'actual' && spec.runnable && !blockers(spec, byCode).length)
  const wizardSteps = new Set(wizard?.stages ?? [])

  return (
    <section className={cn(card, 'space-y-4')} aria-label="Порядок пусконаладки">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-[#f4dfb4]">Порядок пусконаладки</h2>
          <p className="text-sm text-white/50">Каждый шаг использует результаты предыдущих. Шаги {wizard?.stages?.[0]}…{wizard?.stages?.at(-1)} делает мастер ★ за один запуск.</p>
        </div>
        <div className="min-w-48 text-right">
          <p className="text-sm text-white/70"><span className="font-display text-2xl font-bold text-white">{done}</span> из {steps.length} актуальны</p>
          <ProgressBar value={steps.length ? done / steps.length : 0} className="mt-1" />
        </div>
      </div>
      <ol className="flex flex-wrap gap-1.5" aria-label="Шаги">
        {steps.map((spec) => (
          <li key={spec.code}>
            <button
              type="button"
              onClick={() => onSelect(spec.code)}
              title={`${spec.order}. ${spec.title} — ${SPEC_STATUS[spec.status].label}`}
              aria-label={`Шаг ${spec.order}: ${spec.code} ${spec.title}, ${SPEC_STATUS[spec.status].label}`}
              aria-pressed={selected === spec.code}
              className={cn(
                'flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs transition hover:brightness-125',
                SPEC_STATUS[spec.status].dot,
                selected === spec.code && 'ring-2 ring-[#d6b05f]',
                next?.code === spec.code && 'outline outline-1 outline-offset-2 outline-[#d6b05f]/70',
              )}
            >
              <span className="opacity-60">{spec.order}</span>
              <span className="font-mono font-semibold">{spec.code}</span>
              {wizardSteps.has(spec.code) ? <span className="text-[10px] opacity-60" aria-hidden>★</span> : null}
            </button>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[18px] bg-black/20 px-4 py-3">
        {next ? (
          <p className="text-sm text-white/70">
            Следующий шаг: <span className="font-mono text-[#f4dfb4]">{next.code}</span> <span className="font-medium text-white">{next.title}</span>
            {next.status === 'stale' && next.staleReason ? <span className="block text-xs text-[#f2cf87]">устарела: {next.staleReason}</span> : null}
            {next.status === 'failed' ? <span className="block text-xs text-[#ff8f84]">последняя проверка не пройдена</span> : null}
          </p>
        ) : (
          <p className="text-sm text-[#79de83]">Все шаги актуальны. Перед тренировками достаточно ежедневной проверки Q1.</p>
        )}
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-white/45">
          {(['actual', 'stale', 'failed', 'missing'] as const).map((status) => (
            <span key={status} className="flex items-center gap-1"><span className={cn('h-2.5 w-2.5 rounded-full border', SPEC_STATUS[status].dot)} />{SPEC_STATUS[status].label}</span>
          ))}
          {next && next.code !== selected ? <Button variant="secondary" className="py-1.5" onClick={() => onSelect(next.code)}>Открыть {next.code}</Button> : null}
        </div>
      </div>
    </section>
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
    for (const group of result) group.items.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
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
                <span className="block text-sm font-medium text-white">
                  {spec.order ? <span className="mr-1.5 text-xs text-white/35">{spec.order}.</span> : null}{spec.title}
                </span>
                {spec.measuredAt ? <span className="block text-xs text-white/35">{spec.produces.length ? 'измерено' : 'проверено'} {dateTime(spec.measuredAt)}</span> : null}
                {spec.status === 'stale' && spec.staleReason ? <span className="block text-xs text-[#f2cf87]/80">{spec.staleReason}</span> : null}
              </span>
              <StatusBadge status={spec.status} />
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

function StartButton({ disabled, starting, onStart }: { disabled: boolean; starting: boolean; onStart: () => void }) {
  return (
    <button
      type="button"
      disabled={disabled || starting}
      onClick={onStart}
      className={cn(
        'w-full select-none rounded-[28px] border border-[#b5852f]/60 bg-[#b5852f]/15 px-6 py-6 text-center text-[#f4dfb4] transition hover:bg-[#b5852f]/25',
        'disabled:cursor-not-allowed disabled:opacity-40',
      )}
    >
      <span className="block text-lg font-bold">{starting ? 'Запуск…' : 'Запустить калибровку'}</span>
      <span className="mt-1 block text-xs text-white/45">
        Держать кнопку не нужно. Остановить можно в любой момент кнопкой «СТОП»; калибровка прервётся сама, если закрыть или свернуть эту страницу
      </span>
    </button>
  )
}

function StopButton({ onStop }: { onStop: () => void }) {
  return (
    <div className="sticky bottom-4 z-10">
      <button
        type="button"
        onClick={onStop}
        className="w-full select-none rounded-[28px] bg-[#d9473b] px-6 py-6 text-center text-white shadow-[0_0_40px_rgba(217,71,59,0.45)] ring-4 ring-[#ff8f84]/40 transition hover:bg-[#e85548] active:bg-[#b93a30]"
      >
        <span className="block text-2xl font-black tracking-[0.2em]">СТОП</span>
        <span className="mt-1 block text-xs text-white/80">Немедленно прервать: гриф остановится, приводы вернутся в поддержку</span>
      </button>
    </div>
  )
}

// ------------------------------------------------------------------ operator prompt
function PromptPanel({ prompt, busy, onReply }: { prompt: CalibrationPrompt; busy: boolean; onReply: (value: number | null) => void }) {
  const [text, setText] = useState('')
  const value = Number(text.replace(',', '.'))
  const valid = text.trim() !== '' && Number.isFinite(value)
    && (prompt.min === null || value >= prompt.min) && (prompt.max === null || value <= prompt.max)
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (prompt.kind === 'input') { if (valid) onReply(value) } else onReply(null)
  }

  return (
    <form
      onSubmit={submit}
      role="alertdialog"
      aria-label="Действие оператора"
      className={cn(
        'space-y-3 rounded-[22px] border-2 p-5',
        prompt.kind === 'action' ? 'border-[#7fb8ff]/60 bg-[#7fb8ff]/10' : 'border-[#f2cf87]/70 bg-[#f2cf87]/10',
      )}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/50">
        {prompt.kind === 'action' ? 'Выполните действие — тренажёр сам заметит его' : 'Требуется ваше действие'}
      </p>
      <p className="text-lg font-semibold leading-snug text-white">{prompt.text}</p>
      {prompt.kind === 'input' ? (
        <label className="block space-y-1.5">
          <span className="block text-sm text-white/80">{prompt.label ?? 'Значение'}{prompt.unit ? `, ${prompt.unit}` : ''}</span>
          <input
            type="number"
            inputMode="decimal"
            autoFocus
            min={prompt.min ?? undefined}
            max={prompt.max ?? undefined}
            step="any"
            value={text}
            onChange={(event) => setText(event.target.value)}
            className={cn(
              'w-48 rounded-xl border bg-black/30 px-3 py-2 text-lg text-white outline-none focus:border-[#b5852f]',
              text && !valid ? 'border-[#ff8f84]/70' : 'border-white/15',
            )}
          />
          {prompt.min !== null && prompt.max !== null ? (
            <span className="block text-xs text-white/40">Допустимо {prompt.min.toLocaleString('ru-RU')}–{prompt.max.toLocaleString('ru-RU')}{prompt.unit ? ` ${prompt.unit}` : ''}</span>
          ) : null}
        </label>
      ) : null}
      <p className="text-xs text-white/45">Пока вы не ответите, гриф удерживается или стоит на упорах.</p>
      {prompt.kind === 'action' ? (
        <Button type="submit" variant="ghost" disabled={busy}>Пропустить</Button>
      ) : (
        <Button type="submit" disabled={busy || (prompt.kind === 'input' && !valid)}>Готово</Button>
      )}
    </form>
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

function changeDelta(change: CalibrationChange): { text: string; large: boolean } | null {
  const before = change.old?.value
  const after = change.new?.value
  if (typeof before !== 'number' || typeof after !== 'number' || before === after || change.kind === 'sign' || change.kind === 'counts') return null
  const diff = after - before
  const pct = before !== 0 ? (100 * diff) / Math.abs(before) : null
  const sign = diff > 0 ? '+' : '−'
  const text = `${sign}${formatValue(Math.abs(diff), change.kind, change.unit)}${pct !== null ? ` (${sign}${Math.abs(pct).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} %)` : ''}`
  return { text, large: pct !== null && Math.abs(pct) > 20 }
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
            <th className="py-2 pr-3 font-medium">Изменение</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change) => {
            const same = change.old?.value === change.new?.value
            const delta = changeDelta(change)
            return (
              <tr key={`${change.key}-${change.side ?? ''}`} className={cn('border-t border-white/6 align-top', !change.changed && 'opacity-55')}>
                <td className="py-2 pr-3 text-white/80">{change.label}</td>
                <td className="py-2 pr-3 text-white/50">{change.side === 'left' ? 'Левая' : change.side === 'right' ? 'Правая' : '—'}</td>
                <td className="py-2 pr-3"><ChangeValue change={change} which="old" /></td>
                <td className="py-2 pr-3"><ChangeValue change={change} which="new" /></td>
                <td className="py-2 pr-3 text-xs">
                  {delta ? <span className={delta.large ? 'text-[#f2cf87]' : 'text-white/60'}>{delta.text}</span> : null}
                  {same && change.changed ? <span className="text-[#79de83]">подтверждено измерением</span> : null}
                  {!change.changed ? <span className="text-white/40">без изменений</span> : null}
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
  const value = item.kind === 'weight' && (info.points ?? 1) > 1 ? `карта, ${info.points} точек` : formatValue(info.value, item.kind, item.unit)
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

function SpecDetails({ spec, byCode, params, onSelect }: {
  spec: CalibrationSpec
  byCode: Map<string, CalibrationSpec>
  params: Map<string, ParamItem>
  onSelect: (code: string) => void
}) {
  const blocking = blockers(spec, byCode)
  const stages = spec.code === 'WIZARD' ? (spec.stages ?? []).map((code) => byCode.get(code)).filter((item): item is CalibrationSpec => Boolean(item)) : []
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-[#b5852f]/30 px-2 py-0.5 font-mono text-sm text-[#f4dfb4]">{spec.code === 'WIZARD' ? '★' : spec.code}</span>
          <h2 className="text-xl font-semibold text-[#f4dfb4]">{spec.title}</h2>
          <StatusBadge status={spec.status} />
          {spec.durationS ? <span className="text-xs text-white/40">~{clock(spec.durationS)}</span> : null}
        </div>
        <p className="mt-2 text-sm leading-relaxed text-white/70">{spec.description}</p>
      </div>

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
                <button type="button" onClick={() => onSelect(stage.code)} className="flex w-full items-center gap-2 rounded-[14px] border border-white/8 bg-white/3 px-3 py-2 text-left text-sm hover:border-white/20">
                  <span className="text-xs text-white/35">{index + 1}</span>
                  <span className="font-mono text-xs text-white/50">{stage.code}</span>
                  <span className="min-w-0 flex-1 truncate text-white/80">{stage.title}</span>
                  <StatusBadge status={stage.status} />
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
}

// ------------------------------------------------------------------ tab
export function CalibrationsTab({ serviceMode }: { serviceMode: boolean }) {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const linked = searchParams.get('code')
  const [code, setCode] = useState<string>(linked ?? 'WIZARD')
  const [userPicked, setUserPicked] = useState(Boolean(linked))
  const [starting, setStarting] = useState(false)
  const [replying, setReplying] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [referenceKg, setReferenceKg] = useState('')
  const [onlySelected, setOnlySelected] = useState(false)
  const activeRef = useRef(false) // this screen started the run and keeps it alive
  const timerRef = useRef<number | null>(null)

  const catalog = useQuery({ queryKey: ['motor', 'calibrations'], queryFn: motorApi.calibrations })
  const parameters = useQuery({ queryKey: ['motor', 'parameters'], queryFn: motorApi.parameters, staleTime: 30_000 })
  const runs = useQuery({ queryKey: ['motor', 'runs'], queryFn: () => motorApi.runs(15) })
  const state = useQuery({
    queryKey: ['motor', 'session', code],
    queryFn: () => motorApi.session(code),
    refetchInterval: (query) => (activeRef.current || query.state.data?.session?.status === 'running' ? 250 : 1500),
  })
  const session = state.data?.session ?? null
  const running = session?.status === 'running'
  const spec = catalog.data?.find((item) => item.code === code) ?? null
  const needsReference = spec?.inputs?.includes('referenceKg') ?? false
  const referenceValue = Number(referenceKg.replace(',', '.'))
  const referenceValid = referenceKg.trim() !== '' && Number.isFinite(referenceValue) && referenceValue >= REFERENCE_KG.min && referenceValue <= REFERENCE_KG.max

  const byCode = useMemo(() => new Map((catalog.data ?? []).map((item) => [item.code, item])), [catalog.data])
  const params = useMemo(() => {
    const map = new Map<string, ParamItem>()
    for (const group of parameters.data?.groups ?? []) for (const item of group.items) if (item.scope === 'side' || item.scope === 'machine') map.set(item.key, item)
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

  const stopHeartbeat = useCallback(() => {
    activeRef.current = false
    if (timerRef.current !== null) { window.clearInterval(timerRef.current); timerRef.current = null }
  }, [])

  const stop = useCallback(async () => {
    stopHeartbeat()
    try { await motorApi.abort() } catch (err) { setError(errorText(err)) }
    await refresh()
  }, [refresh, stopHeartbeat])

  const start = async () => {
    if (activeRef.current || starting || !spec?.runnable || (needsReference && !referenceValid)) return
    setStarting(true)
    setError(null)
    try {
      const next = await motorApi.start(code as RunnableCode, needsReference ? { referenceKg: referenceValue } : {})
      queryClient.setQueryData<CalibrationState>(['motor', 'session', code], next)
      activeRef.current = true
      timerRef.current = window.setInterval(() => {
        // a failed request is not fatal: the backend aborts by itself after 1.5 s without a heartbeat
        motorApi.keepalive()
          .then((result) => { if (!result.running) { stopHeartbeat(); void refresh() } })
          .catch(() => undefined)
      }, KEEPALIVE_MS)
    } catch (err) {
      setError(errorText(err))
      await refresh()
    } finally {
      setStarting(false)
    }
  }

  const reply = async (value: number | null) => {
    setReplying(true)
    setError(null)
    try {
      await motorApi.reply(value)
      await refresh()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setReplying(false)
    }
  }

  useEffect(() => {
    // the screen must stay in front while the bar moves: hiding or leaving it stops the run
    const hidden = () => { if (document.hidden && activeRef.current) void stop() }
    const leave = () => { if (activeRef.current) void stop() }
    document.addEventListener('visibilitychange', hidden)
    window.addEventListener('pagehide', leave)
    return () => {
      document.removeEventListener('visibilitychange', hidden)
      window.removeEventListener('pagehide', leave)
      if (activeRef.current) void stop()
    }
  }, [stop])

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
    if (running || activeRef.current) return
    setUserPicked(true)
    setCode(next)
  }

  const preconditions = state.data?.preconditions ?? []
  const blocked = preconditions.some((item) => !item.ok)
  const history = (runs.data ?? []).filter((run) => !onlySelected || run.code === code)

  return (
    <div className="space-y-6">
    {catalog.data ? <CommissioningPath specs={catalog.data} selected={code} onSelect={select} /> : null}
    <div className="grid gap-6 xl:grid-cols-[minmax(280px,380px)_minmax(0,1fr)]">
      <aside className="space-y-4">
        {catalog.isError ? <p className="text-sm text-[#ff8f84]">Каталог недоступен: {errorText(catalog.error)}</p> : null}
        {catalog.data ? <CatalogList specs={catalog.data} selected={code} onSelect={select} /> : <p className="text-sm text-white/40">Загрузка…</p>}
      </aside>

      <div className="min-w-0 space-y-6">
        {spec ? (
          <section className={cn(card, 'space-y-5')} aria-label="Калибровка">
            <SpecDetails spec={spec} byCode={byCode} params={params} onSelect={select} />

            {spec.runnable ? (
              <>
                {running && session ? (
                  <>
                    {session.prompt ? <PromptPanel key={session.prompt.text} prompt={session.prompt} busy={replying} onReply={(value) => { void reply(value) }} /> : null}
                    <StopButton onStop={() => { void stop() }} />
                    <LiveProgress session={session} durationS={catalog.data?.find((item) => item.code === session.code)?.durationS ?? null} />
                  </>
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
                {!running ? (
                  <StartButton
                    disabled={blocked || busy || (needsReference && !referenceValid)}
                    starting={starting}
                    onStart={() => { void start() }}
                  />
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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-white/80">История</h3>
            <label className="flex items-center gap-2 text-xs text-white/50">
              <input type="checkbox" className="accent-[#b5852f]" checked={onlySelected} onChange={(event) => setOnlySelected(event.target.checked)} />
              только {code === 'WIZARD' ? 'мастер' : code}
            </label>
          </div>
          {history.length ? (
            <ul className="divide-y divide-white/6">
              {history.map((run) => (
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
    </div>
  )
}
