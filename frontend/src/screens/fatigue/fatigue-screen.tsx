import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw } from 'lucide-react'
import { useState, type PropsWithChildren } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { FatigueData } from '@/entities/stage4/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { FatigueMode } from '@/entities/stage4/model/types'
import { fatigueModes } from '@/mocks/stage4-data'
import { apiGet, apiPost } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { ensureFatigueMuscleCoverage } from '@/shared/ui/stage4/fatigue-muscle-map'
import { MetricCardGrid, MuscleMapDetailed, MuscleSelectionPanel, Panel, PeriodSwitcher, SectionTitle, ToneBadge } from '@/shared/ui/stage4/screen-components'
import { useAppStore } from '@/stores/app-store'

function asFatigueMode(value: string | null): FatigueMode {
  if (value === 'current' || value === 'after-workout' || value === '7d' || value === '30d') {
    return value
  }

  return 'current'
}

// Embedded mode leaves the shell and emergency-stop overlay to ProgressScreen.
export function FatigueScreen({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const mode = asFatigueMode(searchParams.get('mode'))
  const userId = selectedUserId ?? 'alexey'
  const fatigueFigureGender = selectedUserId === 'elena' ? 'female' : 'male'
  const [resetInProgress, setResetInProgress] = useState(false)
  const { data, isLoading, error } = useQuery({
    queryKey: ['fatigue-screen', userId, mode],
    queryFn: () => apiGet<FatigueData>(`/api/fatigue?userId=${encodeURIComponent(userId)}&mode=${encodeURIComponent(mode)}`),
  })

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

  async function handleResetFatigue() {
    if (resetInProgress) {
      return
    }

    setResetInProgress(true)
    try {
      await apiPost('/api/fatigue/reset', { userId })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['fatigue-screen', userId] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard', userId] }),
      ])
    } finally {
      setResetInProgress(false)
    }
  }

  const muscles = data ? ensureFatigueMuscleCoverage(data.muscles) : []
  const selectedId = searchParams.get('muscle') ?? muscles[0]?.id ?? 'chest'
  const selectedMuscle = muscles.find((item) => item.id === selectedId) ?? muscles[0]
  const highOrCritical = muscles.filter((item) => item.status === 'high' || item.status === 'critical')
  const medium = muscles.filter((item) => item.status === 'medium')
  const ready = muscles.filter((item) => item.status === 'ready' || item.status === 'light')

  if (error || (data && !selectedMuscle)) {
    return (
      <FatigueFrame embedded={embedded}>
        <div className="glass-panel rounded-[34px] border border-[#eb5345]/25 bg-[#1b0f10] p-8 text-[#ffb4a7]">Не удалось загрузить данные усталости.</div>
      </FatigueFrame>
    )
  }

  if (isLoading || !data || !selectedMuscle) {
    return (
      <FatigueFrame embedded={embedded}>
        <div className="glass-panel rounded-[34px] p-8 text-white/72">Загрузка карты усталости…</div>
      </FatigueFrame>
    )
  }

  return (
    <FatigueFrame embedded={embedded} machine={data.machine}>
      <SectionTitle
        title="Усталость мышц"
        description="Следите за восстановлением мышц и выбирайте нагрузку без перегруза."
        actions={(
          <div className="flex flex-wrap items-center justify-end gap-3">
            <PeriodSwitcher periods={fatigueModes} active={mode} onChange={(value) => updateParams({ mode: value })} />
            <Button variant="ghost" disabled={resetInProgress} iconLeft={<RotateCcw className="h-4 w-4" />} onClick={() => void handleResetFatigue()}>
              {resetInProgress ? 'Сбрасываю…' : 'Сбросить усталость'}
            </Button>
          </div>
        )}
      />

      <div className="flex justify-end text-sm text-white/45">Данные обновлены: {data.updatedAt}</div>

      <MetricCardGrid items={data.overview} columns="xl:grid-cols-4" />

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <div className="space-y-6">
          <Panel title="Карта мышечной усталости" description={data.recoveryNote}>
            <MuscleMapDetailed muscles={muscles} selectedId={selectedMuscle.id} figureGender={fatigueFigureGender} onSelect={(id) => updateParams({ muscle: id })} />
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
              <Button onClick={() => navigate('/dashboard')}>Выбрать тренировку</Button>
              <Button variant="secondary" onClick={() => navigate('/calendar')}>Открыть календарь</Button>
            </div>
          </Panel>
        </div>
      </div>
    </FatigueFrame>
  )
}

function FatigueFrame({ embedded, machine, children }: PropsWithChildren<{ embedded: boolean; machine?: MachineHealth }>) {
  if (embedded) {
    return <>{children}</>
  }

  return <StandaloneFatigueFrame machine={machine}>{children}</StandaloneFatigueFrame>
}

function StandaloneFatigueFrame({ machine, children }: PropsWithChildren<{ machine?: MachineHealth }>) {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userName = selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'
  const fallbackMachine: MachineHealth = {
    machineState: 'ready',
    machineLabel: 'Загрузка статуса',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: 'Загрузка...',
  }

  return (
    <FormaShell userName={userName} machine={machine ?? fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      {children}
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}