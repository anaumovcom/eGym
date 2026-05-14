import { Camera, ChevronRight, House, Sparkles } from 'lucide-react'
import { useEffect } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { MuscleStatusList, SectionIntro } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function WorkoutSummaryScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const openPhotoProgress = useRuntimeStore((state) => state.openPhotoProgress)

  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    if (!session) {
      ensureSession(initOptions)
    }
  }, [ensureSession, initOptions, session])

  if (!session) {
    return null
  }

  const summary = session.workoutSummary

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={session.machine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro title={summary.title} description={summary.subtitle} />

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {summary.metrics.map((metric) => (
              <div key={metric.label} className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                <div className="text-sm text-white/45">{metric.label}</div>
                <div className="mt-2 font-display text-3xl font-bold text-white">{metric.value}</div>
                <div className="mt-1 text-xs text-white/35">{metric.hint}</div>
              </div>
            ))}
          </div>

          <div className="mt-6 overflow-hidden rounded-[28px] border border-white/8">
            <div className="bg-white/4 px-4 py-3 text-sm uppercase tracking-[0.24em] text-white/35">Упражнения тренировки</div>
            <div className="divide-y divide-white/8">
              {summary.exercises.map((exercise) => (
                <div key={exercise.name} className="flex items-center justify-between gap-4 px-4 py-4 text-white/74">
                  <div>
                    <div className="font-semibold text-white">{exercise.name}</div>
                    <div className="mt-1 text-sm text-white/45">{exercise.result}</div>
                  </div>
                  <div className="rounded-full border border-white/10 bg-white/4 px-3 py-2 text-xs uppercase tracking-[0.22em] text-white/55">{exercise.status}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Нагрузка на мышцы</div>
            <div className="mt-4">
              <MuscleStatusList muscles={summary.muscleLoad} />
            </div>
          </section>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="flex items-center gap-3 text-[#f2cf87]"><Sparkles className="h-5 w-5" />Следующий шаг</div>
            <div className="mt-3 text-sm leading-7 text-white/65">{summary.recommendation}</div>
            <div className="mt-4 rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 text-white/72">{summary.nextWorkout}</div>
            <div className="mt-5 flex flex-col gap-3">
              <Button
                iconLeft={<Camera className="h-4 w-4" />}
                onClick={() => {
                  openPhotoProgress('post-workout')
                  navigate(withSearch('/photo-progress', location.search))
                }}
              >
                Фото после тренировки
              </Button>
              <Button variant="secondary" iconLeft={<ChevronRight className="h-4 w-4" />} onClick={() => navigate('/today')}>
                Открыть план на сегодня
              </Button>
              <Button variant="secondary" iconLeft={<House className="h-4 w-4" />} onClick={() => navigate('/dashboard')}>
                На дашборд
              </Button>
            </div>
          </section>
        </aside>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}