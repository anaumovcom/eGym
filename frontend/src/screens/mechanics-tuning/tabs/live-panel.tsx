import { Pause, Play, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import type { TelemetryBatch } from '@/features/hardware/model/tuning-types'
import type { HardwareControlState } from '@/features/hardware/model/types'
import { buildWebSocketUrl } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'
import { DEFAULT_CHANNELS, TelemetryChart } from '../lib/telemetry-chart'

const WINDOWS = [5, 10, 20, 60] as const

export function useTelemetryDebugStream(enabled: boolean) {
  const ingestBatch = useTuningStore((state) => state.ingestBatch)
  const setError = useTuningStore((state) => state.setError)
  useEffect(() => {
    if (!enabled) return
    let socket: WebSocket | null = null
    let timer: number | null = null
    let disposed = false
    const connect = () => {
      if (disposed) return
      socket = new WebSocket(buildWebSocketUrl('/api/hardware/telemetry-debug'))
      socket.addEventListener('message', (event) => {
        try {
          ingestBatch(JSON.parse(event.data) as TelemetryBatch)
        } catch {
          setError('Не удалось разобрать пакет телеметрии.')
        }
      })
      socket.addEventListener('close', () => {
        if (!disposed) timer = window.setTimeout(connect, 1500)
      })
      socket.addEventListener('error', () => socket?.close())
    }
    connect()
    return () => {
      disposed = true
      if (timer !== null) window.clearTimeout(timer)
      socket?.close()
    }
  }, [enabled, ingestBatch, setError])
}

export function LivePanel({ control }: { control: HardwareControlState | null }) {
  const fields = useTuningStore((state) => state.liveFields)
  const samples = useTuningStore((state) => state.liveSamples)
  const events = useTuningStore((state) => state.events)
  const paused = useTuningStore((state) => state.livePaused)
  const setPaused = useTuningStore((state) => state.setLivePaused)
  const clearLive = useTuningStore((state) => state.clearLive)
  const [enabled, setEnabled] = useState<Set<string>>(() => new Set(['posL', 'posR', 'userForce', 'loadEffective']))
  const [windowSeconds, setWindowSeconds] = useState<(typeof WINDOWS)[number]>(10)

  const toggle = (field: string) =>
    setEnabled((previous) => {
      const next = new Set(previous)
      if (next.has(field)) next.delete(field)
      else next.add(field)
      return next
    })

  const recentEvents = useMemo(() => [...events].slice(-14).reverse(), [events])
  const components = control?.components ?? {}

  return (
    <div className="space-y-4">
      <div className="glass-panel flex flex-wrap items-center gap-2 rounded-2xl p-3">
        <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={paused ? <Play size={14} /> : <Pause size={14} />} onClick={() => setPaused(!paused)}>
          {paused ? 'Продолжить' : 'Пауза'}
        </Button>
        <Button variant="ghost" className="px-3 py-1.5 text-xs" iconLeft={<Trash2 size={14} />} onClick={clearLive}>
          Очистить
        </Button>
        <span className="ml-2 text-xs text-white/40">Окно:</span>
        {WINDOWS.map((value) => (
          <button key={value} type="button" onClick={() => setWindowSeconds(value)} className={cn('rounded-lg px-2 py-1 text-xs', windowSeconds === value ? 'bg-[#b5852f]/30 text-[#f4dfb4]' : 'text-white/40 hover:text-white')}>
            {value} с
          </button>
        ))}
        <span className="ml-auto text-xs text-white/40">
          выборок: {samples.length} · такт {control?.tickLatencyMs ?? '—'} мс · пропущено {control?.missedTicks ?? 0}
        </span>
      </div>

      <TelemetryChart fields={fields} samples={samples} events={events} channels={DEFAULT_CHANNELS} enabled={enabled} windowSeconds={windowSeconds} height={360} />

      <div className="flex flex-wrap gap-1">
        {DEFAULT_CHANNELS.map((channel) => (
          <button
            key={channel.field}
            type="button"
            onClick={() => toggle(channel.field)}
            className={cn('flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] transition', enabled.has(channel.field) ? 'border-white/20 bg-white/10 text-white' : 'border-transparent text-white/35 hover:text-white')}
          >
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: channel.color, opacity: enabled.has(channel.field) ? 1 : 0.4 }} />
            {channel.label}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-2 text-sm font-semibold text-[#f2cf87]">Контур управления</h3>
          {control ? (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <Row label="Режим" value={`${control.mode} · ${control.label}`} />
              <Row label="Позиция" value={`${control.positionMm.toFixed(1)} мм`} />
              <Row label="Скорость" value={`${control.velocityMmPerSec.toFixed(0)} мм/с`} />
              <Row label="Усилие пользователя" value={`${control.userForceKg.toFixed(1)} кг (Л ${control.userForceLeftKg.toFixed(1)} / П ${control.userForceRightKg.toFixed(1)})`} />
              <Row label="Нагрузка" value={`${control.loadEffectiveKg.toFixed(1)} / ${control.loadTargetKg.toFixed(1)} кг`} />
              <Row label="Рассинхрон" value={`${control.syncDeltaMm.toFixed(2)} мм · ${control.syncStatus}`} tone={control.syncStatus === 'critical' ? 'bad' : control.syncStatus === 'warning' ? 'warn' : undefined} />
              <Row label="Асимметрия" value={`${control.asymmetryPercent.toFixed(0)} %`} />
              <Row label="Повторы" value={`${control.repetitionCount} (+${control.partialReps} частичных) · ${control.tempoLabel}`} />
              <Row label="Фазы" value={`↑ ${control.concentricS.toFixed(2)} с · ↓ ${control.eccentricS.toFixed(2)} с`} />
              <Row label="Heartbeat / связь / питание" value={`${flag(control.heartbeatOk)} ${flag(control.commOk)} ${flag(control.powerOk)}`} />
              <Row label="Homed / позиция известна" value={`${flag(control.homed)} ${flag(control.positionKnown)}`} />
              <Row label="Тормоза" value={Object.entries(control.brakes).map(([side, engaged]) => `${side}: ${engaged ? 'зажат' : 'снят'}`).join(' · ')} />
              <Row label="Страховка / отказ / отпущен" value={`${flag(control.spotterActive, 'on')} ${flag(control.failureDetected, 'on')} ${flag(control.released, 'on')}`} />
              <Row label="Временных параметров" value={String(control.temporaryParameters)} />
            </dl>
          ) : (
            <p className="text-xs text-white/40">Нет данных.</p>
          )}
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-2 text-sm font-semibold text-[#f2cf87]">Слагаемые момента, кг</h3>
          {Object.keys(components).length === 0 ? (
            <p className="text-xs text-white/40">Регулятор не формирует момент в текущем режиме.</p>
          ) : (
            <ul className="space-y-1 text-xs">
              {Object.entries(components).map(([key, value]) => (
                <li key={key} className="flex items-center gap-2">
                  <span className="w-28 text-white/50">{componentLabel(key)}</span>
                  <div className="relative h-2 flex-1 rounded bg-white/5">
                    <div className={cn('absolute top-0 h-2 rounded', value >= 0 ? 'left-1/2 bg-[#9be29b]' : 'right-1/2 bg-[#ff9f6e]')} style={{ width: `${Math.min(50, Math.abs(value) / 60 * 50)}%` }} />
                  </div>
                  <span className="w-14 text-right font-mono text-white/80">{value.toFixed(1)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-2 text-sm font-semibold text-[#f2cf87]">События</h3>
          <ul className="max-h-64 space-y-1 overflow-auto text-xs">
            {recentEvents.map((event) => (
              <li key={`${event.time}-${event.kind}-${event.message}`} className="flex gap-2">
                <span className="w-14 shrink-0 font-mono text-white/40">{event.time.toFixed(1)}</span>
                <span className="w-16 shrink-0 text-white/50">{event.kind}</span>
                <span className="text-white/80">{event.message}</span>
              </li>
            ))}
            {recentEvents.length === 0 && <li className="text-white/40">Событий пока нет.</li>}
          </ul>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, tone }: { label: string; value: string; tone?: 'bad' | 'warn' }) {
  return (
    <>
      <dt className="text-white/45">{label}</dt>
      <dd className={cn('font-mono text-white/85', tone === 'bad' && 'text-[#ff8f84]', tone === 'warn' && 'text-[#ffd166]')}>{value}</dd>
    </>
  )
}

function flag(value: boolean, mode: 'ok' | 'on' = 'ok') {
  if (mode === 'on') return value ? '●' : '○'
  return value ? '✓' : '✗'
}

function componentLabel(key: string) {
  return (
    {
      gravity: 'Вес грифа',
      friction: 'Трение',
      inertia: 'Инерция',
      load: 'Нагрузка',
      sync: 'Синхронизация',
      spotter: 'Страховка',
      descentBrake: 'Тормоз спуска',
      bumper: 'Буфер границ',
      damping: 'Демпфирование',
      pretension: 'Натяг, %',
      hold: 'Удержание',
    } as Record<string, string>
  )[key] ?? key
}
