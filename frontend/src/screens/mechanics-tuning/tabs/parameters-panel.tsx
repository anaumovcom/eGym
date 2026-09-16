import { AlertTriangle, RotateCcw, Save, Undo2, Zap } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import type { TuningParameterSpec } from '@/features/hardware/model/tuning-types'
import { useAppStore } from '@/stores/app-store'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

export function ParametersPanel({ serviceMode }: { serviceMode: boolean }) {
  const schema = useTuningStore((state) => state.schema)
  const tuning = useTuningStore((state) => state.tuning)
  const pending = useTuningStore((state) => state.pending)
  const busy = useTuningStore((state) => state.busy)
  const setPending = useTuningStore((state) => state.setPending)
  const clearPending = useTuningStore((state) => state.clearPending)
  const apply = useTuningStore((state) => state.apply)
  const revert = useTuningStore((state) => state.revert)
  const reset = useTuningStore((state) => state.reset)
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const [group, setGroup] = useState<string>('compensation')
  const [filter, setFilter] = useState('')
  const [confirmReset, setConfirmReset] = useState(false)

  const parameters = useMemo(() => {
    if (!schema) return []
    const query = filter.trim().toLowerCase()
    return schema.parameters.filter((item) => (query ? item.label.toLowerCase().includes(query) || item.key.toLowerCase().includes(query) : item.group === group))
  }, [schema, group, filter])

  if (!schema || !tuning) {
    return <div className="glass-panel rounded-2xl p-6 text-sm text-white/50">Загрузка реестра параметров…</div>
  }

  const pendingCount = Object.keys(pending).length
  const temporaryCount = Object.keys(tuning.temporary).length

  return (
    <div className="space-y-4">
      <div className="glass-panel flex flex-wrap items-center gap-3 rounded-2xl p-4">
        <input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Поиск параметра…"
          aria-label="Поиск параметра"
          className="min-w-[220px] flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-[#d6b05f]/60"
        />
        <span className="text-xs text-white/40">
          Изменено: <span className="font-semibold text-[#f2cf87]">{pendingCount}</span> · временных активно: <span className="font-semibold text-[#7fc8ff]">{temporaryCount}</span>
        </span>
        <Button variant="secondary" className="text-xs" iconLeft={<Zap size={14} />} disabled={!serviceMode || busy || pendingCount === 0} onClick={() => void apply('temporary', selectedUserId)}>
          Применить временно
        </Button>
        <Button className="text-xs" iconLeft={<Save size={14} />} disabled={!serviceMode || busy || pendingCount === 0} onClick={() => void apply('persist', selectedUserId)}>
          Сохранить
        </Button>
        <Button variant="ghost" className="text-xs" iconLeft={<Undo2 size={14} />} disabled={pendingCount === 0 && temporaryCount === 0} onClick={() => { clearPending(); void revert() }}>
          Откатить временные
        </Button>
        {confirmReset ? (
          <span className="flex items-center gap-2 text-xs text-[#ff8f84]">
            Сбросить все параметры к заводским?
            <Button variant="danger" className="px-3 py-1.5 text-xs" disabled={!serviceMode} onClick={() => { setConfirmReset(false); void reset(selectedUserId) }}>Да</Button>
            <Button variant="ghost" className="px-3 py-1.5 text-xs" onClick={() => setConfirmReset(false)}>Нет</Button>
          </span>
        ) : (
          <Button variant="ghost" className="text-xs" iconLeft={<RotateCcw size={14} />} disabled={!serviceMode} onClick={() => setConfirmReset(true)}>
            Заводские
          </Button>
        )}
      </div>

      {!filter && (
        <div className="flex flex-wrap gap-1">
          {schema.groups.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setGroup(item.id)}
              title={item.description}
              className={cn(
                'rounded-xl px-3 py-1.5 text-xs font-medium transition',
                group === item.id ? 'border border-[#b5852f]/50 bg-[#b5852f]/30 text-[#f4dfb4]' : 'text-white/40 hover:bg-white/6 hover:text-white',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {parameters.map((spec) => (
          <ParameterCard
            key={spec.key}
            spec={spec}
            value={tuning.values[spec.key]}
            pendingValue={pending[spec.key]}
            temporary={spec.key in tuning.temporary}
            disabled={!serviceMode}
            onChange={(value) => setPending(spec.key, value)}
            onClear={() => clearPending(spec.key)}
          />
        ))}
      </div>
    </div>
  )
}

type CardProps = {
  spec: TuningParameterSpec
  value: unknown
  pendingValue: unknown
  temporary: boolean
  disabled: boolean
  onChange: (value: unknown) => void
  onClear: () => void
}

function ParameterCard({ spec, value, pendingValue, temporary, disabled, onChange, onClear }: CardProps) {
  const hasPending = pendingValue !== undefined
  const current = hasPending ? pendingValue : value
  const isDefault = value === spec.default

  return (
    <div
      className={cn(
        'glass-panel flex flex-col gap-2 rounded-2xl p-4',
        hasPending && 'border border-[#f2cf87]/50',
        temporary && !hasPending && 'border border-[#7fc8ff]/40',
      )}
      data-testid={`param-${spec.key}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            {spec.label}
            {spec.safetyCritical && <AlertTriangle size={12} className="text-[#ff9f6e]" aria-label="Параметр безопасности" />}
          </div>
          <div className="font-mono text-[10px] text-white/30">{spec.key}</div>
        </div>
        <div className="text-right text-[10px] text-white/40">
          <div>по умолч.: {String(spec.default)}{spec.unit ? ` ${spec.unit}` : ''}</div>
          {spec.hardMin !== null && spec.hardMax !== null && <div>жёстко: {spec.hardMin}…{spec.hardMax}</div>}
          {temporary && <div className="text-[#7fc8ff]">временно</div>}
        </div>
      </div>
      <p className="text-xs text-white/50">{spec.description}</p>
      <ParameterInput spec={spec} value={current} disabled={disabled} onChange={onChange} />
      <div className="flex items-center justify-between text-[10px] text-white/40">
        <span>
          сейчас: <span className="font-mono text-white/70">{String(value)}</span>
          {!isDefault && <span className="ml-1 text-[#f2cf87]">≠ default</span>}
        </span>
        {hasPending && (
          <button type="button" onClick={onClear} className="text-[#f2cf87] hover:underline">
            отменить
          </button>
        )}
      </div>
    </div>
  )
}

function ParameterInput({ spec, value, disabled, onChange }: { spec: TuningParameterSpec; value: unknown; disabled: boolean; onChange: (value: unknown) => void }) {
  if (spec.type === 'boolean') {
    const checked = Boolean(value)
    return (
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={spec.label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn('flex h-8 min-h-0 w-16 items-center rounded-full border border-white/10 px-1 transition disabled:opacity-50', checked ? 'bg-[#b5852f]/60 justify-end' : 'bg-white/10 justify-start')}
      >
        <span className="h-6 w-6 rounded-full bg-white shadow" />
      </button>
    )
  }
  if (spec.type === 'enum') {
    return (
      <select
        value={String(value)}
        aria-label={spec.label}
        title={spec.label}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-xl border border-white/10 bg-[#0d0b07] px-3 py-2 text-sm text-white outline-none focus:border-[#d6b05f]/60"
      >
        {spec.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    )
  }
  const numeric = Number(value)
  const step = spec.step ?? (spec.type === 'integer' ? 1 : 0.1)
  const min = spec.min ?? spec.hardMin ?? undefined
  const max = spec.max ?? spec.hardMax ?? undefined
  const clamp = (next: number) => {
    let result = next
    if (min !== undefined) result = Math.max(min, result)
    if (max !== undefined) result = Math.min(max, result)
    return spec.type === 'integer' ? Math.round(result) : Number(result.toFixed(4))
  }
  return (
    <div className="flex items-center gap-2">
      {min !== undefined && max !== undefined && (
        <input
          type="range"
          aria-label={`${spec.label} (слайдер)`}
          min={min}
          max={max}
          step={step}
          value={Number.isFinite(numeric) ? numeric : min}
          disabled={disabled}
          onChange={(event) => onChange(clamp(Number(event.target.value)))}
          className="flex-1 accent-[#d6b05f]"
        />
      )}
      <button type="button" disabled={disabled} aria-label={`${spec.label}: уменьшить`} onClick={() => onChange(clamp(numeric - step))} className="rounded-lg border border-white/10 px-2 py-1 text-xs text-white/70 hover:bg-white/10 disabled:opacity-40">
        −
      </button>
      <input
        type="number"
        aria-label={spec.label}
        value={Number.isFinite(numeric) ? numeric : ''}
        step={step}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(event) => onChange(clamp(Number(event.target.value)))}
        className="w-24 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-right font-mono text-sm text-white outline-none focus:border-[#d6b05f]/60"
      />
      <button type="button" disabled={disabled} aria-label={`${spec.label}: увеличить`} onClick={() => onChange(clamp(numeric + step))} className="rounded-lg border border-white/10 px-2 py-1 text-xs text-white/70 hover:bg-white/10 disabled:opacity-40">
        +
      </button>
      <span className="w-12 text-xs text-white/40">{spec.unit}</span>
    </div>
  )
}
