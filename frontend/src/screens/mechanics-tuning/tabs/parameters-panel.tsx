import {
  AlertTriangle,
  Check,
  CircleGauge,
  Clock3,
  ListFilter,
  RotateCcw,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  ToggleLeft,
  Undo2,
  Zap,
  type LucideIcon,
} from 'lucide-react'
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
  const customizedCount = schema.parameters.filter((spec) => tuning.values[spec.key] !== spec.default).length
  const restartPending = schema.parameters.some((spec) => spec.requiresRestart && spec.key in pending)

  return (
    <div className="space-y-4">
      <div className="glass-panel flex flex-wrap items-center gap-3 rounded-2xl p-4">
        <label className="relative min-w-[220px] flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/30" aria-hidden="true" />
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Поиск параметра…"
            aria-label="Поиск параметра"
            className="w-full rounded-xl border border-white/10 bg-white/5 py-2 pl-9 pr-3 text-sm text-white outline-none focus:border-[#d6b05f]/60"
          />
        </label>
        <div className="flex flex-wrap gap-2" aria-label="Сводка настроек">
          <SummaryBadge icon={Settings2} label="Настроено" value={customizedCount} tone="neutral" />
          <SummaryBadge icon={Clock3} label="Изменено" value={pendingCount} tone="pending" />
          <SummaryBadge icon={Zap} label="Временно" value={temporaryCount} tone="temporary" />
        </div>
        <Button variant="secondary" className="text-xs" iconLeft={<Zap size={14} />} disabled={!serviceMode || busy || pendingCount === 0 || restartPending} onClick={() => void apply('temporary', selectedUserId)}>
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
          {schema.groups.map((item) => {
            const GroupIcon = getGroupIcon(item.id)

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setGroup(item.id)}
                title={item.description}
                className={cn(
                  'flex items-center gap-2 rounded-xl px-3 py-1.5 text-xs font-medium transition',
                  group === item.id ? 'border border-[#b5852f]/50 bg-[#b5852f]/30 text-[#f4dfb4]' : 'text-white/40 hover:bg-white/6 hover:text-white',
                )}
              >
                <GroupIcon size={14} aria-hidden="true" />
                {item.label}
              </button>
            )
          })}
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
  const ParameterIcon = spec.type === 'boolean' ? ToggleLeft : spec.type === 'enum' ? ListFilter : SlidersHorizontal

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
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/5 text-[#d6b05f]">
              <ParameterIcon size={14} aria-hidden="true" />
            </span>
            {spec.label}
            {spec.safetyCritical && <AlertTriangle size={12} className="text-[#ff9f6e]" aria-label="Параметр безопасности" />}
          </div>
          <div className="ml-9 font-mono text-[10px] text-white/30">{spec.key}</div>
        </div>
        <div className="flex max-w-[45%] flex-wrap justify-end gap-1">
          {hasPending ? <StatusBadge label="Не применено" tone="pending" /> : temporary ? <StatusBadge label="Временно" tone="temporary" /> : isDefault ? <StatusBadge label="По умолчанию" tone="default" /> : <StatusBadge label="Настроено" tone="custom" />}
          {spec.safetyCritical ? <StatusBadge label="Безопасность" tone="safety" /> : null}
          {spec.requiresRestart ? <StatusBadge label="После перезапуска" tone="pending" /> : null}
        </div>
      </div>
      <p className="text-xs text-white/50">{spec.description}</p>
      <ParameterInput spec={spec} value={current} disabled={disabled} onChange={onChange} />
      <div className="flex items-center justify-between text-[10px] text-white/40">
        <span>
          сейчас: <span className="font-mono text-white/70">{String(value)}{spec.unit ? ` ${spec.unit}` : ''}</span>
          <span className="ml-2 text-white/30">по умолч.: {String(spec.default)}{spec.unit ? ` ${spec.unit}` : ''}</span>
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
        className={cn('ml-auto flex h-9 min-h-0 w-28 items-center rounded-xl border border-white/10 px-1.5 transition disabled:opacity-50', checked ? 'justify-end bg-[#b5852f]/35' : 'justify-start bg-white/5')}
      >
        <span className={cn('flex h-6 min-w-6 items-center justify-center rounded-lg px-1.5 text-[10px] font-semibold shadow transition', checked ? 'bg-[#d6b05f] text-[#171006]' : 'bg-white/20 text-white/55')}>
          {checked ? 'ВКЛ' : 'ВЫКЛ'}
        </span>
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
  const defaultPercent = min !== undefined && max !== undefined && max > min
    ? toPercent(Number(spec.default), min, max)
    : 0
  const defaultMarkerOffsetRem = 0.375 * (1 - 2 * defaultPercent / 100)

  return (
    <div className="flex items-center gap-3">
      {min !== undefined && max !== undefined && (
        <div className="min-w-0 flex-1 rounded-xl border border-white/6 bg-black/15 px-3 py-2">
          <div className="relative flex items-center">
            <input
              type="range"
              aria-label={`${spec.label} (слайдер)`}
              min={min}
              max={max}
              step={step}
              value={Number.isFinite(numeric) ? numeric : min}
              disabled={disabled}
              onChange={(event) => onChange(clamp(Number(event.target.value)))}
              className="relative z-10 w-full accent-[#d6b05f]"
            />
            <span
              className="pointer-events-none absolute top-1/2 z-20 h-3 w-px -translate-y-1/2 bg-[#7fc8ff]"
              style={{ left: `calc(${defaultPercent}% + ${defaultMarkerOffsetRem}rem)` }}
              title={`По умолчанию: ${spec.default}`}
            />
          </div>
          <div className="flex justify-between font-mono text-[9px] text-white/30">
            <span>{min}{spec.unit ? ` ${spec.unit}` : ''}</span>
            <span className="text-[#7fc8ff]/70">◆ default</span>
            <span>{max}{spec.unit ? ` ${spec.unit}` : ''}</span>
          </div>
        </div>
      )}
      <div className="flex shrink-0 items-center gap-2">
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
    </div>
  )
}

function SummaryBadge({ icon: Icon, label, value, tone }: { icon: LucideIcon; label: string; value: number; tone: 'neutral' | 'pending' | 'temporary' }) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[10px]',
      tone === 'neutral' && 'border-white/8 bg-white/4 text-white/45',
      tone === 'pending' && 'border-[#f2cf87]/20 bg-[#f2cf87]/8 text-[#f2cf87]',
      tone === 'temporary' && 'border-[#7fc8ff]/20 bg-[#7fc8ff]/8 text-[#7fc8ff]',
    )}>
      <Icon size={12} aria-hidden="true" />
      {label} <strong className="font-mono text-xs">{value}</strong>
    </span>
  )
}

function StatusBadge({ label, tone }: { label: string; tone: 'pending' | 'temporary' | 'default' | 'custom' | 'safety' }) {
  const Icon = tone === 'pending' ? Clock3 : tone === 'temporary' ? Zap : tone === 'safety' ? ShieldCheck : Check

  return (
    <span className={cn(
      'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[9px] font-medium',
      tone === 'pending' && 'border-[#f2cf87]/25 bg-[#f2cf87]/8 text-[#f2cf87]',
      tone === 'temporary' && 'border-[#7fc8ff]/25 bg-[#7fc8ff]/8 text-[#7fc8ff]',
      tone === 'default' && 'border-white/8 bg-white/4 text-white/40',
      tone === 'custom' && 'border-[#d6b05f]/25 bg-[#d6b05f]/8 text-[#f2cf87]',
      tone === 'safety' && 'border-[#ff9f6e]/25 bg-[#ff9f6e]/8 text-[#ff9f6e]',
    )}>
      <Icon size={9} aria-hidden="true" />
      {label}
    </span>
  )
}

function getGroupIcon(group: string): LucideIcon {
  if (group.includes('safety') || group.includes('limit')) return ShieldCheck
  if (group.includes('load') || group.includes('torque') || group.includes('compensation')) return CircleGauge
  if (group.includes('detection') || group.includes('sync')) return AlertTriangle
  return Settings2
}

function toPercent(value: number, min: number, max: number) {
  return Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100))
}
