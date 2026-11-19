import { memo, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  PROVENANCE_LABEL,
  formatValue,
  kgfHint,
  motorApi,
  type ParamItem,
  type ParameterChangeRequest,
  type ParameterPreview,
  type ResetScope,
  type Side,
  type ValueInfo,
} from '@/features/motor/api/motor-api'
import { ApiError } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { CalibrationRecordView } from './calibration-record'
import { ParameterMap, mapAxes } from './parameter-map'
import { ParameterReview } from './parameter-review'

type Draft = Record<string, string | boolean>
type Filter = 'all' | 'measured' | 'manual' | 'default'

const RESETS: { scope: ResetScope; label: string; warning: string }[] = [
  { scope: 'calibrations', label: 'Сбросить калибровки', warning: 'Все измеренные значения тренажёра вернутся к паспортным; калибровки придётся пройти заново. Направление двигателей и ноль энкодера сохранятся.' },
  { scope: 'parameters', label: 'Сбросить настройки', warning: 'Настройки поведения и пределы безопасности вернутся к значениям по умолчанию.' },
  { scope: 'all', label: 'Сбросить всё', warning: 'Калибровки и настройки вернутся к значениям по умолчанию. Направление двигателей и ноль энкодера сохранятся.' },
]

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'Все' },
  { id: 'measured', label: 'Измерено' },
  { id: 'manual', label: 'Вручную' },
  { id: 'default', label: 'Не измерено' },
]

function provenances(item: ParamItem): ValueInfo['provenance'][] {
  return item.values ? [item.values.left.provenance, item.values.right.provenance] : item.value ? [item.value.provenance] : []
}

function matches(item: ParamItem, filter: Filter, query: string): boolean {
  const kinds = provenances(item)
  if (filter === 'default' && !kinds.some((kind) => kind === 'default' || kind === 'derived')) return false
  if ((filter === 'measured' || filter === 'manual') && !kinds.includes(filter)) return false
  const text = query.trim().toLowerCase()
  return !text || [item.label, item.description, item.key, ...item.producedBy].some((part) => part.toLowerCase().includes(text))
}

const PROVENANCE_CLASS: Record<ValueInfo['provenance'], string> = {
  measured: 'bg-[#79de83]/15 text-[#79de83]',
  manual: 'bg-[#7fb8ff]/15 text-[#7fb8ff]',
  default: 'bg-white/6 text-white/45',
  derived: 'bg-[#f2cf87]/15 text-[#f2cf87]',
}

function draftKey(item: ParamItem, side: Side | null): string {
  return `${item.scope}|${item.key}|${side ?? ''}`
}

function editableValue(item: ParamItem, info: ValueInfo): boolean {
  return item.editable && !(item.kind === 'weight' && (info.points ?? 1) > 1)
}

function parse(item: ParamItem, raw: string | boolean): { value: number | boolean | null; error: string | null } {
  if (typeof raw === 'boolean') return { value: raw, error: null }
  const value = Number(raw.replace(',', '.'))
  if (raw.trim() === '' || !Number.isFinite(value)) return { value: null, error: 'введите число' }
  if ((item.kind === 'int' || item.kind === 'counts') && !Number.isInteger(value)) return { value: null, error: 'целое число' }
  if (item.min !== null && value < item.min) return { value: null, error: `не меньше ${item.min}` }
  if (item.max !== null && value > item.max) return { value: null, error: `не больше ${item.max}` }
  return { value, error: null }
}

function ValueCell({ item, info, side, draft, canEdit, onChange, onSource, source }: {
  item: ParamItem
  info: ValueInfo
  side: Side | null
  draft: Draft
  canEdit: boolean
  onChange: (key: string, value: string | boolean | undefined) => void
  onSource: (id: string) => void
  source: string | null
}) {
  const key = draftKey(item, side)
  const raw = draft[key]
  const edit = canEdit && editableValue(item, info)
  const parsed = raw === undefined ? null : parse(item, raw)
  const changed = parsed !== null && parsed.error === null && parsed.value !== info.value
  const hint = kgfHint(info.value, item.unit)
  const label = side === 'left' ? 'Левая' : side === 'right' ? 'Правая' : null
  const rows = info.rows
  const axes = mapAxes(item.key, item.unit)
  const origin = item.effective ?? info

  return (
    <div className={cn('rounded-[16px] border px-3 py-2', changed ? 'border-[#b5852f]/60 bg-[#b5852f]/10' : 'border-white/8 bg-black/15')}>
      {label ? <p className="text-[11px] uppercase tracking-[0.12em] text-white/35">{label}</p> : null}
      {item.effective && <p className="text-xs text-white/65">Базовое значение</p>}
      {edit && item.kind === 'bool' ? (
        <label className="flex items-center gap-2 py-1 text-sm text-white">
          <input
            type="checkbox"
            className="h-5 w-5 accent-[#b5852f]"
            checked={typeof raw === 'boolean' ? raw : Boolean(info.value)}
            onChange={(event) => onChange(key, event.target.checked === info.value ? undefined : event.target.checked)}
            aria-label={`${item.label}${label ? ` (${label})` : ''}`}
          />
          {(typeof raw === 'boolean' ? raw : Boolean(info.value)) ? 'включено' : 'выключено'}
        </label>
      ) : edit ? (
        <div className="flex items-center gap-2">
          <input
            type="number"
            inputMode="decimal"
            min={item.min ?? undefined}
            max={item.max ?? undefined}
            step={item.step ?? 'any'}
            value={typeof raw === 'string' ? raw : String(info.value ?? '')}
            onChange={(event) => onChange(key, event.target.value === String(info.value) ? undefined : event.target.value)}
            aria-label={`${item.label}${label ? ` (${label})` : ''}`}
            aria-invalid={parsed?.error ? true : undefined}
            className={cn(
              'w-full min-w-0 rounded-xl border bg-white/6 px-3 py-1.5 text-sm text-white outline-none focus:border-[#d6b05f]',
              parsed?.error ? 'border-[#ff8f84]' : 'border-white/10',
            )}
          />
          {item.unit ? <span className="shrink-0 text-xs text-white/45">{item.unit}</span> : null}
        </div>
      ) : rows ? (
        <details className="cal-map-values"><summary>{rows.length ? `Точки измерения · ${rows.length}` : item.key === 'tight_spots' ? 'Тугих участков не обнаружено' : 'Карта пуста'}</summary>
          {rows.length > 0 && <table><thead><tr><th>{axes.x}, {axes.xUnit}</th><th>{axes.y}, {axes.yUnit}</th></tr></thead>
            <tbody>{rows.map(([x, y], i) => <tr key={i}><td>{formatValue(x, 'float', '')}</td>
              <td>{formatValue(y * axes.factor, 'float', '')}</td></tr>)}</tbody></table>}
        </details>
      ) : (
        <p className="py-1 text-sm font-medium text-white">{formatValue(info.value, item.kind, item.unit)}</p>
      )}
      {parsed?.error ? <p className="text-xs text-[#ff8f84]">{parsed.error}</p> : null}
      {item.effective && <p className="mt-1 text-sm text-[#79de83]">Контроллер использует {formatValue(item.effective.value, item.kind, item.unit)}
        {' · '}{item.effective.label}{item.effective.procedure ? ` (${item.effective.procedure})` : ''}.</p>}
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-white/40">
        <span className={cn('rounded-full px-2 py-0.5', PROVENANCE_CLASS[info.provenance])}>{PROVENANCE_LABEL[info.provenance]}</span>
        {info.ci95 != null ? <span title="95 % доверительный интервал">95 % ДИ ± {formatValue(info.ci95, 'float', item.unit)}</span> : null}
        {hint ? <span>{hint}</span> : null}
        {item.kind === 'weight' && (info.points ?? 1) > 1 ? <span>{info.points} точек по высоте</span> : null}
        {changed ? <span className="text-[#f2cf87]">было {formatValue(info.value, item.kind, item.unit)}</span> : null}
      </div>
      {(origin.measuredAt || origin.runId) && <div className="cal-value-source">
        {origin.measuredAt && <time dateTime={origin.measuredAt}>{new Date(origin.measuredAt).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}</time>}
        {origin.runId === 'reset_zero_position' ? <span>Ноль задан оператором</span> : origin.runId && <button type="button" className="cal-link"
          aria-expanded={source === origin.runId} aria-label={`Запись замера · ${item.label}${label ? ' · ' + label : ''}`}
          onClick={() => onSource(origin.runId!)}>{source === origin.runId ? 'Скрыть запись' : 'Запись замера'}</button>}
      </div>}
    </div>
  )
}

function SideDifference({ item }: { item: ParamItem }) {
  if (!item.values || item.kind !== 'float') return null
  const { left, right } = item.values
  if (left.provenance !== 'measured' || right.provenance !== 'measured' || typeof left.value !== 'number' || typeof right.value !== 'number') return null
  const difference = right.value - left.value
  return <p className="cal-side-difference">Правая минус левая · {difference > 0 ? '+' : ''}{formatValue(difference, 'float', item.unit)}
    {left.runId && right.runId && left.runId !== right.runId && ' · замеры из разных запусков'}</p>
}

function ParamRow({ item, draft, canEdit, onChange, onOpen }: {
  item: ParamItem
  draft: Draft
  canEdit: boolean
  onChange: (key: string, value: string | boolean | undefined) => void
  onOpen: (code: string) => void
}) {
  const [source, setSource] = useState<string | null>(null)
  const toggleSource = (id: string) => setSource(previous => previous === id ? null : id)
  const series = item.values ? [{ name: 'Левая', info: item.values.left }, { name: 'Правая', info: item.values.right }] : [{ name: 'Профиль', info: item.value }]
  return (
    <li className="grid gap-3 border-t border-white/6 py-4 first:border-t-0 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-white">{item.label}</span>
          {!item.editable ? <span className="rounded-full bg-white/6 px-2 py-0.5 text-[11px] text-white/40">только калибровкой</span> : null}
          {item.producedBy.map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => onOpen(code)}
              title={`Открыть калибровку ${code}`}
              className="rounded-full bg-[#b5852f]/15 px-2 py-0.5 text-[11px] text-[#f2cf87] hover:bg-[#b5852f]/30"
            >
              измеряет {code} →
            </button>
          ))}
          {item.restart ? <span className="rounded-full bg-[#ff8f84]/10 px-2 py-0.5 text-[11px] text-[#ff8f84]">после перезапуска</span> : null}
        </div>
        <p className="mt-1 text-sm leading-relaxed text-white/55">{item.description}</p>
        <p className="mt-1 font-mono text-[11px] text-white/25">
          {item.key}{item.min !== null || item.max !== null ? ` · ${item.min ?? '−∞'} … ${item.max ?? '∞'}${item.unit ? ` ${item.unit}` : ''}` : ''}
        </p>
      </div>
      <div className={cn('grid gap-2', item.values ? 'grid-cols-2' : 'grid-cols-1')}>
        {item.values
          ? (['left', 'right'] as const).map((side) => (
              <ValueCell key={side} item={item} info={item.values![side]} side={side} draft={draft} canEdit={canEdit} onChange={onChange} onSource={toggleSource} source={source} />
            ))
          : item.value
            ? <ValueCell item={item} info={item.value} side={null} draft={draft} canEdit={canEdit} onChange={onChange} onSource={toggleSource} source={source} />
            : null}
        <SideDifference item={item} />
      </div>
      {(item.kind === 'weight' || item.kind === 'table') && series.some(s => s.info?.rows != null || s.info?.points != null) &&
        <div className="cal-param-evidence"><ParameterMap paramKey={item.key} unit={item.unit} label={item.values ? 'Сравнить карты левой и правой сторон' : 'График точек профиля'} series={series} /></div>}
      {source && <section className="cal-param-evidence cal-source-record" aria-label={`Источник параметра · ${item.label}`}>
        <CalibrationRecordView key={source} runId={source} parameter={item.effective?.key ? { scope: 'machine', key: item.effective.key } : item} />
      </section>}
    </li>
  )
}

export const ParametersTab = memo(function ParametersTab({ serviceMode, calibrating }: { serviceMode: boolean; calibrating: boolean }) {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['motor', 'parameters'], queryFn: motorApi.parameters })
  const [draft, setDraft] = useState<Draft>({})
  const [saving, setSaving] = useState(false)
  const [review, setReview] = useState<{ result: ParameterPreview; request: ParameterChangeRequest[] } | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [, setSearchParams] = useSearchParams()
  const canEdit = serviceMode && !calibrating
  const openCalibration = (code: string) => setSearchParams({ tab: 'calibrations', code })

  const summary = useMemo(() => {
    const counts: Record<ValueInfo['provenance'], number> = { measured: 0, manual: 0, default: 0, derived: 0 }
    for (const group of query.data?.groups ?? []) {
      for (const item of group.items) if (item.scope === 'side' || item.scope === 'machine') for (const kind of provenances(item)) counts[kind] += 1
    }
    return counts
  }, [query.data])
  const groups = useMemo(
    () => (query.data?.groups ?? []).map((group) => ({ ...group, items: group.items.filter((item) => matches(item, filter, search)) })),
    [query.data, filter, search],
  )

  const items = useMemo(() => new Map<string, ParamItem>((query.data?.groups ?? []).flatMap((group) => group.items.map((item) => [`${item.scope}|${item.key}`, item] as const))), [query.data])

  const pending = useMemo(() => {
    const changes: ParameterChangeRequest[] = []
    let invalid = false
    for (const [key, raw] of Object.entries(draft)) {
      const [scope, name, side] = key.split('|')
      const item = items.get(`${scope}|${name}`)
      if (!item) continue
      const { value, error } = parse(item, raw)
      if (error || value === null) { invalid = true; continue }
      const current = side ? item.values?.[side as Side]?.value : item.value?.value
      if (value === current) continue
      changes.push({ scope: item.scope, key: item.key, ...(side ? { side: side as Side } : {}), value })
    }
    return { changes, invalid }
  }, [draft, items])

  const onChange = (key: string, value: string | boolean | undefined) => {
    setMessage(null)
    setReview(null)
    setDraft((current) => {
      const next = { ...current }
      if (value === undefined) delete next[key]
      else next[key] = value
      return next
    })
  }

  const currentReview = review && review.result.baseVersion === query.data?.version ? review : null
  const reviewOrSave = async () => {
    const version = query.data?.version
    if (saving || !canEdit || version == null || pending.invalid || !pending.changes.length) return
    setSaving(true)
    setMessage(null)
    try {
      if (!currentReview) {
        const result = await motorApi.previewParameters(pending.changes, version)
        setReview({ result, request: pending.changes })
        return
      }
      const note = `Ручная настройка: ${currentReview.request.length} параметр(ов)`
      const result = await motorApi.updateParameters(currentReview.request, note, currentReview.result.baseVersion)
      queryClient.setQueryData(['motor', 'parameters'], result)
      void queryClient.invalidateQueries({ queryKey: ['motor', 'calibrations'] })
      setDraft({})
      setReview(null)
      setMessage({ ok: true, text: `Сохранено: профиль v${result.version ?? '—'}` })
    } catch (error) {
      setReview(null)
      if (error instanceof ApiError && error.status === 409) await query.refetch()
      setMessage({ ok: false, text: error instanceof ApiError || error instanceof Error ? error.message : 'Ошибка сохранения' })
    } finally {
      setSaving(false)
    }
  }

  const reset = async (scope: ResetScope) => {
    const option = RESETS.find((item) => item.scope === scope)
    if (!option || !window.confirm(`${option.label}?\n${option.warning}\nПрежние версии профиля останутся в истории.`)) return
    setSaving(true)
    try {
      const result = await motorApi.reset(scope)
      queryClient.setQueryData(['motor', 'parameters'], result)
      void queryClient.invalidateQueries({ queryKey: ['motor', 'calibrations'] })
      setDraft({})
      setReview(null)
      setMessage({ ok: true, text: `Сброшено: профиль v${result.version ?? '—'}` })
    } catch (error) {
      setMessage({ ok: false, text: error instanceof ApiError || error instanceof Error ? error.message : 'Ошибка сброса' })
    } finally {
      setSaving(false)
    }
  }

  if (query.isError) return <p className="text-sm text-[#ff8f84]">Параметры недоступны: {(query.error as Error).message}</p>
  if (!query.data) return <p className="text-sm text-white/40">Загрузка…</p>

  return (
    <div className="space-y-6">
      {query.data.audit && <section className="cal-surface cal-audit" aria-label="Проверка параметров">
        <h2>Проверка параметров профиля</h2>
        <p>Проверено параметров · {query.data.audit.definitions}. Значений с учётом обеих сторон · {query.data.audit.values}.
          {' '}Без значения · {query.data.audit.unset} (ожидают измерения или используют настройку контроллера).</p>
        {query.data.audit.issues.length ? <details open><summary>Замечания · {query.data.audit.issues.length}</summary>
          <ul>{query.data.audit.issues.map((issue, i) => <li key={i}><strong>{issue.label}{issue.side ? ` · ${issue.side === 'left' ? 'левая' : 'правая'}` : ''}.</strong> {issue.detail}</li>)}</ul>
        </details> : <p data-tone="good">Форматы, диапазоны и взаимные ограничения согласованы.</p>}
        {!!query.data.audit.pending?.length && <details><summary>Какие значения ещё нужно измерить</summary>
          <ul>{query.data.audit.pending.map(row => <li key={row.key}><button type="button" className="cal-link"
            onClick={() => openCalibration(row.procedure)}>{row.procedure} · {row.label}</button>{row.values === 2 ? ' · обе стороны' : ''}</li>)}</ul>
        </details>}
      </section>}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-white/8 bg-white/4 px-5 py-3 text-sm">
        <span className="text-white/60">
          Активный профиль <span className="font-semibold text-white">v{query.data.version ?? '—'}</span>
          {query.data.runtimeVersion !== query.data.version ? <span className="text-[#f2cf87]"> · в работе v{query.data.runtimeVersion ?? '—'}</span> : null}
        </span>
        <span className="text-white/45">
          {calibrating ? 'Идёт калибровка — изменение недоступно' : serviceMode ? 'Сервисный режим: значения можно менять' : 'Для изменения включите сервисный режим'}
        </span>
        <span className="flex flex-wrap gap-2" role="group" aria-label="Сброс">
          {RESETS.map((item) => (
            <Button key={item.scope} variant="ghost" onClick={() => void reset(item.scope)} disabled={saving || !canEdit} title={item.warning}>
              {item.label}
            </Button>
          ))}
        </span>
      </div>

      <div className="space-y-3 rounded-[20px] border border-white/8 bg-white/4 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Поиск: трение, S3, support…"
            aria-label="Поиск параметра"
            className="min-w-56 flex-1 rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-sm text-white outline-none focus:border-[#d6b05f]"
          />
          <div className="flex gap-1" role="group" aria-label="Фильтр по происхождению">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={filter === item.id}
                onClick={() => setFilter(item.id)}
                className={cn('rounded-xl px-3 py-1.5 text-xs transition', filter === item.id ? 'bg-[#b5852f]/30 text-[#f4dfb4]' : 'text-white/50 hover:bg-white/6')}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-white/40">Значения тренажёра:</span>
          {(['measured', 'manual', 'derived', 'default'] as const).map((kind) => (
            <span key={kind} className={cn('rounded-full px-2 py-0.5', PROVENANCE_CLASS[kind])}>{PROVENANCE_LABEL[kind]} · {summary[kind]}</span>
          ))}
          <span className="ml-auto flex flex-wrap gap-1">
            {groups.filter(group => group.items.length).map((group) => (
              <a key={group.id} href={`#params-${group.id}`} className="rounded-lg px-2 py-0.5 text-white/45 hover:bg-white/6 hover:text-white">{group.title} ({group.items.length})</a>
            ))}
          </span>
        </div>
      </div>

      {groups.every((group) => !group.items.length) ? <p className="text-sm text-white/45">Ничего не найдено.</p> : null}

      <fieldset disabled={saving} className="min-w-0 space-y-6">{groups.filter((group) => group.items.length).map((group) => (
        <section key={group.id} id={`params-${group.id}`} className="scroll-mt-4 rounded-[24px] border border-white/8 bg-white/4 p-5" aria-label={group.title}>
          <h3 className="text-lg font-semibold text-[#f4dfb4]">{group.title}</h3>
          <p className="mt-1 text-sm text-white/50">{group.description}</p>
          <ul className="mt-3">
            {group.items.map((item) => <ParamRow key={`${item.scope}|${item.key}`} item={item} draft={draft} canEdit={canEdit} onChange={onChange} onOpen={openCalibration} />)}
          </ul>
        </section>
      ))}</fieldset>

      {pending.changes.length || pending.invalid || message ? (
        <div className="cal-review-dock">
          {currentReview && <ParameterReview review={currentReview.result} />}
          <div className="cal-review-actions"><span role={message && !message.ok ? 'alert' : 'status'} className={cn('flex-1 text-sm', message ? (message.ok ? 'text-[#79de83]' : 'text-[#ff8f84]') : 'text-white/70')}>
            {message?.text ?? (saving ? 'Идёт запрос…' : pending.invalid ? 'Есть недопустимые значения' : review && !currentReview
              ? 'Активная версия изменилась. Проверьте правки повторно.' : currentReview ? 'Правки проверены. Можно применить их к тренажёру.' : `Правок в черновике · ${pending.changes.length}`)}
          </span>
          {Object.keys(draft).length ? <Button variant="ghost" onClick={() => { setDraft({}); setReview(null); setMessage(null) }} disabled={saving}>Отменить правки</Button> : null}
          {pending.changes.length ? <Button onClick={() => void reviewOrSave()} disabled={saving || pending.invalid || !canEdit || query.data.version == null}>{currentReview ? 'Сохранить и применить' : 'Проверить изменения'}</Button> : null}</div>
        </div>
      ) : null}
    </div>
  )
})
