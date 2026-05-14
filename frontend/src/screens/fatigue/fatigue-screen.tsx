import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { FatigueMode } from '@/entities/stage4/model/types'
import { buildFatigueData, fatigueModes } from '@/mocks/stage4-data'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { MetricCardGrid, MuscleMapDetailed, MuscleSelectionPanel, Panel, PeriodSwitcher, SectionTitle, Stage4DevPanel, ToneBadge } from '@/shared/ui/stage4/screen-components'
import { useStage4Screen } from '@/features/stage4/lib/use-stage4-screen'

function asFatigueMode(value: string | null): FatigueMode {
  if (value === 'current' || value === 'after-workout' || value === '7d' || value === '30d') {
    return value
  }

  return 'current'
}

export function FatigueScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { userName, emergencyStopActive, setEmergencyStopActive, dev, patchDevFlags, resetDevFlags } = useStage4Screen()
  const mode = asFatigueMode(searchParams.get('mode'))

  const effectiveDev = useMemo(() => {
    if (mode === 'after-workout') {
      return { ...dev, offlineHours: 0 }
    }

    if (mode === '7d') {
      return { ...dev, offlineHours: Math.max(dev.offlineHours, 24 * 7) }
    }

    if (mode === '30d') {
      return { ...dev, offlineHours: Math.max(dev.offlineHours, 24 * 30) }
    }

    return dev
  }, [dev, mode])

  const data = useMemo(() => buildFatigueData({ dev: effectiveDev }), [effectiveDev])
  const selectedId = searchParams.get('muscle') ?? data.muscles[0]?.id ?? 'chest'
  const selectedMuscle = data.muscles.find((item) => item.id === selectedId) ?? data.muscles[0]
  const highOrCritical = data.muscles.filter((item) => item.status === 'high' || item.status === 'critical')
  const medium = data.muscles.filter((item) => item.status === 'medium')
  const ready = data.muscles.filter((item) => item.status === 'ready' || item.status === 'light')

  function updateParams(patch: Record<string, string | null>) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)

      Object.entries(patch).forEach(([key, value]) => {
        if (!value) {
          next.delete(key)
        } else {
          next.set(key, value)
        }
      })

      return next
    })
  }

  if (!selectedMuscle) {
    return null
  }

  return (
    <FormaShell userName={userName} machine={data.machine} onStop={() => setEmergencyStopActive(true)}>
      <SectionTitle
        title="Усталость мышц"
        description="Следите за восстановлением мышц и выбирайте нагрузку без перегруза."
        actions={<PeriodSwitcher periods={fatigueModes} active={mode} onChange={(value) => updateParams({ mode: value })} />}
      />

      <div className="flex justify-end text-sm text-white/45">Данные обновлены: {data.updatedAt}</div>

      <MetricCardGrid items={data.overview} columns="xl:grid-cols-4" />

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <div className="space-y-6">
          <Panel title="Карта мышечной усталости" description={data.recoveryNote}>
            <MuscleMapDetailed muscles={data.muscles} selectedId={selectedMuscle.id} onSelect={(id) => updateParams({ muscle: id })} />
          </Panel>

          <div className="grid gap-6 xl:grid-cols-3">
            <Panel title="Состояние мышц">
              <div className="space-y-3 text-sm text-white/72">
                {highOrCritical.map((item) => (
                  <div key={item.id} className="flex items-center gap-3 rounded-[20px] border border-white/8 bg-white/4 px-3 py-3"><ToneBadge status={item.status} /><span>{item.name}</span></div>
                ))}
              </div>
            </Panel>
            <Panel title="Рекомендуется сегодня">
              <div className="space-y-3 text-sm text-white/72">
                {ready.slice(0, 4).map((item) => (
                  <div key={item.id} className="flex items-center gap-3 rounded-[20px] border border-white/8 bg-white/4 px-3 py-3"><ToneBadge status={item.status} /><span>{item.name}</span></div>
                ))}
              </div>
            </Panel>
            <Panel title="Под наблюдением">
              <div className="space-y-3 text-sm text-white/72">
                {medium.map((item) => (
                  <div key={item.id} className="flex items-center gap-3 rounded-[20px] border border-white/8 bg-white/4 px-3 py-3"><ToneBadge status={item.status} /><span>{item.name}</span></div>
                ))}
              </div>
            </Panel>
          </div>
        </div>

        <div className="space-y-6">
          <MuscleSelectionPanel muscle={selectedMuscle} />
          <Panel title="Рекомендация Forma">
            <div className="text-sm leading-7 text-white/68">{data.recommendedPlan}</div>
            <div className="mt-5 flex flex-col gap-3">
              <Button onClick={() => navigate('/today')}>Сгенерировать тренировку</Button>
              <Button variant="secondary" onClick={() => navigate('/calendar')}>Открыть календарь</Button>
            </div>
          </Panel>
        </div>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
      <Stage4DevPanel value={dev} onChange={patchDevFlags} onReset={resetDevFlags} />
    </FormaShell>
  )
}