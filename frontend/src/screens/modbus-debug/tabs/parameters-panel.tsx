import { RefreshCw, Save, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { GROUP_LABELS, PARAMETER_CATALOG } from '@/features/modbus/model/parameter-catalog'
import type { ParameterDef, ParameterGroup, ParameterState } from '@/features/modbus/model/types'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

export function ParametersPanel() {
  const {
    paramStates,
    connectionStatus,
    setUiValue,
    readRegister,
    writeRegister,
    writeAllDirty,
    discardUiChanges,
    readBatch,
  } = useModbusStore()

  const [search, setSearch] = useState('')
  const [filterGroup, setFilterGroup] = useState<ParameterGroup | 'ALL'>('ALL')
  const [filterDirty, setFilterDirty] = useState(false)
  const [filterErrors, setFilterErrors] = useState(false)
  const [savingAll, setSavingAll] = useState(false)
  const [readingGroup, setReadingGroup] = useState(false)
  const [readingAll, setReadingAll] = useState(false)
  const [readAllProgress, setReadAllProgress] = useState(0)

  const isConnected = connectionStatus?.connected ?? false

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return PARAMETER_CATALOG.filter((p) => {
      if (filterGroup !== 'ALL' && p.group !== filterGroup) return false
      if (filterDirty) {
        const st = paramStates.get(p.address)
        if (!st?.dirty) return false
      }
      if (filterErrors) {
        const st = paramStates.get(p.address)
        if (st?.readStatus !== 'error' && st?.writeStatus !== 'error') return false
      }
      if (q) {
        return (
          p.name.toLowerCase().includes(q) ||
          p.label.toLowerCase().includes(q) ||
          p.description.toLowerCase().includes(q) ||
          p.addressHex.toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [search, filterGroup, filterDirty, filterErrors, paramStates])

  const dirtyCount = useMemo(() => [...paramStates.values()].filter((s) => s.dirty).length, [paramStates])
  const unsavedCount = useMemo(() => [...paramStates.values()].filter((s) => s.writtenButUnsaved).length, [paramStates])
  const allAddresses = useMemo(() => Array.from(new Set(PARAMETER_CATALOG.map((p) => p.address))), [])

  const handleReadGroup = async () => {
    if (filterGroup === 'ALL') return
    const addresses = PARAMETER_CATALOG.filter((p) => p.group === filterGroup).map((p) => p.address)
    setReadingGroup(true)
    try {
      await readBatch(addresses)
    } finally {
      setReadingGroup(false)
    }
  }

  const handleReadAll = async () => {
    setReadingAll(true)
    setReadAllProgress(0)
    try {
      for (const [index, address] of allAddresses.entries()) {
        setReadAllProgress(index + 1)
        await readRegister(address)
      }
    } finally {
      setReadingAll(false)
    }
  }

  const handleWriteAllDirty = async () => {
    setSavingAll(true)
    try {
      await writeAllDirty()
    } finally {
      setSavingAll(false)
    }
  }

  const groups = useMemo(() => {
    const gset = new Set(PARAMETER_CATALOG.map((p) => p.group))
    return [...gset]
  }, [])

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="glass-panel rounded-2xl p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
            <input
              type="text"
              placeholder="Поиск по параметру, названию, адресу..."
              className="input-field w-full pl-8"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            className="input-field"
            value={filterGroup}
            onChange={(e) => setFilterGroup(e.target.value as ParameterGroup | 'ALL')}
          >
            <option value="ALL">Все группы</option>
            {groups.map((g) => (
              <option key={g} value={g}>{GROUP_LABELS[g] ?? g}</option>
            ))}
          </select>
          <FilterToggle active={filterDirty} onClick={() => setFilterDirty((v) => !v)}>
            Изменённые {dirtyCount > 0 && `(${dirtyCount})`}
          </FilterToggle>
          <FilterToggle active={filterErrors} onClick={() => setFilterErrors((v) => !v)}>
            С ошибками
          </FilterToggle>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            className="text-xs"
            iconLeft={readingAll ? <RefreshCw size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            onClick={handleReadAll}
            disabled={!isConnected || readingGroup || readingAll}
          >
            {readingAll ? `Чтение всех параметров (${readAllProgress}/${allAddresses.length})` : `Читать все параметры (${allAddresses.length})`}
          </Button>
          {filterGroup !== 'ALL' && (
            <Button
              variant="secondary"
              className="text-xs"
              iconLeft={readingGroup ? <RefreshCw size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              onClick={handleReadGroup}
              disabled={!isConnected || readingGroup || readingAll}
            >
              Читать группу: {GROUP_LABELS[filterGroup] ?? filterGroup}
            </Button>
          )}
          {dirtyCount > 0 && (
            <Button
              variant="primary"
              className="text-xs"
              iconLeft={<Save size={13} />}
              onClick={handleWriteAllDirty}
              disabled={!isConnected || savingAll}
            >
              Записать изменённые ({dirtyCount})
            </Button>
          )}
          {dirtyCount > 0 && (
            <Button
              variant="ghost"
              className="text-xs"
              onClick={discardUiChanges}
            >
              Сбросить изменения
            </Button>
          )}
          {unsavedCount > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-[#2d2500] px-3 py-1 text-xs text-[#f2cf87]">
              {unsavedCount} параметров записано, но не сохранено в память
            </span>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="glass-panel rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/8 text-xs text-white/40 uppercase tracking-wide">
                <th className="px-4 py-3 text-left">Параметр</th>
                <th className="px-4 py-3 text-left">Адрес</th>
                <th className="px-4 py-3 text-left">Название / Группа</th>
                <th className="px-4 py-3 text-right">Значение в драйвере</th>
                <th className="px-4 py-3 text-right">Новое значение</th>
                <th className="px-4 py-3 text-center">Статус</th>
                <th className="px-4 py-3 text-center">Действия</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-white/30 text-sm">
                    Нет параметров по фильтру
                  </td>
                </tr>
              )}
              {filtered.map((param) => (
                <ParameterRow
                  key={param.address}
                  param={param}
                  state={paramStates.get(param.address)}
                  isConnected={isConnected}
                  onRead={() => readRegister(param.address)}
                  onWrite={(v) => writeRegister(param.address, v)}
                  onSetUi={(v) => setUiValue(param.address, v)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function FilterToggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      className={cn(
        'rounded-xl px-3 py-2 text-xs font-medium transition',
        active ? 'bg-[#b5852f]/30 text-[#f2cf87]' : 'border border-white/10 bg-white/4 text-white/50 hover:text-white',
      )}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function ParameterRow({
  param, state, isConnected, onRead, onWrite, onSetUi,
}: {
  param: ParameterDef
  state: ParameterState | undefined
  isConnected: boolean
  onRead: () => void
  onWrite: (v: number) => void
  onSetUi: (v: number | null) => void
}) {
  const [localInput, setLocalInput] = useState('')
  const [writing, setWriting] = useState(false)
  const [reading, setReading] = useState(false)

  const driverVal = state?.driverValue
  const displayDriver = driverVal != null
    ? formatValue(driverVal, param)
    : state?.readStatus === 'loading' ? '...' : '—'

  const isDirty = state?.dirty ?? false
  const isUnsaved = state?.writtenButUnsaved ?? false

  const handleRead = async () => {
    setReading(true)
    try {
      await onRead()
    } finally {
      setReading(false)
    }
  }

  const handleWrite = async () => {
    const v = parseValue(localInput)
    if (v === null) return
    setWriting(true)
    try {
      await onWrite(v)
      setLocalInput('')
      onSetUi(null)
    } finally {
      setWriting(false)
    }
  }

  const handleInputChange = (raw: string) => {
    setLocalInput(raw)
    const v = parseValue(raw)
    onSetUi(v)
  }

  return (
    <tr className={cn(
      'border-b border-white/4 hover:bg-white/3 transition',
      isDirty && 'bg-[#2d2500]/40',
      isUnsaved && 'bg-[#0d2d0f]/40',
    )}>
      {/* Parameter name */}
      <td className="px-4 py-3 font-mono text-xs text-[#f2cf87] whitespace-nowrap">
        <div className="flex items-center gap-1">
          {param.name}
          {param.dangerous && <span className="text-[#ff8f84] text-[10px]">⚠</span>}
          {param.requiresReboot && <span className="text-[#f2cf87] text-[10px]" title="Требуется перезапуск">↻</span>}
          {param.readOnly && <span className="text-white/30 text-[10px]">RO</span>}
        </div>
      </td>

      {/* Address */}
      <td className="px-4 py-3 font-mono text-xs text-white/40 whitespace-nowrap">
        {param.addressHex}
        <div className="text-[10px] text-white/20">{param.address}</div>
      </td>

      {/* Label / Group */}
      <td className="px-4 py-3 min-w-[160px]">
        <div className="text-sm text-white/90">{param.label}</div>
        <div className="text-xs text-white/30">{GROUP_LABELS[param.group] ?? param.group}</div>
      </td>

      {/* Driver value */}
      <td className="px-4 py-3 text-right font-mono">
        <div className={cn('text-sm', state?.readStatus === 'error' ? 'text-[#ff8f84]' : 'text-white')}>
          {displayDriver}
        </div>
        {driverVal != null && param.enumMap?.[driverVal] && (
          <div className="text-[11px] text-white/40">{param.enumMap[driverVal]}</div>
        )}
        {driverVal != null && param.unit && (
          <div className="text-[11px] text-white/30">{param.unit}</div>
        )}
        {state?.readStatus === 'error' && (
          <div className="text-[10px] text-[#ff8f84]/70">{state.readError}</div>
        )}
      </td>

      {/* New value input */}
      <td className="px-4 py-3 text-right">
        {!param.readOnly && (
          <div className="flex items-center justify-end gap-1">
            <input
              type="number"
              className="input-field w-24 text-right text-sm"
              placeholder={driverVal != null ? String(driverVal) : '—'}
              value={localInput}
              min={param.min}
              max={param.max}
              onChange={(e) => handleInputChange(e.target.value)}
              disabled={!isConnected}
            />
            {isDirty && (
              <span className="text-[10px] text-[#f2cf87]">*</span>
            )}
          </div>
        )}
      </td>

      {/* Status badges */}
      <td className="px-4 py-3 text-center">
        <div className="flex items-center justify-center gap-1 flex-wrap">
          <StatusDot status={state?.readStatus ?? 'idle'} label="R" />
          {!param.readOnly && <StatusDot status={state?.writeStatus ?? 'idle'} label="W" />}
          {isUnsaved && (
            <span className="rounded px-1 py-0.5 text-[9px] bg-[#0d2d0f] text-[#79de83]">ЗАПИСАН</span>
          )}
        </div>
      </td>

      {/* Actions */}
      <td className="px-4 py-3 text-center">
        <div className="flex items-center justify-center gap-1">
          <ActionBtn
            onClick={handleRead}
            loading={reading}
            disabled={!isConnected}
            title="Читать"
          >
            R
          </ActionBtn>
          {!param.readOnly && (
            <ActionBtn
              onClick={handleWrite}
              loading={writing}
              disabled={!isConnected || localInput === ''}
              title="Записать"
              accent
            >
              W
            </ActionBtn>
          )}
        </div>
      </td>
    </tr>
  )
}

function StatusDot({ status, label }: { status: string; label: string }) {
  const colors: Record<string, string> = {
    idle: 'bg-white/20 text-white/30',
    loading: 'bg-[#f2cf87]/40 text-[#f2cf87] animate-pulse',
    ok: 'bg-[#79de83]/20 text-[#79de83]',
    error: 'bg-[#ff8f84]/20 text-[#ff8f84]',
  }
  return (
    <span className={cn('rounded px-1.5 py-0.5 text-[9px] font-bold', colors[status] ?? colors.idle)}>
      {label}
    </span>
  )
}

function ActionBtn({
  onClick, loading, disabled, title, children, accent,
}: {
  onClick: () => void
  loading?: boolean
  disabled?: boolean
  title?: string
  children: React.ReactNode
  accent?: boolean
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(
        'rounded-lg px-2 py-1 text-xs font-bold transition',
        accent
          ? 'bg-[#b5852f]/30 text-[#f2cf87] hover:bg-[#b5852f]/50 disabled:opacity-30'
          : 'bg-white/8 text-white/50 hover:bg-white/14 hover:text-white disabled:opacity-30',
      )}
    >
      {loading ? '…' : children}
    </button>
  )
}

function formatValue(v: number, param: ParameterDef): string {
  if (param.enumMap?.[v]) return `${v} (${param.enumMap[v]})`
  return String(v)
}

function parseValue(s: string): number | null {
  if (!s.trim()) return null
  const n = s.trim().startsWith('0x') ? parseInt(s, 16) : parseInt(s, 10)
  return isNaN(n) ? null : n
}
