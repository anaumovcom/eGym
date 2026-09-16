import { Hand, RefreshCw, ShieldAlert, Sliders } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

const SCENARIOS = [
  { id: 'none', label: 'Нет (ручное усилие)' },
  { id: 'steady_set', label: 'Ровный подход' },
  { id: 'failure', label: 'Отказ' },
  { id: 'jerk', label: 'Рывок' },
  { id: 'release', label: 'Отпустил гриф' },
  { id: 'tilt', label: 'Перекос' },
  { id: 'hold_still', label: 'Держит неподвижно' },
]

const FAULTS: { id: string; label: string; side?: boolean; value?: boolean }[] = [
  { id: 'power_loss', label: 'Пропадание питания' },
  { id: 'power_restore', label: 'Восстановить питание' },
  { id: 'comm_lost', label: 'Потеря связи', side: true },
  { id: 'encoder_drift', label: 'Дрейф энкодера', side: true, value: true },
  { id: 'overheat', label: 'Перегрев', side: true },
  { id: 'physical_estop', label: 'Физический СТОП' },
  { id: 'physical_estop_release', label: 'Отпустить физический СТОП' },
]

const PHYSICS_LABELS: Record<string, string> = {
  bar_mass_kg: 'Масса грифа (истинная), кг',
  moving_parts_kg: 'Подвижные части, кг',
  friction_kg: 'Трение, кг',
  equivalent_mass_kg: 'Инерция ШВП (привед.), кг',
  backlash_mm: 'Люфт, мм',
  coupling_kg_per_mm: 'Жёсткость грифа, кг/мм',
  coupling_damping: 'Демпфирование связи',
  drive_kp_kg_per_mm: 'Kp привода, кг/мм',
  drive_kd: 'Kd привода',
  drive_kv: 'Kv привода',
}

export function EmulatorPanel() {
  const emulator = useTuningStore((state) => state.emulator)
  const loadEmulator = useTuningStore((state) => state.loadEmulator)
  const control = useTuningStore((state) => state.controlEmulator)
  const [force, setForce] = useState(0)
  const [bias, setBias] = useState(0)
  const [side, setSide] = useState<'left' | 'right'>('right')
  const [strength, setStrength] = useState(60)
  const [period, setPeriod] = useState(3)
  const [physics, setPhysics] = useState<Record<string, number>>({})

  useEffect(() => {
    void loadEmulator()
    const timer = window.setInterval(() => void loadEmulator(), 2000)
    return () => window.clearInterval(timer)
  }, [loadEmulator])

  useEffect(() => {
    if (emulator?.physics && Object.keys(physics).length === 0) setPhysics(emulator.physics)
  }, [emulator, physics])

  if (!emulator) return <div className="glass-panel rounded-2xl p-6 text-sm text-white/50">Загрузка состояния эмулятора…</div>
  if (!emulator.active) return <div className="glass-panel rounded-2xl p-6 text-sm text-white/50">Активен реальный адаптер приводов — эмулятор недоступен.</div>

  const sendForce = (value: number, nextBias = bias) => {
    setForce(value)
    void control({ action: 'user_force', forceKg: value, bias: nextBias })
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#f2cf87]"><Hand size={14} /> Виртуальная рука</h3>
          <p className="mb-3 text-xs text-white/45">Постоянное усилие на грифе: + вверх, − вниз (например, повис на турнике). Смещение распределяет усилие между сторонами.</p>
          <label className="block text-xs text-white/50">
            Усилие: <span className="font-mono text-white">{force.toFixed(0)} кг</span>
            <input type="range" min={-120} max={120} step={1} value={force} aria-label="Усилие виртуальной руки" className="mt-1 w-full accent-[#d6b05f]" onChange={(event) => sendForce(Number(event.target.value))} />
          </label>
          <label className="mt-2 block text-xs text-white/50">
            Смещение Л ← → П: <span className="font-mono text-white">{bias.toFixed(2)}</span>
            <input type="range" min={-1} max={1} step={0.05} value={bias} aria-label="Смещение усилия между сторонами" className="mt-1 w-full accent-[#7fc8ff]" onChange={(event) => { setBias(Number(event.target.value)); sendForce(force, Number(event.target.value)) }} />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            {[0, 5, 20, 40, -20, -70].map((value) => (
              <Button key={value} variant={value === 0 ? 'secondary' : 'ghost'} className="px-3 py-1.5 text-xs" onClick={() => sendForce(value)}>
                {value === 0 ? 'Отпустить' : `${value > 0 ? '+' : ''}${value} кг`}
              </Button>
            ))}
          </div>
          <div className="mt-2 text-[11px] text-white/40">Текущее: {emulator.userForceKg?.toFixed(1)} кг · смещение {emulator.userBias?.toFixed(2)} · сценарий {emulator.scenario?.name} (повторов {emulator.scenario?.repsDone})</div>
        </div>

        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#f2cf87]"><RefreshCw size={14} /> Сценарий виртуального пользователя</h3>
          <div className="mb-3 flex flex-wrap gap-3 text-xs text-white/50">
            <label>Сила, кг <input type="number" aria-label="Сила пользователя" className="ml-1 w-20 rounded-lg border border-white/10 bg-white/5 px-2 py-1 font-mono text-white" value={strength} onChange={(event) => setStrength(Number(event.target.value))} /></label>
            <label>Период, с <input type="number" step={0.5} aria-label="Период повтора" className="ml-1 w-20 rounded-lg border border-white/10 bg-white/5 px-2 py-1 font-mono text-white" value={period} onChange={(event) => setPeriod(Number(event.target.value))} /></label>
          </div>
          <div className="flex flex-wrap gap-2">
            {SCENARIOS.map((item) => (
              <Button key={item.id} variant={emulator.scenario?.name === item.id ? 'primary' : 'secondary'} className="px-3 py-1.5 text-xs" onClick={() => void control({ action: 'scenario', name: item.id, strengthKg: strength, periodS: period, tiltBias: item.id === 'tilt' ? 0.8 : 0 })}>
                {item.label}
              </Button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-white/40">Диапазон сценария берётся из текущей конфигурации подхода (нижняя/верхняя точка), поэтому запускайте после «start_motion» или задайте границы в тренировке.</p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#ff8f84]"><ShieldAlert size={14} /> Сбои</h3>
          <div className="mb-2 flex items-center gap-2 text-xs text-white/50">
            Сторона:
            {(['left', 'right'] as const).map((value) => (
              <button key={value} type="button" onClick={() => setSide(value)} className={cn('rounded-lg px-2 py-1', side === value ? 'bg-[#b5852f]/30 text-[#f4dfb4]' : 'text-white/40 hover:text-white')}>{value}</button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {FAULTS.map((fault) => (
              <Button key={fault.id} variant="danger" className="px-3 py-1.5 text-xs" onClick={() => void control({ action: 'fault', fault: fault.id, side: fault.side ? side : undefined, value: fault.value ? 3 : undefined })}>
                {fault.label}{fault.side ? ` (${side})` : ''}
              </Button>
            ))}
            <Button variant="secondary" className="px-3 py-1.5 text-xs" onClick={() => void control({ action: 'clear_faults' })}>Снять все сбои</Button>
          </div>
          <div className="mt-3 text-[11px] text-white/50">
            Активные: питание {emulator.faults?.powerLoss ? 'потеряно' : 'ок'} · физ. СТОП {emulator.faults?.physicalEstop ? 'нажат' : 'нет'} · связь потеряна: {emulator.faults?.commLost?.join(', ') || '—'} · дрейф: {Object.entries(emulator.faults?.encoderDrift ?? {}).map(([k, v]) => `${k} ${v} мм/с`).join(', ') || '—'} · перегрев: {emulator.faults?.overheat?.join(', ') || '—'}
          </div>
        </div>

        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#f2cf87]"><Sliders size={14} /> Физика эмулятора («истина»)</h3>
          <p className="mb-2 text-[11px] text-white/45">Эти значения — реальность, против которой настраивается контроллер. Меняйте их, чтобы проверить мастера измерения.</p>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(physics).filter(([key]) => key in PHYSICS_LABELS).map(([key, value]) => (
              <label key={key} className="text-[11px] text-white/50">
                {PHYSICS_LABELS[key]}
                <input type="number" step={0.1} aria-label={PHYSICS_LABELS[key]} className="mt-0.5 w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1 font-mono text-xs text-white" value={value} onChange={(event) => setPhysics((prev) => ({ ...prev, [key]: Number(event.target.value) }))} />
              </label>
            ))}
          </div>
          <Button className="mt-3 px-3 py-1.5 text-xs" onClick={() => void control({ action: 'physics', physics })}>Применить физику</Button>
        </div>
      </div>

      <div className="glass-panel rounded-2xl p-4">
        <h3 className="mb-2 text-sm font-semibold text-[#f2cf87]">Журнал эмулятора</h3>
        <ul className="max-h-40 space-y-1 overflow-auto text-xs text-white/70">
          {(emulator.events ?? []).slice().reverse().map((event, index) => (
            <li key={`${event.time}-${index}`}><span className="font-mono text-white/40">{event.time.toFixed(1)}</span> · {event.kind} · {event.message}</li>
          ))}
          {(emulator.events ?? []).length === 0 && <li className="text-white/40">Событий нет.</li>}
        </ul>
      </div>
    </div>
  )
}
