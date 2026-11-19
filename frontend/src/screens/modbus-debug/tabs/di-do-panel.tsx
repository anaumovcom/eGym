import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { DI_BIT_LABELS, DO_BIT_LABELS } from '@/features/modbus/model/parameter-catalog'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

export function DiDoPanel() {
  const { paramStates, connectionStatus, readRegister, writeRegister } = useModbusStore()
  const [busy, setBusy] = useState(false)

  const di = paramStates.get(0x1D2)
  const outputs = paramStates.get(0x1D3)
  const diWord = di?.readStatus === 'ok' ? di.driverValue : null
  const doWord = outputs?.readStatus === 'ok' ? outputs.driverValue : null
  const isConnected = connectionStatus?.connected ?? false
  const simulatedInputs = connectionStatus?.simulationMode ?? false

  const handleRefresh = async () => {
    setBusy(true)
    try {
      await readRegister(0x1D2, 2)
    } finally {
      setBusy(false)
    }
  }

  const toggleDiBit = async (bit: number) => {
    if (!simulatedInputs || diWord == null) return
    const next = (diWord ^ (1 << bit)) & 0xFF
    await writeRegister(0x201, next)
    await readRegister(0x1D2, 2)
  }

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Цифровые входы DI · PA_1D2</h3>
          <Button
            variant="secondary"
            className="text-xs"
            iconLeft={busy ? <RefreshCw size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            onClick={handleRefresh}
            disabled={busy || !isConnected}
          >
            Обновить
          </Button>
        </div>
        <p className="text-xs text-white/40">
          Состояние входов · <span className="font-mono text-white/60">{diWord == null ? '—' : '0b' + diWord.toString(2).padStart(8, '0')}</span>
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {Object.entries(DI_BIT_LABELS).map(([bitStr, info]) => {
            const bit = Number(bitStr)
            const active = diWord != null && !!(diWord & (1 << bit))
            return (
              <div
                key={bit}
                className={cn(
                  'flex items-center justify-between rounded-xl p-3 transition',
                  active ? 'bg-[#123553] border border-[#2b7ab9]' : 'bg-white/4',
                )}
              >
                <div className="flex items-center gap-3">
                  <BitIndicator active={active} />
                  <div>
                    <div className="text-sm font-mono font-semibold text-white/90">{simulatedInputs ? info.name : `DI${bit}`}</div>
                    {simulatedInputs && <div className="text-xs text-white/40">{info.description}</div>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-white/30">bit {bit}</span>
                  <button
                    className={cn(
                      'rounded-lg px-2.5 py-1 text-xs font-semibold transition',
                      active ? 'bg-[#ff8f84]/20 text-[#ff8f84] hover:bg-[#ff8f84]/30' : 'bg-[#79de83]/10 text-[#79de83] hover:bg-[#79de83]/20',
                    )}
                    onClick={() => toggleDiBit(bit)}
                    disabled={!isConnected || !simulatedInputs || diWord == null}
                  >
                    {diWord == null ? '—' : simulatedInputs ? (active ? 'OFF' : 'ON') : (active ? 'ON' : 'OFF')}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <h3 className="font-semibold">Цифровые выходы DO · PA_1D3</h3>
        <p className="text-xs text-white/40">
          Состояние выходов · <span className="font-mono text-white/60">{doWord == null ? '—' : '0x' + doWord.toString(16).toUpperCase()}</span>
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {Object.entries(DO_BIT_LABELS).filter(([bit]) => simulatedInputs || Number(bit) < 4).map(([bitStr, info]) => {
            const bit = Number(bitStr)
            const active = doWord != null && !!(doWord & (1 << bit))
            return (
              <div
                key={bit}
                className={cn(
                  'flex items-center gap-3 rounded-xl p-3',
                  active ? 'bg-[#0d2d0f] border border-[#79de83]/20' : 'bg-white/4',
                )}
              >
                <BitIndicator active={active} color="green" />
                <div className="flex-1">
                  <div className="text-sm font-mono font-semibold text-white/90">{simulatedInputs ? info.name : `DO${bit}`}</div>
                  {simulatedInputs && <div className="text-xs text-white/40">{info.description}</div>}
                </div>
                <span className="text-xs text-white/30">bit {bit}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function BitIndicator({ active, color = 'amber' }: { active: boolean; color?: 'amber' | 'green' }) {
  const onColor = color === 'green' ? 'bg-[#79de83] shadow-[0_0_6px_#79de83]' : 'bg-[#70c9ff] shadow-[0_0_6px_#70c9ff]'
  return (
    <span className={cn(
      'h-3 w-3 rounded-full shrink-0 transition',
      active ? onColor : 'bg-white/15',
    )} />
  )
}
