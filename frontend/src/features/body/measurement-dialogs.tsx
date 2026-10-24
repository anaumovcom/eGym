import * as Dialog from '@radix-ui/react-dialog'
import { useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useId, useState } from 'react'
import { Button } from '@/shared/ui/button'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { bodyApi, invalidateBody } from './body-api'
import { bodyMetrics, formatBody, metricSummary, type BodyMeasurement, type BodyMetricKey } from './body-metrics'

type Draft = Record<BodyMetricKey, string>
const emptyDraft: Draft = { weightKg: '', bodyFatPercent: '', waistCm: '', chestCm: '', hipsCm: '' }
// Plausible ranges catch typos such as 830 instead of 83.0 before they distort every chart.
const limits: Record<BodyMetricKey, [number, number]> = { weightKg: [20, 300], bodyFatPercent: [2, 70], waistCm: [40, 200], chestCm: [50, 200], hipsCm: [50, 200] }
const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })

function today() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
function parse(value: string) { const parsed = Number(value.replace(',', '.')); return value.trim() && Number.isFinite(parsed) ? parsed : null }

export function MeasurementDialog({ open, onOpenChange, userId, measurements }: { open: boolean; onOpenChange: (open: boolean) => void; userId: string; measurements: BodyMeasurement[] }) {
  const client = useQueryClient()
  const formId = useId()
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [date, setDate] = useState(today)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const invalid = bodyMetrics.filter((metric) => { const value = parse(draft[metric.key]); return value !== null && (value < limits[metric.key][0] || value > limits[metric.key][1]) })
  const filled = bodyMetrics.some((metric) => parse(draft[metric.key]) !== null)

  function close(next: boolean) {
    if (pending) return
    if (!next) { setDraft(emptyDraft); setDate(today()); setError(null) }
    onOpenChange(next)
  }

  async function save() {
    if (pending || invalid.length || !filled) return
    setPending(true); setError(null)
    try {
      const measuredAt = date === today() ? new Date().toISOString() : new Date(`${date}T09:00:00`).toISOString()
      await bodyApi.create(userId, measuredAt, Object.fromEntries(bodyMetrics.map((metric) => [metric.key, parse(draft[metric.key])])))
      await invalidateBody(client, userId)
      setPending(false)
      close(false)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Не удалось сохранить измерение.')
      setPending(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={close}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
        <SafetyDialogContent className="body-dialog">
          <Dialog.Title className="font-display text-3xl font-bold">Новое измерение</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-white/60">Заполните то, что измерили. Пустые поля не сохраняются, серым показано прошлое значение.</Dialog.Description>
          <div className="body-form">
            {bodyMetrics.map((metric) => {
              const last = metricSummary(measurements, metric.key).last
              const wrong = invalid.includes(metric)
              return (
                <div key={metric.key} className="body-field" data-invalid={wrong || undefined}>
                  <label htmlFor={`${formId}-${metric.key}`}>{metric.field}</label>
                  <input id={`${formId}-${metric.key}`} type="text" inputMode="decimal" autoComplete="off" value={draft[metric.key]} placeholder={last ? formatBody(last.value) : '—'} aria-invalid={wrong || undefined} aria-describedby={`${formId}-${metric.key}-hint`} onChange={(event) => setDraft((current) => ({ ...current, [metric.key]: event.target.value }))} />
                  <small id={`${formId}-${metric.key}-hint`}>{wrong ? `Допустимо ${limits[metric.key][0]}–${limits[metric.key][1]} ${metric.unit}` : last ? `было ${formatBody(last.value)} ${metric.unit}` : 'ещё не измеряли'}</small>
                </div>
              )
            })}
            <div className="body-field">
              <label htmlFor={`${formId}-date`}>Дата</label>
              <input id={`${formId}-date`} type="date" value={date} max={today()} onChange={(event) => setDate(event.target.value || today())} />
              <small>{date === today() ? 'сегодня' : 'задним числом'}</small>
            </div>
          </div>
          {error ? <p role="alert" className="mt-4 text-[#ffb4a7]">{error}</p> : null}
          <div className="body-dialog-actions">
            <Dialog.Close asChild><Button variant="secondary" disabled={pending}>Отмена</Button></Dialog.Close>
            <Button disabled={pending || !filled || invalid.length > 0} onClick={() => void save()}>{pending ? 'Сохранение…' : 'Сохранить измерение'}</Button>
          </div>
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function DeleteMeasurementDialog({ measurement, onClose, userId }: { measurement: BodyMeasurement | null; onClose: () => void; userId: string }) {
  const client = useQueryClient()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const values = measurement ? bodyMetrics.filter((metric) => measurement[metric.key] != null && Number(measurement[metric.key]) > 0).map((metric) => `${metric.label} ${formatBody(Number(measurement[metric.key]))} ${metric.unit}`) : []

  async function remove() {
    if (!measurement || pending) return
    setPending(true); setError(null)
    try {
      await bodyApi.remove(userId, measurement.id)
      await invalidateBody(client, userId)
      setPending(false)
      onClose()
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : 'Не удалось удалить измерение.')
      setPending(false)
    }
  }

  return (
    <Dialog.Root open={measurement !== null} onOpenChange={(open) => { if (!open && !pending) { setError(null); onClose() } }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
        <SafetyDialogContent className="body-dialog body-dialog-narrow">
          <Dialog.Title className="font-display text-2xl font-bold">Удалить измерение?</Dialog.Title>
          <Dialog.Description className="mt-3 leading-7 text-white/65">{measurement ? `${dateFormat.format(new Date(measurement.measuredAt))}: ${values.join(', ') || 'без значений'}. ` : ''}Запись исчезнет из профиля, графиков и прогресса.</Dialog.Description>
          {error ? <p role="alert" className="mt-4 text-[#ffb4a7]">{error}</p> : null}
          <div className="body-dialog-actions">
            <Dialog.Close asChild><Button variant="secondary" disabled={pending} autoFocus>Отмена</Button></Dialog.Close>
            <Button variant="danger" iconLeft={<Trash2 aria-hidden="true" />} disabled={pending} onClick={() => void remove()}>{pending ? 'Удаление…' : 'Удалить'}</Button>
          </div>
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
