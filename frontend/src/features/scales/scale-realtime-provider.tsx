import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownRight, ArrowUpRight, CheckCircle2, Minus, Scale } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { playExerciseEventSound } from '@/features/runtime/lib/exercise-event-sounds'
import { buildWebSocketUrl } from '@/shared/api/client'
import { ToastNotification } from '@/shared/ui/overlays/surface-components'
import { useAppStore } from '@/stores/app-store'
import { invalidateScaleOwner, scaleKeys, scalesApi, type ScaleMeasurement, type ScaleStatus } from './api'

const MAX_SEEN_MEASUREMENTS = 256

/** One app-wide observer. Never reset the watermark on reconnect, deletion or profile change. */
export function ScaleRealtimeProvider() {
  const client = useQueryClient()
  const selectedUserId = useAppStore(state => state.selectedUserId)
  const startedAt = useRef(Date.now())
  const latestTimestamp = useRef(-Infinity)
  const seenMeasurements = useRef(new Set<string>())
  const previousUser = useRef(selectedUserId)
  const [notice, setNotice] = useState<ScaleMeasurement | null>(null)
  const status = useQuery({ queryKey: scaleKeys.status, queryFn: scalesApi.status, refetchInterval: 5000 })

  const observe = useCallback((measurement: ScaleMeasurement | null) => {
    if (!measurement || !Number.isSafeInteger(measurement.id) || measurement.id <= 0) return
    const timestamp = Date.parse(measurement.timestamp)
    if (!Number.isFinite(timestamp) || timestamp < latestTimestamp.current) return
    // SQLite can reuse a deleted row's ID. Impedance updates retain its identity.
    const key = `${measurement.id}:${timestamp}`
    if (seenMeasurements.current.has(key)) return
    seenMeasurements.current.add(key)
    if (seenMeasurements.current.size > MAX_SEEN_MEASUREMENTS) {
      const oldest = seenMeasurements.current.values().next().value
      if (oldest !== undefined) seenMeasurements.current.delete(oldest)
    }
    latestTimestamp.current = timestamp
    void invalidateScaleOwner(client, measurement.userId)
    if (measurement.stable && timestamp >= startedAt.current && measurement.userId === useAppStore.getState().selectedUserId) {
      setNotice(measurement)
      playExerciseEventSound('success')
    }
  }, [client])

  useEffect(() => { observe(status.data?.lastMeasurement ?? null) }, [observe, status.data])
  useEffect(() => {
    if (previousUser.current !== selectedUserId) setNotice(null)
    previousUser.current = selectedUserId
  }, [selectedUserId])
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), 6000)
    return () => clearTimeout(timer)
  }, [notice])

  useEffect(() => {
    let disposed = false
    let socket: WebSocket | undefined
    let reconnect: ReturnType<typeof setTimeout> | undefined
    function connect() {
      if (disposed) return
      try {
        const current = new WebSocket(buildWebSocketUrl('/api/scales/realtime'))
        socket = current
        current.onmessage = event => {
          if (disposed) return
          try {
            const next: ScaleStatus = JSON.parse(event.data)
            if (typeof next.enabled !== 'boolean' || !Array.isArray(next.devices)) return
            observe(next.lastMeasurement)
            client.setQueryData(scaleKeys.status, next)
          } catch { /* REST polling remains available for malformed frames. */ }
        }
        current.onclose = () => { if (!disposed) { clearTimeout(reconnect); reconnect = setTimeout(connect, 2000) } }
        current.onerror = () => current.close()
      } catch { reconnect = setTimeout(connect, 2000) }
    }
    connect()
    return () => {
      disposed = true
      clearTimeout(reconnect)
      if (socket) {
        socket.onmessage = null
        socket.onclose = null
        socket.onerror = null
        socket.close()
      }
    }
  }, [client, observe])

  return notice && notice.userId === selectedUserId ? <WeightMeasurementNotice key={`${notice.id}:${notice.timestamp}`} measurement={notice} onDismiss={() => setNotice(null)} /> : null
}

function WeightMeasurementNotice({ measurement, onDismiss }: { measurement: ScaleMeasurement; onDismiss: () => void }) {
  const history = useQuery({
    queryKey: ['scales', 'notice-history', measurement.userId, measurement.id, measurement.timestamp],
    queryFn: () => scalesApi.history(measurement.userId, 3650),
    gcTime: 60000,
  })
  const previous = history.data?.measurements
    .filter(item => item.userId === measurement.userId && item.id !== measurement.id && (
      Date.parse(item.timestamp) < Date.parse(measurement.timestamp)
      || (item.timestamp === measurement.timestamp && item.id < measurement.id)
    ))
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp) || b.id - a.id)[0]
  const delta = previous ? Math.round((measurement.weightKg - previous.weightKg) * 100) / 100 : null
  const Icon = delta === null ? Scale : delta === 0 ? Minus : delta > 0 ? ArrowUpRight : ArrowDownRight
  // Direction is not a health judgement: neither gaining nor losing is inherently bad.
  const tone = delta === null || delta === 0 ? 'border-white/10 bg-white/5 text-white/65'
    : delta > 0 ? 'border-amber-300/20 bg-amber-300/10 text-amber-200'
      : 'border-sky-300/20 bg-sky-300/10 text-sky-200'
  const format = (value: number) => value.toLocaleString('ru-RU', { maximumFractionDigits: 2 })

  return <ToastNotification title="Вес сохранён" onDismiss={onDismiss} description={<div className="space-y-3">
    <div className="flex items-center gap-2"><CheckCircle2 aria-hidden="true" className="h-5 w-5 text-emerald-300" /><strong className="text-2xl font-semibold text-white">{format(measurement.weightKg)} <span className="text-sm font-normal text-white/55">кг</span></strong></div>
    <div className={`flex items-start gap-2 rounded-xl border px-3 py-2 ${tone}`}>
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <div>{history.isPending ? 'Сравниваем с прошлым замером…' : history.isError ? 'Не удалось загрузить прошлый замер' : delta === null ? 'Первое взвешивание' : delta === 0 ? 'Без изменений с прошлого замера' : <><strong>{delta > 0 ? '+' : '−'}{format(Math.abs(delta))} кг</strong> с прошлого замера</>}
        {previous ? <div className="mt-1 text-xs opacity-75">Было {format(previous.weightKg)} кг · {new Date(previous.timestamp).toLocaleDateString('ru-RU')}</div> : null}
      </div>
    </div>
    <time className="block text-xs text-white/40" dateTime={measurement.timestamp}>{new Date(measurement.timestamp).toLocaleString('ru-RU')}</time>
  </div>} />
}