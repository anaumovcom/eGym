import { Fragment, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  comparisonValue,
  formatValue,
  kgfHint,
  type CalibrationChange,
  type CalibrationPrompt,
  type CalibrationSessionPayload,
  type CalibrationStage,
  type Precondition,
  type ReportLine,
} from '@/features/motor/api/motor-api'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { SessionChart } from './session-chart'
import { CalibrationGuide } from './calibration-guide'
import { PriorityMark } from './calibration-priority'
import { FrictionTrackChart, hasWeightDeviation, LiveFrictionCoverage } from './friction-track-chart'
import { isPlotStage, plotNames } from './measurement-model'
import { MeasurementPlot } from './measurement-plot'
import { mapChangeLabel, ParameterMap } from './parameter-map'
import type { CalibrationRun } from './use-calibration-run'

const REFERENCE_KG = { min: 2, max: 60 }
const card = 'rounded-[24px] border border-white/8 bg-white/4 p-5'

function clock(seconds: number): string {
  const value = Math.max(0, Math.round(seconds))
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`
}

function dateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
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
    <div
      className={cn('h-2 overflow-hidden rounded-full bg-white/8', className)}
      role='progressbar'
      aria-label='Выполнение калибровки'
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value * 100)}
    >
      <div
        className='h-full rounded-full bg-linear-to-r from-[#b5852f] to-[#f2cf87]'
        style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }}
      />
    </div>
  )
}

function Preconditions({ items }: { items: Precondition[] }) {
  if (!items.length) return <p className='text-sm text-[#ff8f84]'>Условия запуска ещё не получены.</p>
  return (
    <ul className='grid gap-1.5 sm:grid-cols-2' aria-label='Условия запуска'>
      {items.map((item) => (
        <li key={item.id} className='flex items-start gap-2 text-sm'>
          <span className={cn('mt-0.5 font-bold', item.ok ? 'text-[#79de83]' : 'text-[#ff8f84]')}>{item.ok ? '✓' : '✕'}</span>
          <span>
            <span className={item.ok ? 'text-white/70' : 'text-white'}>{item.label}</span>
            {item.detail ? <span className='block text-xs text-white/40'>{item.detail}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

function StartButton({ disabled, starting, onStart }: { disabled: boolean; starting: boolean; onStart: () => void }) {
  return (
    <button
      type='button'
      disabled={disabled || starting}
      onClick={onStart}
      className={cn(
        'w-full select-none rounded-[28px] border border-[#b5852f]/60 bg-[#b5852f]/15 px-6 py-6 text-center text-[#f4dfb4] transition hover:bg-[#b5852f]/25',
        'disabled:cursor-not-allowed disabled:opacity-40',
      )}
    >
      <span className='block text-lg font-bold'>{starting ? 'Запуск…' : 'Запустить калибровку'}</span>
      <span className='mt-1 block text-xs text-white/45'>
        Держать кнопку не нужно. Не закрывайте и не сворачивайте страницу во время калибровки; для запроса прерывания используйте «СТОП»
      </span>
    </button>
  )
}

function StopButton({ onStop, pending }: { onStop: () => void; pending: boolean }) {
  return (
    <button type="button" onClick={onStop} disabled={pending} className="cal-run-stop" title="Дождитесь подтверждения остановки перед подходом к грифу"
      aria-label="СТОП. Запросить прерывание этой калибровки">СТОП</button>
  )
}

function PromptPanel({ session, prompt, busy, onReply }: {
  session: CalibrationSessionPayload
  prompt: CalibrationPrompt
  busy: boolean
  onReply: (promptText: string, value: number | null) => void
}) {
  const [text, setText] = useState('')
  const value = Number(text.replace(',', '.'))
  const valid = text.trim() !== '' && Number.isFinite(value)
    && (prompt.min === null || value >= prompt.min) && (prompt.max === null || value <= prompt.max)
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (prompt.kind === 'input') { if (valid) onReply(prompt.text, value) } else onReply(prompt.text, null)
  }

  return (
    <form
      id="calibration-operator-prompt"
      onSubmit={submit}
      role='alertdialog'
      aria-label='Действие оператора'
      className={cn(
        'space-y-3 rounded-[22px] border-2 p-5',
        prompt.kind === 'action' ? 'border-[#7fb8ff]/60 bg-[#7fb8ff]/10' : 'border-[#f2cf87]/70 bg-[#f2cf87]/10',
      )}
    >
      <p className='text-xs font-semibold uppercase tracking-[0.14em] text-white/50'>
        {prompt.kind === 'action' ? 'Выполните действие — тренажёр сам заметит его' : 'Требуется ваше действие'}
      </p>
      <p className='text-lg font-semibold leading-snug text-white'>{prompt.text}</p>
      {prompt.kind === 'input' ? (
        <label className='block space-y-1.5'>
          <span className='block text-sm text-white/80'>{prompt.label ?? 'Значение'}{prompt.unit ? `, ${prompt.unit}` : ''}</span>
          <input
            type='number'
            inputMode='decimal'
            autoFocus
            min={prompt.min ?? undefined}
            max={prompt.max ?? undefined}
            step='any'
            value={text}
            onChange={(event) => setText(event.target.value)}
            className={cn(
              'w-48 rounded-xl border bg-black/30 px-3 py-2 text-lg text-white outline-none focus:border-[#b5852f]',
              text && !valid ? 'border-[#ff8f84]/70' : 'border-white/15',
            )}
          />
          {prompt.min !== null && prompt.max !== null ? (
            <span className='block text-xs text-white/40'>Допустимо {prompt.min.toLocaleString('ru-RU')}–{prompt.max.toLocaleString('ru-RU')}{prompt.unit ? ` ${prompt.unit}` : ''}</span>
          ) : null}
        </label>
      ) : null}
      {prompt.kind !== 'action' && <p className='text-xs text-white/45'>После подтверждения начнётся следующий этап.</p>}
      {prompt.kind === 'action' ? (
        <Button type='submit' variant='ghost' disabled={busy}>{session.currentStage === 'G3' ? 'Завершить попытку' : 'Пропустить'}</Button>
      ) : (
        <Button type='submit' disabled={busy || (prompt.kind === 'input' && !valid)}>Готово</Button>
      )}
      <span className='sr-only'>Сессия {session.id}</span>
    </form>
  )
}

function readable(text: string) {
  return text.replace(/\bleft\b/gi, 'левая сторона').replace(/\bright\b/gi, 'правая сторона')
}

function stopHelp(reason: string) {
  if (/с экраном|heartbeat|свёрнут/i.test(reason)) return 'Экран перестал подтверждать наблюдение. Восстановите связь и откройте страницу калибровки перед повтором.'
  if (/скорост.*огибающ|превышение скорости/i.test(reason)) return 'Скорость вышла за предел измерения. На графике скорости найдите сторону и момент скачка, затем сверьте их с изменением высоты.'
  if (/позици.*огибающ|границ.*хода/i.test(reason)) return 'Каретка вышла за рабочие границы этого замера. Сверьте ноль и измеренный ход с положением грифа.'
  if (/перекос|рассинхр/i.test(reason)) return 'Сравните графики высоты и перекоса. Осмотрите направляющие на высоте, где линии начали расходиться.'
  if (/modbus|нет ответа|нет связи с привод|телеметри/i.test(reason)) return 'Проверьте связь с указанным приводом. После восстановления должны снова появиться показания обеих сторон.'
  return null
}

function LiveProgress({ session, durationS, updatedAt, connectionError, stopping, onStop }: {
  session: CalibrationSessionPayload; durationS: number | null; updatedAt: number; connectionError: boolean; stopping: boolean; onStop?: () => void
}) {
  const [clockMs, setClockMs] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setClockMs(Date.now()), 750)
    return () => window.clearInterval(timer)
  }, [])
  const current = session.stages.find((stage) => stage.code === session.currentStage)
  const index = current ? session.stages.indexOf(current) : 0
  const next = session.stages[index + 1]
  const previous = session.stages[index - 1]
  const log = session.stageLog ?? session.log
  const late = connectionError || (updatedAt > 0 && clockMs - updatedAt > 3000)
    || (session.frameAgeS != null && session.staleAfterS != null && session.frameAgeS > session.staleAfterS)
  const state = stopping ? 'Ожидание подтверждения остановки. Держитесь в стороне от грифа.'
    : late ? 'Данные задерживаются. Показан последний полученный кадр.'
    : session.prompt ? 'Ожидание вашего действия' : !log.t.length ? 'Ожидание первого кадра' : 'Идёт измерение'
  const num = (value: number | undefined, digits = 1) => value == null ? '—' : value.toLocaleString('ru-RU', { maximumFractionDigits: digits })
  const pair = (a: number[], b: number[], scale = 1, digits = 1) => [a.at(-1), b.at(-1)].map(v => num(v == null ? undefined : v / scale, digits)).join(' / ')
  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-end justify-between gap-2'>
        <div>
          <p className='text-xs uppercase tracking-[0.14em] text-white/60'>{session.stages.length > 1 ? `Этап ${index + 1} из ${session.stages.length}` : 'Сейчас выполняется'}</p>
          <div>
            <p className='text-lg font-semibold text-[#f4dfb4]'>{current ? `${current.code} · ${current.title}` : session.title}</p>
            <PriorityMark code={current?.code ?? session.code} explain />
          </div>
          <p className='text-sm text-white/70'>{readable(session.note || 'Подготовка измерения…')}</p>
        </div>
        <div className='text-right'>
          <p className='font-display text-3xl font-bold text-white'>{Math.round(session.progress * 100)}%</p>
          <p className='text-xs text-white/45'>{clock(session.elapsedS)}{durationS ? ` из ~${clock(durationS)}` : ''}</p>
        </div>
      </div>
      <ProgressBar value={session.progress} className='h-3' />
      <CalibrationGuide code={current?.code ?? session.code} title={current?.title ?? session.title} />
      {next && <p className="cal-up-next">Дальше автоматически · {next.title}</p>}
      {log.t.length > 0 && <div className="cal-signal-readings" aria-label="Последний кадр, левая и правая стороны">
        <p>Последний кадр · левая / правая</p>
        <dl><div><dt>Высота, мм</dt><dd>{pair(log.xL, log.xR)}</dd></div>
          <div><dt>Скорость, м/с</dt><dd>{pair(log.vL, log.vR, 1000, 3)}</dd></div>
          <div><dt>Усилие привода, Н</dt><dd>{pair(log.fL, log.fR)}</dd></div></dl>
      </div>}
      {session.currentStage === 'S10' && session.frictionCoverage && <LiveFrictionCoverage coverage={session.frictionCoverage} />}
      {current && isPlotStage(current.code) && (current.result?.partial
        ? <MeasurementPlot key={current.code} code={current.code} result={current.result} live />
        : <p className="mp-progress" role="status">График «{plotNames[current.code]}» появится после первой завершённой точки замера.</p>)}
      <SessionChart log={log} code={session.currentStage ?? session.code} zone={current ? current.workingZone : session.workingZone} />
      {previous && <details><summary>Последний замер · {previous.title}</summary><ReportTable stages={[previous]} /></details>}
      {session.stages.length > 1 && <details><summary>Все этапы серии</summary><StageList stages={session.stages} /></details>}
      <div className="cal-observer-dock">
        <div className="cal-monitor-status" data-tone={stopping || late || session.prompt ? 'warn' : 'good'}>
          <strong role="status">{state}</strong><span>{current?.code ?? session.code} · {Math.round(session.progress * 100)} %
            {current?.frames != null && ` · кадров на этапе ${current.frames}`}</span>
          {session.prompt && onStop && <a href="#calibration-operator-prompt" className="cal-link">К действию</a>}
        </div>
        {onStop && <StopButton onStop={onStop} pending={stopping} />}
      </div>
    </div>
  )
}

function StageList({ stages }: { stages: CalibrationStage[] }) {
  if (stages.length < 2) return null
  return (
    <ol className='grid gap-2 sm:grid-cols-3' aria-label='Этапы'>
      {stages.map((stage) => (
        <li key={stage.code} className={cn('rounded-[18px] border p-3', stage.status === 'running' ? 'border-[#b5852f]/60 bg-[#b5852f]/10' : 'border-white/8 bg-white/3')}>
          <div className='flex items-center gap-2'>
            <StageIcon status={stage.status} />
            <span className='min-w-0 text-sm'><span className='font-mono text-white/50'>{stage.code}</span> <span className='text-white'>{stage.title}</span>
              <span className="cal-procedure-meta"><PriorityMark code={stage.code} /></span>
            </span>
          </div>
          {stage.status === 'running' ? <ProgressBar value={stage.progress} className='mt-2' /> : null}
          {stage.reason ? <p className='mt-1 text-xs text-[#ff8f84]'>{stage.reason}</p> : null}
        </li>
      ))}
    </ol>
  )
}

function stageReport(stage: CalibrationStage): ReportLine[] {
  const report = stage.result?.report
  return Array.isArray(report) ? (report as ReportLine[]) : []
}

export function CalibrationFindings({ stages, onStage }: { stages: CalibrationStage[]; onStage?: (code: string) => void }) {
  // In gain searches, rejected candidates belong in the detailed report. B8, S8 and
  // S10 also report end-stop and rail findings even when the measurement completed.
  const inspected = stages.filter(s => s.verification || s.status === 'failed' || ['B8', 'S8', 'S10'].includes(s.code))
  const findings = inspected.map(stage => ({ stage, flags: stageReport(stage).filter(line => line.ok === false) })).filter(group => group.flags.length)
  if (!findings.length) return null
  return <section className="cal-findings" aria-label="Замечания протокола"><h4>На что обратить внимание</h4>
    {findings.map(({ stage, flags }) => <div key={stage.code}>
      {onStage ? <button type="button" className="cal-link" onClick={() => onStage(stage.code)}>{stage.code} · {stage.title}</button>
        : <strong>{stage.code} · {stage.title}</strong>}
      <ul>{flags.map((line, i) => <li key={i}>{line.label} · {line.value}</li>)}</ul>
      {stage.code === 'S8' && <p>Осмотрите направляющие на указанных высотах. После обслуживания повторите S8.</p>}
      {stage.code === 'S10' && hasWeightDeviation(stage) && <p>Сверьте баланс грифа по высоте в S7, затем повторите карту трения S10.</p>}
    </div>)}
  </section>
}

export function ReportTable({ stages }: { stages: CalibrationStage[] }) {
  const blocks = stages.map((stage) => ({ stage, lines: stageReport(stage) }))
    .filter(({ stage, lines }) => lines.length || (isPlotStage(stage.code) && stage.result?.partial))
  if (!blocks.length) return null
  return (
    <div className='space-y-3' aria-label='Отчёт измерения'>
      {blocks.map(({ stage, lines }) => (
        <div key={stage.code} className='rounded-[18px] border border-white/8 bg-black/15 p-3'>
          {blocks.length > 1 ? <p className='mb-2 text-xs text-white/40'><span className='font-mono'>{stage.code}</span> {stage.title}</p> : null}
          {stage.code === 'S10' && <FrictionTrackChart stage={stage} />}
          {isPlotStage(stage.code) && stage.result && <details className="mp-inline" open={blocks.length === 1}>
            <summary>График · {plotNames[stage.code]}</summary>
            <MeasurementPlot code={stage.code} result={stage.result} />
          </details>}
          {lines.some(line => line.comparison) && <p className="cal-comparison-caption">Вертикальная отметка на каждой шкале показывает допуск.</p>}
          <ul className='divide-y divide-white/6'>
            {lines.map((line, index) => (
              <li key={`${line.label}-${index}`} className='flex flex-wrap items-start justify-between gap-x-4 gap-y-0.5 py-1.5 text-sm'>
                <span className='text-white/60'>{line.label}</span>
                <span className={cn('text-right', line.ok === false ? 'text-[#ff8f84]' : line.ok ? 'text-[#79de83]' : 'text-white')}>
                  {line.ok === false ? '✕ ' : line.ok ? '✓ ' : ''}{line.value}
                  {line.comparison && line.comparison.limit > 0 && <span className="cal-comparison" aria-hidden="true">
                    <i data-exceeded={line.ok === false} style={{ width: `${Math.min(100, 100 * line.comparison.value / (1.5 * line.comparison.limit))}%` }} />
                  </span>}
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
  if (!info) return <span className='text-white/30'>—</span>
  const hint = kgfHint(info.value, change.unit)
  return (
    <span>
      <span className={which === 'new' ? 'font-semibold text-white' : 'text-white/55'}>{info.points != null && (change.kind === 'table' || info.points > 1)
        ? `Точек в карте · ${info.points}` : comparisonValue(info.value, change[which === 'old' ? 'new' : 'old']?.value, change.kind, change.unit)}</span>
      {info.ci95 != null ? <span className='text-xs text-white/55' title="95 % доверительный интервал"> ± {formatValue(info.ci95, 'float', '')}</span> : null}
      {hint ? <span className='block text-xs text-white/35'>{hint}</span> : null}
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

export function ChangesTable({ changes }: { changes: CalibrationChange[] }) {
  return (
    <div className='overflow-x-auto'>
      <table className='w-full text-sm'>
        <thead>
          <tr className='text-left text-xs uppercase tracking-[0.1em] text-white/35'>
            <th className='py-2 pr-3 font-medium'>Параметр</th>
            <th className='py-2 pr-3 font-medium'>Сторона</th>
            <th className='py-2 pr-3 font-medium'>Было</th>
            <th className='py-2 pr-3 font-medium'>Стало</th>
            <th className='py-2 pr-3 font-medium'>Изменение</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change) => {
            const map = change.kind === 'table' || change.kind === 'weight'
            const same = change.old?.value != null && change.old.value === change.new?.value
            const delta = map ? null : changeDelta(change)
            return (
              <Fragment key={`${change.scope}-${change.key}-${change.side ?? ''}`}><tr className={cn('border-t border-white/6 align-top', !change.changed && 'opacity-55')}>
                <td className='py-2 pr-3 text-white/80'>{change.label}</td>
                <td className='py-2 pr-3 text-white/50'>{change.side === 'left' ? 'Левая' : change.side === 'right' ? 'Правая' : '—'}</td>
                <td className='py-2 pr-3'><ChangeValue change={change} which='old' /></td>
                <td className='py-2 pr-3'><ChangeValue change={change} which='new' /></td>
                <td className='py-2 pr-3 text-xs'>
                  {map ? mapChangeLabel(change) : !change.changed ? 'без изменений'
                    : delta ? <span className={delta.large ? 'text-[#f2cf87]' : 'text-white/60'}>{delta.text}</span>
                    : same ? 'подтверждено измерением' : change.old?.value == null ? 'первое значение' : 'изменилось значение'}
                </td>
              </tr>{map && <tr><td colSpan={5}><ParameterMap paramKey={change.key} unit={change.unit} label={`Сравнить точки · ${change.label}${change.side ? change.side === 'left' ? ' · левая' : ' · правая' : ''}`}
                series={[{ name: 'Было', info: change.old }, { name: 'Стало', info: change.new }]} /></td></tr>}</Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ResultPanel({ run, guided, onNext }: { run: CalibrationRun; guided: boolean; onNext?: () => void }) {
  const session = run.session
  const resultRef = useRef<HTMLElement>(null)
  useEffect(() => {
    resultRef.current?.scrollIntoView?.({ block: 'start' })
  }, [session?.id])
  if (!session) return null
  const head = session.status === 'done'
    ? { title: 'Калибровка завершена', className: 'text-[#79de83]' }
    : session.status === 'aborted'
      ? { title: 'Калибровка прервана', className: 'text-[#f2cf87]' }
      : { title: 'Калибровка не удалась', className: 'text-[#ff8f84]' }
  const pending = session.status === 'done' && session.hasChanges && session.savedVersion === null
  const proposedLimit = session.code === 'B8' ? session.stages[0]?.result?.suggestedSoftMaxMm : null
  const isSeries = session.stages.length > 1
  const failedStage = session.stages.find(stage => stage.status === 'failed' || stage.status === 'aborted')
  const track = session.stages.find(stage => stage.code === 'S10' && stage.result?.track)
  const technical = (
    <>
      <StageList stages={session.stages} />
      <ReportTable stages={session.stages} />
    </>
  )

  return (
    <section ref={resultRef} className={cn(card, 'space-y-4 cal-result')} aria-label='Результат калибровки'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <h3 className={cn('text-lg font-semibold', head.className)}>{head.title}</h3>
          <div className="cal-stage-title"><p className='text-sm text-white/55'>{session.title} · {dateTime(session.startedAt)} · {clock(session.elapsedS)}</p>
            <PriorityMark code={session.code} /></div>
          {session.reason ? <div className="cal-stop-reason" role="alert"><strong>{readable(session.reason)}</strong>
            {stopHelp(session.reason) && <p>{stopHelp(session.reason)}</p>}</div> : null}
        </div>
        {session.savedVersion !== null ? <Badge label={`сохранено · профиль v${session.savedVersion}`} className='bg-[#79de83]/15 text-[#79de83]' /> : null}
      </div>
      {session.status === 'done' && <CalibrationFindings stages={session.stages} />}
      {session.status !== 'done' && <div>
        <CalibrationGuide code={failedStage?.code ?? session.code} title={failedStage?.title ?? session.title} />
        <p className='mb-1 text-sm text-white/65'>К моменту остановки выполнено {Math.round(session.progress * 100)} %</p>
        <ProgressBar value={session.progress} />
      </div>}
      {session.status === 'done' && <CalibrationGuide code={session.code} title={session.title} />}
      {isSeries && <p className='text-sm text-white/70'>Завершено замеров · {session.stages.filter(s => s.status === 'done').length} из {session.stages.length}</p>}
      {isSeries && failedStage && <ReportTable stages={[failedStage]} />}
      {failedStage && <SessionChart log={session.stageLog ?? session.log} code={failedStage.code} zone={failedStage.workingZone} />}
      {track && isSeries && failedStage !== track && <FrictionTrackChart stage={track} />}
      {guided || isSeries ? <details className='text-sm text-white/50'><summary className='cursor-pointer select-none'>Этапы и протокол измерения</summary><div className='mt-3 space-y-3'>{technical}</div></details> : technical}
      {session.status === 'done' && session.changes.length ? (
        <>
          <p className='text-sm text-white/60'>
            {pending ? 'Новые значения ещё не применены. Сохраните их в профиль, чтобы тренажёр начал их использовать.' : 'Измеренные значения:'}
          </p>
          {isSeries ? <details><summary>Сравнить значения параметров · {session.changes.length}</summary><ChangesTable changes={session.changes} /></details> : <ChangesTable changes={session.changes} />}
        </>
      ) : null}
      {session.status !== 'done' ? <p className='text-sm text-white/55'>Профиль не изменён. Перед повтором проверьте состояние тренажёра.</p> : null}
      {session.status === 'done' && !session.changes.length ? <p className='text-sm text-white/55'>Проверка пройдена, параметры профиля не меняются.</p> : null}
      {(!failedStage || isSeries) && <details className='text-sm text-white/50'>
        <summary className='cursor-pointer select-none'>График записи</summary>
        <div className='mt-3'><SessionChart log={session.log} code={session.code} zone={session.workingZone} /></div>
      </details>}
      {pending && <p className='text-xs text-white/50'>Сохраните или отклоните изменения перед следующим запуском.</p>}
      {pending && typeof proposedLimit === 'number' && <p className="cal-limit-proposal">Текущий верхний предел выходит за измеренный ход. Если обе каретки действительно дошли до верхних упоров, сохраните ход и предел {proposedLimit} мм. Если гриф остановился на тугом месте, отклоните замер и осмотрите направляющие.</p>}
      <div className='flex flex-wrap gap-3'>
        {pending && typeof proposedLimit === 'number' ? <Button disabled={run.busy} onClick={() => {
          if (window.confirm(`Обе каретки дошли до верхних упоров? Сохранить ход и уменьшить верхний предел до ${proposedLimit} мм?`)) void run.accept(true)
        }}>Сохранить ход и предел {proposedLimit} мм</Button> : pending && isSeries && onNext ? (
          <Button disabled={run.busy} onClick={async () => { if (await run.accept() && await run.discard()) onNext() }}>Сохранить серию и продолжить</Button>
        ) : pending ? <Button onClick={() => { if (window.confirm('Сохранить новые значения в профиль и применить их?')) void run.accept() }} disabled={run.busy}>Сохранить новые значения</Button> : null}
        {!pending && session.status === 'done' && onNext && <Button disabled={run.busy} onClick={async () => { if (await run.discard()) onNext() }}>К следующему этапу</Button>}
        <Button variant={pending ? 'ghost' : 'secondary'} onClick={() => { void run.discard() }} disabled={run.busy}>{pending ? 'Отклонить' : 'Закрыть'}</Button>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ shared controls
export function CalibrationRunControls({ run, guided = false, onNext }: { run: CalibrationRun; guided?: boolean; onNext?: () => void }) {
  const spec = run.spec
  const needsReference = spec?.inputs?.includes('referenceKg') ?? false
  const [referenceKg, setReferenceKg] = useState('')
  const [physicalOk, setPhysicalOk] = useState(false)
  const wasRunning = useRef(false)

  // A fresh physical check is required before every start: reset once a run has completed.
  useEffect(() => {
    const was = wasRunning.current
    wasRunning.current = run.running
    if (was && !run.running) setPhysicalOk(false)
  }, [run.running])

  const preconditions = run.state.data?.preconditions ?? []
  const referenceValue = Number(referenceKg.replace(',', '.'))
  const referenceValid = referenceKg.trim() !== '' && Number.isFinite(referenceValue)
    && referenceValue >= REFERENCE_KG.min && referenceValue <= REFERENCE_KG.max

  const startBlocked = !run.canStart || (needsReference && !referenceValid) || (guided && !physicalOk)

  const onStart = () => {
    setPhysicalOk(false)
    void run.start(needsReference ? referenceValue : undefined)
  }

  if (run.running) {
    return (
      <>
        {run.ownsRun && run.session?.prompt ? (
          <PromptPanel key={run.session.prompt.text} session={run.session} prompt={run.session.prompt} busy={run.busy} onReply={(text, value) => { void run.reply(text, value) }} />
        ) : null}
        {!run.ownsRun && (
          <p role='alert' className='rounded-[18px] bg-[#b5852f]/10 px-4 py-3 text-sm text-[#f2cf87]'>
            Калибровка выполняется на другом экране. Этот экран ею не управляет.
          </p>
        )}
        {run.session ? <LiveProgress session={run.session} updatedAt={run.state.dataUpdatedAt} connectionError={run.state.isError} stopping={run.stopping}
          onStop={run.ownsRun ? () => { void run.stop() } : undefined} durationS={spec?.code === run.session.code ? spec.durationS : null} /> : null}
      </>
    )
  }

  if (run.session) return <ResultPanel run={run} guided={guided} onNext={onNext} />

  if (!spec?.runnable) {
    return spec
      ? <p className='rounded-[18px] bg-white/4 px-4 py-3 text-sm text-white/50'>Запуск этой калибровки из интерфейса пока не реализован.</p>
      : null
  }

  return (
    <section className={cn(card, 'space-y-4')} aria-label='Разрешение запуска'>
      <h4 className='text-xs font-semibold uppercase tracking-[0.14em] text-white/35'>Перед запуском</h4>
      {run.state.isError ? <p className='text-sm text-[#ff8f84]'>Не удалось получить актуальные условия запуска.</p> : null}
      {guided ? (
        <details className='text-sm text-white/70'>
          <summary className='cursor-pointer select-none'>
            Условия запуска: {preconditions.filter((item) => item.ok).length} из {preconditions.length}
            {preconditions.length > 0 && preconditions.every((item) => item.ok) ? ' ✓' : ''}
          </summary>
          <div className='mt-3'><Preconditions items={preconditions} /></div>
        </details>
      ) : <Preconditions items={preconditions} />}
      {needsReference ? (
        <label className='block space-y-1.5 pt-1'>
          <span className='block text-sm text-white/80'>Масса эталонного груза на грифе, кг</span>
          <input
            type='number'
            inputMode='decimal'
            min={REFERENCE_KG.min}
            max={REFERENCE_KG.max}
            step={0.1}
            value={referenceKg}
            onChange={(event) => setReferenceKg(event.target.value)}
            placeholder='например, 20'
            className={cn(
              'w-40 rounded-xl border bg-black/30 px-3 py-2 text-white outline-none focus:border-[#b5852f]',
              referenceKg && !referenceValid ? 'border-[#ff8f84]/70' : 'border-white/15',
            )}
          />
          <span className='block text-xs text-white/40'>Половина на каждую сторону, масса взвешена на весах. Допустимо {REFERENCE_KG.min}–{REFERENCE_KG.max} кг.</span>
        </label>
      ) : null}
      {guided ? (
        <label className='flex items-start gap-2 pt-1 text-sm text-white/80'>
          <input type='checkbox' className='mt-0.5 accent-[#b5852f]' checked={physicalOk} onChange={(event) => setPhysicalOk(event.target.checked)} />
          <span>Я проверил: гриф на нижних упорах, рабочая зона свободна</span>
        </label>
      ) : null}
      <StartButton disabled={startBlocked} starting={run.starting} onStart={onStart} />
    </section>
  )
}
