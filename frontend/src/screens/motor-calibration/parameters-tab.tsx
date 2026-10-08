import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  PROVENANCE_LABEL,
  formatValue,
  kgfHint,
  motorApi,
  type ParamItem,
  type ParameterChangeRequest,
  type Side,
  type ValueInfo,
} from '@/features/motor/api/motor-api'
import { ApiError } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'

type Draft = Record<string, string | boolean>

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

function ValueCell({ item, info, side, draft, canEdit, onChange }: {
  item: ParamItem
  info: ValueInfo
  side: Side | null
  draft: Draft
  canEdit: boolean
  onChange: (key: string, value: string | boolean | undefined) => void
}) {
  const key = draftKey(item, side)
  const raw = draft[key]
  const edit = canEdit && editableValue(item, info)
  const parsed = raw === undefined ? null : parse(item, raw)
  const changed = parsed !== null && parsed.error === null && parsed.value !== info.value
  const hint = kgfHint(info.value, item.unit)
  const label = side === 'left' ? 'Левая' : side === 'right' ? 'Правая' : null

  return (
    <div className={cn('rounded-[16px] border px-3 py-2', changed ? 'border-[#b5852f]/60 bg-[#b5852f]/10' : 'border-white/8 bg-black/15')}>
      {label ? <p className="text-[11px] uppercase tracking-[0.12em] text-white/35">{label}</p> : null}
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
      ) : (
        <p className="py-1 text-sm font-medium text-white">{formatValue(info.value, item.kind, item.unit)}</p>
      )}
      {parsed?.error ? <p className="text-xs text-[#ff8f84]">{parsed.error}</p> : null}
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-white/40">
        <span className={cn('rounded-full px-2 py-0.5', PROVENANCE_CLASS[info.provenance])}>{PROVENANCE_LABEL[info.provenance]}</span>
        {info.ci95 ? <span>± {formatValue(info.ci95, item.kind, item.unit)}</span> : null}
        {hint ? <span>{hint}</span> : null}
        {item.kind === 'weight' && (info.points ?? 1) > 1 ? <span>{info.points} точек по высоте</span> : null}
        {changed ? <span className="text-[#f2cf87]">было {formatValue(info.value, item.kind, item.unit)}</span> : null}
      </div>
    </div>
  )
}

function ParamRow({ item, draft, canEdit, onChange }: { item: ParamItem; draft: Draft; canEdit: boolean; onChange: (key: string, value: string | boolean | undefined) => void }) {
  return (
    <li className="grid gap-3 border-t border-white/6 py-4 first:border-t-0 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-white">{item.label}</span>
          {!item.editable ? <span className="rounded-full bg-white/6 px-2 py-0.5 text-[11px] text-white/40">только калибровкой</span> : null}
          {item.producedBy ? <span className="rounded-full bg-[#b5852f]/15 px-2 py-0.5 text-[11px] text-[#f2cf87]">измеряет {item.producedBy}</span> : null}
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
              <ValueCell key={side} item={item} info={item.values![side]} side={side} draft={draft} canEdit={canEdit} onChange={onChange} />
            ))
          : item.value
            ? <ValueCell item={item} info={item.value} side={null} draft={draft} canEdit={canEdit} onChange={onChange} />
            : null}
      </div>
    </li>
  )
}

export function ParametersTab({ serviceMode, calibrating }: { serviceMode: boolean; calibrating: boolean }) {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['motor', 'parameters'], queryFn: motorApi.parameters })
  const [draft, setDraft] = useState<Draft>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const canEdit = serviceMode && !calibrating

  const items = useMemo(() => new Map<string, ParamItem>((query.data?.groups ?? []).flatMap((group) => group.items.map((item) => [`${item.scope}|${item.key}`, item] as const))), [query.data])

  const pending = useMemo(() => {
    const changes: ParameterChangeRequest[] = []
    let invalid = false
    let restart = false
    for (const [key, raw] of Object.entries(draft)) {
      const [scope, name, side] = key.split('|')
      const item = items.get(`${scope}|${name}`)
      if (!item) continue
      const { value, error } = parse(item, raw)
      if (error || value === null) { invalid = true; continue }
      const current = side ? item.values?.[side as Side]?.value : item.value?.value
      if (value === current) continue
      restart ||= item.restart
      changes.push({ scope: item.scope, key: item.key, ...(side ? { side: side as Side } : {}), value })
    }
    return { changes, invalid, restart }
  }, [draft, items])

  const onChange = (key: string, value: string | boolean | undefined) => {
    setMessage(null)
    setDraft((current) => {
      const next = { ...current }
      if (value === undefined) delete next[key]
      else next[key] = value
      return next
    })
  }

  const save = async () => {
    const note = `Ручная настройка: ${pending.changes.length} параметр(ов)`
    const warning = pending.restart ? '\nЧасть параметров вступит в силу только после перезапуска бэкенда.' : ''
    if (!window.confirm(`Сохранить ${pending.changes.length} изменений как новую версию профиля и применить?${warning}`)) return
    setSaving(true)
    try {
      const result = await motorApi.updateParameters(pending.changes, note)
      queryClient.setQueryData(['motor', 'parameters'], result)
      void queryClient.invalidateQueries({ queryKey: ['motor', 'calibrations'] })
      setDraft({})
      setMessage({ ok: true, text: `Сохранено: профиль v${result.version ?? '—'}` })
    } catch (error) {
      setMessage({ ok: false, text: error instanceof ApiError || error instanceof Error ? error.message : 'Ошибка сохранения' })
    } finally {
      setSaving(false)
    }
  }

  if (query.isError) return <p className="text-sm text-[#ff8f84]">Параметры недоступны: {(query.error as Error).message}</p>
  if (!query.data) return <p className="text-sm text-white/40">Загрузка…</p>

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-white/8 bg-white/4 px-5 py-3 text-sm">
        <span className="text-white/60">
          Активный профиль <span className="font-semibold text-white">v{query.data.version ?? '—'}</span>
          {query.data.runtimeVersion !== query.data.version ? <span className="text-[#f2cf87]"> · в работе v{query.data.runtimeVersion ?? '—'}</span> : null}
        </span>
        <span className="text-white/45">
          {calibrating ? 'Идёт калибровка — изменение недоступно' : serviceMode ? 'Сервисный режим: значения можно менять' : 'Для изменения включите сервисный режим'}
        </span>
      </div>

      {query.data.groups.map((group) => (
        <section key={group.id} className="rounded-[24px] border border-white/8 bg-white/4 p-5" aria-label={group.title}>
          <h3 className="text-lg font-semibold text-[#f4dfb4]">{group.title}</h3>
          <p className="mt-1 text-sm text-white/50">{group.description}</p>
          <ul className="mt-3">
            {group.items.map((item) => <ParamRow key={`${item.scope}|${item.key}`} item={item} draft={draft} canEdit={canEdit} onChange={onChange} />)}
          </ul>
        </section>
      ))}

      {pending.changes.length || pending.invalid || message ? (
        <div className="sticky bottom-4 z-10 flex flex-wrap items-center gap-3 rounded-[20px] border border-[#b5852f]/50 bg-[#1b1408]/95 px-5 py-3 shadow-lg backdrop-blur">
          <span role={message && !message.ok ? 'alert' : undefined} className={cn('flex-1 text-sm', message ? (message.ok ? 'text-[#79de83]' : 'text-[#ff8f84]') : 'text-white/70')}>
            {message?.text ?? (pending.invalid ? 'Есть недопустимые значения' : `Изменено параметров: ${pending.changes.length}`)}
          </span>
          {Object.keys(draft).length ? <Button variant="ghost" onClick={() => { setDraft({}); setMessage(null) }} disabled={saving}>Сбросить</Button> : null}
          {pending.changes.length ? <Button onClick={() => void save()} disabled={saving || pending.invalid || !canEdit}>Сохранить</Button> : null}
        </div>
      ) : null}
    </div>
  )
}
