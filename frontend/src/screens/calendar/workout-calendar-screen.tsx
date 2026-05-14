import { useQuery } from '@tanstack/react-query'
import { CalendarPlus, CalendarRange } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { WorkoutCalendarData } from '@/entities/calendar/model/types'
import { machineScenarios } from '@/mocks/data'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { CalendarDayCard, DayDetailsPanel, FilterChip, SectionIntro, SupportCard } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function WorkoutCalendarScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const selectedCalendarDayId = useAppStore((state) => state.selectedCalendarDayId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const setSelectedCalendarDayId = useAppStore((state) => state.setSelectedCalendarDayId)

  const mode = searchParams.get('mode') === 'week' ? 'week' : 'month'
  const selectedDayId = searchParams.get('selectedDayId') ?? selectedCalendarDayId ?? '2026-05-14'

  const { data } = useQuery({
    queryKey: ['workout-calendar', mode, selectedDayId],
    queryFn: () => apiGet<WorkoutCalendarData>(`/api/calendar?mode=${encodeURIComponent(mode)}&selectedDayId=${encodeURIComponent(selectedDayId)}`),
  })

  const visibleDays = useMemo(() => data?.days ?? [], [data?.days])

  if (!data) {
    return null
  }

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={machineScenarios.ready} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro
        title="Календарь тренировок"
        description="Планируйте тренировки с учётом целей, восстановления и нагрузки на мышцы. Доступны недельный и месячный виды на моковых данных."
        actions={
          <div className="flex flex-wrap gap-3">
            <div className="inline-flex rounded-[22px] border border-[#d6b05f]/20 bg-white/4 p-1">
              {(['week', 'month'] as const).map((nextMode) => (
                <button
                  key={nextMode}
                  type="button"
                  onClick={() =>
                    setSearchParams((current) => {
                      const next = new URLSearchParams(current)
                      next.set('mode', nextMode)
                      return next
                    })
                  }
                  className={nextMode === mode ? 'inline-flex min-h-11 items-center rounded-[18px] bg-[#3b2b11] px-4 text-sm text-[#f3d18b]' : 'inline-flex min-h-11 items-center rounded-[18px] px-4 text-sm text-white/58'}
                >
                  {nextMode === 'week' ? 'Неделя' : 'Месяц'}
                </button>
              ))}
            </div>
            <Button variant="secondary" iconLeft={<CalendarPlus className="h-4 w-4" />} onClick={() => navigate('/builder')}>
              Добавить тренировку
            </Button>
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
        <section className="space-y-6">
          <div className="glass-panel rounded-[32px] p-5">
            <div className="mb-5 flex items-center justify-between">
              <div className="font-display text-4xl font-bold text-white">{data.title}</div>
              <div className="flex flex-wrap gap-2">
                {data.legend.map((item) => (
                  <FilterChip key={item} label={item} />
                ))}
              </div>
            </div>

            <div className={mode === 'week' ? 'grid gap-4 xl:grid-cols-7' : 'grid gap-4 md:grid-cols-3 xl:grid-cols-7'}>
              {visibleDays.map((day) => (
                <CalendarDayCard
                  key={day.id}
                  day={day}
                  onSelect={() => {
                    setSelectedCalendarDayId(day.id)
                    setSearchParams((current) => {
                      const next = new URLSearchParams(current)
                      next.set('selectedDayId', day.id)
                      return next
                    })
                  }}
                />
              ))}
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-3">
            {data.summary.map((item) => (
              <section key={item.label} className="glass-panel rounded-[28px] p-5">
                <div className="font-display text-4xl font-bold text-white">{item.value}</div>
                <div className="mt-2 text-sm text-white/45">{item.label}</div>
              </section>
            ))}
          </div>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="mb-4 flex items-center gap-3 text-white/45"><CalendarRange className="h-4 w-4" />Баланс мышечных групп</div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {data.muscleBalance.map((item) => (
                <div key={item.label} className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                  <div className="text-sm text-white/45">{item.label}</div>
                  <div className="mt-2 font-display text-3xl font-bold text-white">{item.value}</div>
                </div>
              ))}
            </div>
          </section>
        </section>

        <aside className="space-y-6">
          <DayDetailsPanel details={data.selectedDay} onStart={() => navigate('/exercise-setup?source=calendar&photo=before')} onOpenPlan={() => navigate('/today')} />

          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Быстрые действия</div>
            <div className="mt-4 flex flex-col gap-3">
              {data.quickActions.map((item) => (
                <Button key={item} variant="secondary">{item}</Button>
              ))}
            </div>
          </section>

          <SupportCard />
        </aside>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}