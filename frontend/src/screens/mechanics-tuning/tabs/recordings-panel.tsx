import { Camera, Circle, Eye, GitCompare, Square, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import type { RecordingSummary } from '@/features/hardware/model/tuning-types'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'
import { DEFAULT_CHANNELS, TelemetryChart } from '../lib/telemetry-chart'

export function RecordingsPanel() {
  const recordings = useTuningStore((state) => state.recordings)
  const opened = useTuningStore((state) => state.openedRecording)
  const compare = useTuningStore((state) => state.compareRecording)
  const loadRecordings = useTuningStore((state) => state.loadRecordings)
  const recording = useTuningStore((state) => state.recording)
  const openRecording = useTuningStore((state) => state.openRecording)
  const closeRecording = useTuningStore((state) => state.closeRecording)
  const deleteRecording = useTuningStore((state) => state.deleteRecording)
  const [title, setTitle] = useState('')
  const [comment, setComment] = useState('')
  const [enabled, setEnabled] = useState<Set<string>>(() => new Set(['posL', 'userForce', 'loadEffective']))

  useEffect(() => {
    void loadRecordings()
  }, [loadRecordings])

  const active = recordings?.recording ?? false

  const renderList = (items: RecordingSummary[], emptyLabel: string) => (
    <ul className="space-y-2">
      {items.length === 0 && <li className="text-xs text-white/40">{emptyLabel}</li>}
      {items.map((item) => (
        <li key={item.id} className={cn('flex flex-wrap items-center gap-2 rounded-xl border border-white/8 p-3', opened?.id === item.id && 'border-[#f2cf87]/50', compare?.id === item.id && 'border-[#7fc8ff]/50')}>
          <div className="flex-1">
            <div className="text-sm text-white">{item.title}</div>
            <div className="text-[11px] text-white/40">
              {new Date(item.createdAt).toLocaleString('ru-RU')} · {item.durationS.toFixed(1)} с · {item.sampleCount} выборок{item.comment ? ` · ${item.comment}` : ''}
            </div>
          </div>
          <Button variant="ghost" className="px-2 py-1 text-xs" iconLeft={<Eye size={14} />} onClick={() => void openRecording(item.id, 'main')}>Открыть</Button>
          <Button variant="ghost" className="px-2 py-1 text-xs" iconLeft={<GitCompare size={14} />} onClick={() => void openRecording(item.id, 'compare')}>Сравнить</Button>
          <button type="button" aria-label={`Удалить запись ${item.title}`} onClick={() => void deleteRecording(item.id)} className="text-white/30 hover:text-[#ff8f84]"><Trash2 size={14} /></button>
        </li>
      ))}
    </ul>
  )

  return (
    <div className="space-y-4">
      <div className="glass-panel flex flex-wrap items-center gap-2 rounded-2xl p-4">
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Название записи" aria-label="Название записи" className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-[#d6b05f]/60" />
        <input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Комментарий (что настраивали)" aria-label="Комментарий записи" className="min-w-[220px] flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-[#d6b05f]/60" />
        {active ? (
          <Button variant="danger" className="text-xs" iconLeft={<Square size={14} />} onClick={() => void recording('stop', { title: title || 'Запись', comment })}>
            Остановить запись
          </Button>
        ) : (
          <Button className="text-xs" iconLeft={<Circle size={14} />} onClick={() => void recording('start')}>
            Начать запись
          </Button>
        )}
        <Button variant="secondary" className="text-xs" iconLeft={<Camera size={14} />} onClick={() => void recording('snapshot', { title: title || 'Снимок 20 с', comment, seconds: 20 })}>
          Снимок последних 20 с
        </Button>
        {active && <span className="flex items-center gap-1 text-xs text-[#ff8f84]"><Circle size={10} className="animate-pulse fill-current" /> идёт запись</span>}
      </div>

      {(opened || compare) && (
        <div className="glass-panel rounded-2xl p-4">
          <div className="mb-2 flex flex-wrap items-center gap-3 text-xs">
            {opened && <span className="text-[#f2cf87]">Сплошная: {opened.title} <button type="button" aria-label="Закрыть запись" className="ml-1 text-white/40 hover:text-white" onClick={() => closeRecording('main')}><X size={12} className="inline" /></button></span>}
            {compare && <span className="text-[#7fc8ff]">Пунктир: {compare.title} <button type="button" aria-label="Закрыть сравнение" className="ml-1 text-white/40 hover:text-white" onClick={() => closeRecording('compare')}><X size={12} className="inline" /></button></span>}
          </div>
          <TelemetryChart
            fields={(opened ?? compare)!.fields}
            samples={(opened ?? compare)!.samples}
            events={(opened ?? compare)!.events}
            channels={DEFAULT_CHANNELS}
            enabled={enabled}
            windowSeconds={Math.max(1, (opened ?? compare)!.durationS + 0.5)}
            overlay={opened && compare ? { fields: compare.fields, samples: compare.samples, label: compare.title } : null}
            height={320}
          />
          <div className="mt-2 flex flex-wrap gap-1">
            {DEFAULT_CHANNELS.map((channel) => (
              <button
                key={channel.field}
                type="button"
                onClick={() => setEnabled((prev) => { const next = new Set(prev); if (next.has(channel.field)) next.delete(channel.field); else next.add(channel.field); return next })}
                className={cn('flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px]', enabled.has(channel.field) ? 'border-white/20 bg-white/10 text-white' : 'border-transparent text-white/35 hover:text-white')}
              >
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: channel.color }} />
                {channel.label}
              </button>
            ))}
          </div>
          {opened && (
            <details className="mt-3 text-xs text-white/60">
              <summary className="cursor-pointer text-white/50">Параметры на момент записи</summary>
              <pre className="mt-2 max-h-48 overflow-auto font-mono text-[10px]">{JSON.stringify(opened.parameters, null, 1)}</pre>
            </details>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-3 text-sm font-semibold text-[#f2cf87]">Записи</h3>
          {renderList(recordings?.recordings ?? [], 'Сохранённых записей нет.')}
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <h3 className="mb-3 text-sm font-semibold text-[#ff8f84]">Чёрный ящик (инциденты)</h3>
          <p className="mb-2 text-[11px] text-white/40">Последние 60 с телеметрии сохраняются автоматически при СТОП, ошибке привода, критическом рассинхроне, отказе и препятствии.</p>
          {renderList(recordings?.incidents ?? [], 'Инцидентов не зафиксировано.')}
        </div>
      </div>
    </div>
  )
}
