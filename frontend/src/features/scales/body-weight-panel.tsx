import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import { useRef, useState, type ReactNode } from 'react'
import { ChevronDown, Scale, Settings2, Trash2 } from 'lucide-react'
import { bodyMassIndex } from '@/features/body/body-metrics'
import { BodyTrendChart } from '@/features/body/body-trend-chart'
import { Button } from '@/shared/ui/button'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { useAppStore } from '@/stores/app-store'
import { invalidateScaleOwner, scaleKeys, scalesApi, type ScaleMeasurement, type ScalePeriod, type ScaleSettings } from './api'
import '@/features/body/body.css'

const formatWeight = (weight: number) => weight.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
const formatDate = (timestamp: string) => new Date(timestamp).toLocaleString('ru-RU', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
const formatDay = (timestamp: string) => new Date(timestamp).toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' })
const formatTime = (timestamp: string) => new Date(timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
const pauseLabels: Record<string, string> = { setup: 'настройка', exercise: 'упражнение', rest: 'отдых' }
const visibleHistory = 6

/** `children` render between the weight overview and the weigh-in log (e.g. body measurements). */
export function BodyWeightPanel({ userId, userName, heightCm, children }: { userId: string; userName: string; heightCm?: number | null; children?: ReactNode }) {
  const client = useQueryClient()
  const [days, setDays] = useState<ScalePeriod>(30)
  const [deleting, setDeleting] = useState<ScaleMeasurement | null>(null)
  const [showAll, setShowAll] = useState(false)
  const deleteTrigger = useRef<HTMLButtonElement | null>(null)
  const activeId = useAppStore(state => state.selectedUserId)
  const activeName = activeId === userId ? userName : activeId === 'elena' ? 'Елена' : activeId === 'alexey' ? 'Алексей' : activeId === 'guest' ? 'Гость' : activeId
  const statusQuery = useQuery({ queryKey: scaleKeys.status, queryFn: scalesApi.status })
  const history = useQuery({ queryKey: [...scaleKeys.history(userId), days], queryFn: () => scalesApi.history(userId, days), refetchInterval: 30000 })
  const latest = useQuery({ queryKey: scaleKeys.latest(userId), queryFn: () => scalesApi.latest(userId), refetchInterval: 30000 })
  const status = statusQuery.data

  const mutation = useMutation({
    mutationFn: (action: boolean | ScaleSettings) => typeof action === 'boolean' ? scalesApi.scan(action) : scalesApi.settings(action),
    onSuccess: () => client.invalidateQueries({ queryKey: scaleKeys.status }),
  })
  const deletion = useMutation({
    mutationFn: (item: ScaleMeasurement) => scalesApi.deleteMeasurement(item.id, item.userId),
    onSuccess: async (_, item) => {
      setDeleting(null)
      await Promise.all([invalidateScaleOwner(client, item.userId), client.invalidateQueries({ queryKey: scaleKeys.status })])
    },
  })
  const measurements = (history.data?.measurements ?? []).filter(item => item.userId === userId).sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp) || b.id - a.id)
  const chronological = [...measurements].reverse()
  const delta = chronological.length > 1 ? chronological[chronological.length - 1].weightKg - chronological[0].weightKg : null
  const weights = measurements.map(item => item.weightKg)
  const last: ScaleMeasurement | null = latest.data?.userId === userId ? latest.data : null
  const bmi = bodyMassIndex(last?.weightKg, heightCm)
  const bind = (deviceId: string) => mutation.mutate({ enabled: true, deviceId })
  const statusText = statusQuery.isPending ? 'Загрузка статуса весов…' : statusQuery.isError ? 'Статус весов недоступен.' : !status?.enabled ? 'Поиск весов выключен' : status.paused ? `Поиск на паузе${status.pauseReason && pauseLabels[status.pauseReason] ? ` · ${pauseLabels[status.pauseReason]}` : ''}` : !status.bluetoothAvailable ? 'Bluetooth недоступен' : status.measuring ? 'Идёт измерение — стойте неподвижно' : status.scanning ? 'Поиск весов' : 'Ожидание весов'
  const live = Boolean(status?.measuring && !status.paused)
  const shown = showAll ? measurements : measurements.slice(0, visibleHistory)

  return <section aria-label="Вес тела" className="bw">
    <div className="bw-top">
      <article className="bw-hero">
        <header><h2><Scale aria-hidden="true" />Вес тела</h2><span role="status" className="bw-status" data-live={live || undefined}>{statusText}</span></header>
        <div aria-live="polite" className="bw-latest">{latest.isPending ? <p>Загрузка последнего измерения…</p> : latest.isError ? <div role="alert">Не удалось загрузить последнее измерение. <Button variant="secondary" onClick={() => void latest.refetch()}>Повторить измерение</Button></div> : last ? <><p className="bw-weight">{formatWeight(last.weightKg)} <span>кг</span></p><p className="bw-when">Последнее измерение: <time dateTime={last.timestamp}>{formatDate(last.timestamp)}</time></p></> : <><p className="bw-weight bw-weight-empty">— <span>кг</span></p><p>Сохранённых измерений пока нет.</p><p className="bw-when">Выберите весы в настройках и встаньте на них. Стабильный результат появится автоматически.</p></>}</div>
        <dl className="bw-stats">
          <div><dt>Изменение за {days} дней</dt><dd><p data-tone={delta === null ? undefined : delta < 0 ? 'down' : delta > 0 ? 'up' : undefined}>{history.isError || history.isPending || delta === null ? '—' : `${delta > 0 ? '+' : ''}${formatWeight(Math.round(delta * 100) / 100)} кг`}</p></dd></div>
          <div><dt>Измерений за период</dt><dd><p>{history.isError || history.isPending ? '—' : measurements.length}</p></dd></div>
          <div><dt>Диапазон за период</dt><dd><p>{weights.length > 1 ? `${formatWeight(Math.min(...weights))}–${formatWeight(Math.max(...weights))} кг` : '—'}</p></dd></div>
          <div><dt>Индекс массы тела</dt><dd><p>{bmi ? <>{formatWeight(bmi.value)} <small data-tone={bmi.tone}>{bmi.category}</small></> : '—'}</p></dd></div>
        </dl>
      </article>
      <article className="bw-chart-card">
        <header><h3>Динамика веса тела</h3><div className="bw-periods" role="group" aria-label="Период истории веса">{([7, 30, 90] as const).map(period => <button type="button" key={period} aria-pressed={days === period} onClick={() => setDays(period)}>{period} дней</button>)}</div></header>
        {history.isPending ? <p role="status" className="bw-chart-state">Загрузка истории веса…</p> : history.isError ? <div role="alert" className="bw-chart-state">Не удалось загрузить историю веса. <Button variant="secondary" onClick={() => void history.refetch()}>Повторить историю</Button></div> : measurements.length ? <BodyTrendChart points={chronological.map(item => ({ id: item.id, date: item.timestamp, value: item.weightKg }))} unit="кг" label="Динамика веса тела" height={280} /> : <p className="bw-chart-state">За выбранный период измерений нет.</p>}
      </article>
    </div>
    {children}

    <article className="bw-history">
      <header><h3>История взвешиваний</h3>{measurements.length ? <span>{measurements.length} за {days} дней</span> : null}</header>
      {measurements.length ? <ul>{shown.map((item, index) => {
        const previous = measurements[index + 1]
        const change = previous ? item.weightKg - previous.weightKg : null
        return <li key={item.id}>
          <div className="bw-history-date"><time dateTime={item.timestamp}>{formatDay(item.timestamp)}</time><small>{formatTime(item.timestamp)}{item.impedanceOhm !== null ? <> · <span>Импеданс: {item.impedanceOhm} Ом</span></> : null}</small></div>
          <strong>{formatWeight(item.weightKg)} кг</strong>
          <span className="bw-history-change" data-tone={change === null || Math.abs(change) < 0.05 ? 'flat' : change < 0 ? 'down' : 'up'}>{change === null ? 'первое' : Math.abs(change) < 0.05 ? 'без изменений' : `${change > 0 ? '+' : '−'}${formatWeight(Math.abs(Math.round(change * 100) / 100))}`}</span>
          <Button variant="ghost" className="min-h-12 min-w-12" aria-label={`Удалить ${formatWeight(item.weightKg)} кг · ${formatDate(item.timestamp)}`} onClick={event => { deleteTrigger.current = event.currentTarget; deletion.reset(); setDeleting(item) }}><Trash2 aria-hidden="true" className="h-5 w-5" /></Button>
        </li>
      })}</ul> : <p className="bw-muted">{history.isError ? 'История недоступна.' : history.isPending ? 'Загрузка…' : 'Здесь будут ваши стабильные результаты.'}</p>}
      {measurements.length > visibleHistory ? <button type="button" className="bw-more" aria-expanded={showAll} onClick={() => setShowAll(value => !value)}>{showAll ? 'Свернуть' : `Показать все ${measurements.length}`}<ChevronDown aria-hidden="true" /></button> : null}
    </article>

    <details className="bw-settings"><summary><Settings2 aria-hidden="true" />Настройки весов<span>{status?.deviceId ? `весы ${status.deviceId}` : 'весы не выбраны'}</span></summary>
      <div className="grid gap-5">
        <p className="text-sm text-white/65">Весы общие для всех профилей. {activeName ? <>Новые стабильные результаты сохраняются в активный профиль «{activeName}».</> : 'Выберите активный профиль для сохранения результатов.'}</p>
        <p className="text-sm text-white/60">Весы передают данные при взвешивании; поиск не означает постоянное подключение.</p>
        <p className="text-sm text-white/60">Поиск включён по умолчанию и работает автоматически вне тренировки. Во время настройки упражнения, выполнения, отдыха и калибровки поиск на паузе, затем возобновляется автоматически. Ручное выключение сохраняется.</p>
        {status?.lastSeen ? <p>Последний сигнал: {formatDate(status.lastSeen)}</p> : null}
        {statusQuery.isError ? <Button variant="secondary" onClick={() => void statusQuery.refetch()}>Повторить статус</Button> : null}
        {status?.warning ? <p role="alert">{status.warning}</p> : null}
        {status?.error ? <p role="alert">{status.error}</p> : null}
        {mutation.isError ? <p role="alert">Не удалось изменить настройки весов: {mutation.error.message}</p> : null}
        <div className="flex flex-wrap gap-3">
          <Button className="min-h-14" disabled={mutation.isPending} onClick={() => mutation.mutate(true)}>Включить поиск</Button>
          <Button className="min-h-14" variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate(false)}>Выключить поиск</Button>
        </div>
        {status?.deviceId ? <p>Выбранные весы: {status.deviceId}</p> : null}
        <div className="grid gap-3">
          <h3 className="text-lg font-semibold">Весы поблизости</h3>
          {!status?.devices.length ? <p>Устройства не обнаружены. Включите поиск и встаньте на весы.</p> : status.devices.map((device) => <div key={device.deviceId} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 p-4">
            <div><strong>{device.name || 'Xiaomi'}</strong><p>{device.deviceId}{device.rssi !== null ? ` · ${device.rssi} dBm` : ''}</p><p>Сигнал: {formatDate(device.lastSeen)}</p></div>
            <Button className="min-h-14" variant="secondary" disabled={mutation.isPending || status.deviceId === device.deviceId} onClick={() => bind(device.deviceId)}>{status.deviceId === device.deviceId ? 'Выбраны' : 'Выбрать весы'}</Button>
          </div>)}
        </div>
        {status?.deviceId ? <Button className="min-h-14" variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate({ enabled: status.enabled, deviceId: null })}>Сбросить выбор весов</Button> : null}
      </div>
    </details>
    <Dialog.Root open={deleting !== null} onOpenChange={open => { if (!open && !deletion.isPending) setDeleting(null) }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" /><SafetyDialogContent onCloseAutoFocus={event => { if (deleteTrigger.current?.isConnected) { event.preventDefault(); deleteTrigger.current.focus() } }} className="w-[min(32rem,calc(100vw-24px))] rounded-[28px] border border-[#d6b05f]/25 bg-[#111419] p-6 text-white"><Dialog.Title className="text-2xl font-semibold">Удалить взвешивание?</Dialog.Title><Dialog.Description className="mt-3 leading-7 text-white/65">{deleting ? `${formatWeight(deleting.weightKg)} кг · ${formatDate(deleting.timestamp)} · №${deleting.id}. ` : ''}Измерение будет удалено из истории и прогресса. Это действие нельзя отменить.</Dialog.Description>{deletion.isError ? <p role="alert" className="mt-4 text-red-300">Не удалось удалить измерение: {deletion.error.message}</p> : null}<div className="mt-6 flex flex-wrap gap-3"><Button autoFocus variant="secondary" disabled={deletion.isPending} onClick={() => setDeleting(null)}>Отмена</Button><Button variant="danger" disabled={deletion.isPending} onClick={() => { if (deleting) deletion.mutate(deleting) }}>{deletion.isPending ? 'Удаление…' : 'Удалить измерение'}</Button></div></SafetyDialogContent></Dialog.Portal></Dialog.Root>
  </section>
}
