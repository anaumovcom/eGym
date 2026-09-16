import { Download, GitCompare, Save, Trash2, Upload, Zap } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import { useAppStore } from '@/stores/app-store'
import { Button } from '@/shared/ui/button'

export function PresetsPanel({ serviceMode }: { serviceMode: boolean }) {
  const presets = useTuningStore((state) => state.presets)
  const diff = useTuningStore((state) => state.presetDiff)
  const tuning = useTuningStore((state) => state.tuning)
  const loadPresets = useTuningStore((state) => state.loadPresets)
  const savePreset = useTuningStore((state) => state.savePreset)
  const deletePreset = useTuningStore((state) => state.deletePreset)
  const diffPreset = useTuningStore((state) => state.diffPreset)
  const applyPreset = useTuningStore((state) => state.applyPreset)
  const setPending = useTuningStore((state) => state.setPending)
  const apply = useTuningStore((state) => state.apply)
  const setError = useTuningStore((state) => state.setError)
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const fileRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    void loadPresets()
  }, [loadPresets])

  const exportJson = () => {
    if (!tuning) return
    const blob = new Blob([JSON.stringify({ title: 'export', values: tuning.values }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `mechanics-tuning-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const importJson = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text()) as { values?: Record<string, unknown> }
      if (!parsed.values || typeof parsed.values !== 'object') throw new Error('В файле нет поля values')
      for (const [key, value] of Object.entries(parsed.values)) setPending(key, value)
      await apply('temporary', selectedUserId)
    } catch (error) {
      setError(error instanceof Error ? `Импорт не удался: ${error.message}` : 'Импорт не удался')
    }
  }

  return (
    <div className="space-y-4">
      <div className="glass-panel flex flex-wrap items-center gap-2 rounded-2xl p-4">
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Название пресета" aria-label="Название пресета" className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-[#d6b05f]/60" />
        <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Описание" aria-label="Описание пресета" className="min-w-[200px] flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-[#d6b05f]/60" />
        <Button className="text-xs" iconLeft={<Save size={14} />} disabled={!title.trim()} onClick={() => { void savePreset(title.trim(), description.trim(), selectedUserId); setTitle(''); setDescription('') }}>
          Сохранить текущие
        </Button>
        <Button variant="secondary" className="text-xs" iconLeft={<Download size={14} />} onClick={exportJson}>
          Экспорт JSON
        </Button>
        <Button variant="secondary" className="text-xs" iconLeft={<Upload size={14} />} disabled={!serviceMode} onClick={() => fileRef.current?.click()}>
          Импорт JSON
        </Button>
        <input ref={fileRef} type="file" accept="application/json" aria-label="Файл пресета" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importJson(file); event.target.value = '' }} />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {presets.map((preset) => (
          <div key={preset.id} className="glass-panel rounded-2xl p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-white">{preset.title} {preset.builtin && <span className="ml-1 rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-white/50">встроенный</span>}</div>
                <div className="text-xs text-white/45">{preset.description}</div>
                <div className="text-[10px] text-white/30">{Object.keys(preset.values).length} параметров{preset.createdAt ? ` · ${new Date(preset.createdAt).toLocaleString('ru-RU')}` : ''}</div>
              </div>
              {!preset.builtin && (
                <button type="button" aria-label={`Удалить пресет ${preset.title}`} onClick={() => void deletePreset(preset.id)} className="text-white/30 hover:text-[#ff8f84]">
                  <Trash2 size={14} />
                </button>
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="ghost" className="px-3 py-1.5 text-xs" iconLeft={<GitCompare size={14} />} onClick={() => void diffPreset(preset.id)}>
                Сравнить
              </Button>
              <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Zap size={14} />} disabled={!serviceMode} onClick={() => void applyPreset(preset.id, 'temporary', selectedUserId)}>
                Применить временно
              </Button>
              <Button className="px-3 py-1.5 text-xs" disabled={!serviceMode} onClick={() => void applyPreset(preset.id, 'persist', selectedUserId)}>
                Применить и сохранить
              </Button>
            </div>
            {diff?.presetId === preset.id && (
              <div className="mt-3 rounded-xl bg-black/30 p-3 text-xs">
                {diff.differences.length === 0 ? (
                  <span className="text-white/50">Отличий от текущих значений нет.</span>
                ) : (
                  <table className="w-full">
                    <thead className="text-white/40">
                      <tr><th className="text-left">Параметр</th><th className="text-right">Сейчас</th><th className="text-right">Пресет</th></tr>
                    </thead>
                    <tbody>
                      {diff.differences.map((item) => (
                        <tr key={item.key}>
                          <td className="py-0.5 text-white/70">{item.label} <span className="font-mono text-white/30">{item.key}</span></td>
                          <td className="text-right font-mono text-white/60">{String(item.current)}</td>
                          <td className="text-right font-mono text-[#f2cf87]">{String(item.preset)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
