import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import { useRef, useState } from 'react'
import { Scale, Settings2, Trash2 } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Panel } from '@/shared/ui/stage4/screen-components'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { useAppStore } from '@/stores/app-store'
import { invalidateScaleOwner, scaleKeys, scalesApi, type ScaleMeasurement, type ScalePeriod, type ScaleSettings } from './api'
import { WeightChart } from './weight-chart'

const formatWeight = (weight: number) => weight.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
const formatDate = (timestamp: string) => new Date(timestamp).toLocaleString('ru-RU', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
const pauseLabels: Record<string, string> = { setup: 'настройка', exercise: 'упражнение', rest: 'отдых' }

export function BodyWeightPanel({ userId, userName }: { userId: string; userName: string }) {
  const client = useQueryClient()
  const [days, setDays] = useState<ScalePeriod>(30)
  const [deleting, setDeleting] = useState<ScaleMeasurement | null>(null)
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
  const last: ScaleMeasurement | null = latest.data?.userId === userId ? latest.data : null
  const bind = (deviceId: string) => mutation.mutate({ enabled: true, deviceId })

  return <section aria-label="Вес тела" className="grid gap-4 mb-6 text-white">
    <div className="rounded-[32px] border border-[#d6b05f]/20 bg-[radial-gradient(ellipse_at_top_right,rgba(214,176,95,0.14),transparent_65%)] bg-[#111419] p-6 sm:p-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4"><h2 className="flex items-center gap-3 text-xl font-semibold"><Scale aria-hidden="true" className="text-[#d6b05f]" />Вес тела</h2><span role="status" className={`rounded-full border border-white/10 px-4 py-2 text-sm ${status?.measuring && !status.paused ? 'text-[#f1d391]' : 'text-white/55'}`}>{statusQuery.isPending ? 'Загрузка статуса весов…' : statusQuery.isError ? 'Статус весов недоступен.' : !status?.enabled ? 'Поиск весов выключен' : status.paused ? `Поиск на паузе${status.pauseReason && pauseLabels[status.pauseReason] ? ` · ${pauseLabels[status.pauseReason]}` : ''}` : !status.bluetoothAvailable ? 'Bluetooth недоступен' : status.measuring ? 'Идёт измерение — стойте неподвижно' : status.scanning ? 'Поиск весов' : 'Ожидание весов'}</span></header>
      <div aria-live="polite">{latest.isPending ? <p>Загрузка последнего измерения…</p> : latest.isError ? <div role="alert">Не удалось загрузить последнее измерение. <Button variant="secondary" onClick={() => void latest.refetch()}>Повторить измерение</Button></div> : last ? <><p className="font-display text-6xl font-semibold tracking-tight text-[#f1d391] sm:text-7xl">{formatWeight(last.weightKg)} <span className="text-2xl font-normal text-white/45">кг</span></p><p className="mt-3 text-sm text-white/50">Последнее измерение: <time dateTime={last.timestamp}>{formatDate(last.timestamp)}</time></p></> : <><p className="text-5xl text-[#f1d391]">— кг</p><p className="mt-3">Сохранённых измерений пока нет.</p><p className="mt-2 text-sm text-white/50">Выберите весы в настройках и встаньте на них. Стабильный результат появится автоматически.</p></>}</div>
      <div className="mt-7 grid grid-cols-2 gap-4 border-t border-white/10 pt-5"><div><p className="text-sm text-white/45">Изменение за {days} дней</p><p className="mt-1 text-2xl text-[#f1d391]">{history.isError || history.isPending || delta === null ? '—' : `${delta > 0 ? '+' : ''}${formatWeight(Math.round(delta * 100) / 100)} кг`}</p></div><div><p className="text-sm text-white/45">Измерений за период</p><p className="mt-1 text-2xl">{history.isError || history.isPending ? '—' : measurements.length}</p></div></div>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-semibold">Динамика веса тела</h3><div className="inline-flex rounded-2xl border border-white/10 bg-white/5 p-1" role="group" aria-label="Период истории веса">{([7, 30, 90] as const).map(period => <button type="button" key={period} className={`min-h-12 rounded-xl px-5 text-sm ${days === period ? 'bg-[#d6b05f] font-semibold text-[#15120c]' : 'text-white/60 hover:bg-white/5'}`} aria-pressed={days === period} onClick={() => setDays(period)}>{period} дней</button>)}</div></div>
    {history.isPending ? <p role="status">Загрузка истории веса…</p> : history.isError ? <div role="alert">Не удалось загрузить историю веса. <Button variant="secondary" onClick={() => void history.refetch()}>Повторить историю</Button></div> : measurements.length ? <WeightChart measurements={chronological} /> : <p className="rounded-3xl border border-dashed border-white/10 p-8 text-center text-white/50">За выбранный период измерений нет.</p>}
    <Panel title="История взвешиваний">{measurements.length ? <ul className="divide-y divide-white/10">{measurements.map(item => <li key={item.id} className="flex items-center justify-between gap-3 py-4"><div><strong className="text-xl text-[#f1d391]">{formatWeight(item.weightKg)} кг</strong><time className="mt-1 block text-sm text-white/50" dateTime={item.timestamp}>{formatDate(item.timestamp)}</time>{item.impedanceOhm !== null ? <span className="text-xs text-white/40">Импеданс: {item.impedanceOhm} Ом</span> : null}</div><Button variant="ghost" className="min-h-12 min-w-12" aria-label={`Удалить ${formatWeight(item.weightKg)} кг · ${formatDate(item.timestamp)}`} onClick={event => { deleteTrigger.current = event.currentTarget; deletion.reset(); setDeleting(item) }}><Trash2 aria-hidden="true" className="h-5 w-5" /></Button></li>)}</ul> : <p className="text-sm text-white/50">{history.isError ? 'История недоступна.' : history.isPending ? 'Загрузка…' : 'Здесь будут ваши стабильные результаты.'}</p>}</Panel>
    <details className="rounded-[28px] border border-white/10 bg-[#111419] p-6"><summary className="min-h-12 cursor-pointer text-lg font-semibold"><Settings2 aria-hidden="true" className="mr-3 inline h-5 w-5 text-[#d6b05f]" />Настройки весов</summary>
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