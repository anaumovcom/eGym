import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Clock3, Dumbbell, Plus } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { DashboardBuilderWorkout, DashboardData } from '@/entities/dashboard/model/types'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { getRuntimeResumeView, isSessionInCurrentTrainingDay, runtimeViewPath } from '@/features/runtime/lib/runtime-day'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import { HomeRecovery } from '@/screens/dashboard/home-recovery'

export type DashboardViewProps = {
  data: DashboardData
  userName: string
  emergencyStopActive: boolean
  onStop: () => void
  onEmergencyStopChange: (open: boolean) => void
}

function canResumeWorkout(session: RuntimeWorkoutSession | null, workout: DashboardBuilderWorkout) {
  return Boolean(session?.source === 'builder'
    && session.programId === workout.id
    && isSessionInCurrentTrainingDay(session)
    && session.exercises.length === workout.exercises.length
    && session.exercises.every((exercise, index) => exercise.slug === workout.exercises[index].slug))
}

function workoutStatus(workout: DashboardBuilderWorkout, resumable: boolean) {
  if (workout.todayStatus === 'completed') return 'Сегодня выполнена'
  if (workout.todayStatus === 'partial') return 'Сегодня выполнена частично'
  if (workout.todayStatus === 'aborted') return 'Сегодня прервана'
  if (resumable || workout.todayStatus === 'in_progress') return 'Есть незавершённая тренировка'
  if (workout.lastPerformedAt && workout.lastStatus) {
    const date = new Date(workout.lastPerformedAt)
    if (!Number.isNaN(date.getTime())) {
      const status = { completed: 'Выполнена', partial: 'Выполнена частично', aborted: 'Прервана' }[workout.lastStatus]
      return `${status} · ${date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}`
    }
  }
  return 'Нет сохранённых выполнений'
}

export function DashboardScreen() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const [searchParams] = useSearchParams()
  const scenario = searchParams.get('scenario') ?? 'default'
  const userId = selectedUserId ?? 'alexey'
  const userName = userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
  const { data, isError, refetch } = useQuery({
    queryKey: ['dashboard', userId, scenario],
    queryFn: () => apiGet<DashboardData>(`/api/dashboard?userId=${encodeURIComponent(userId)}&scenario=${encodeURIComponent(scenario)}`),
  })

  if (!data) {
    return (
      <FormaShell userName={userName} machine={{ machineState: 'warning', machineLabel: 'Проверка связи с тренажёром', leftDrive: 'warning', rightDrive: 'warning', safety: 'enabled', calibration: '' }} onStop={() => setEmergencyStopActive(true)}>
        <section className="home-empty glass-panel" aria-live="polite">
          <h1>{isError ? 'Не удалось загрузить тренировки' : 'Загрузка тренировок…'}</h1>
          {isError ? <Button onClick={() => void refetch()}>Повторить</Button> : null}
        </section>
        <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
      </FormaShell>
    )
  }

  return <DashboardView key={userId} data={data} userName={userName} emergencyStopActive={emergencyStopActive} onEmergencyStopChange={setEmergencyStopActive} onStop={() => setEmergencyStopActive(true)} />
}

export function DashboardView({ data, userName, emergencyStopActive, onStop, onEmergencyStopChange }: DashboardViewProps) {
  return (
    <FormaShell userName={userName} machine={data.machine} onStop={onStop}>
      {data.alerts.map((alert) => alert.tone === 'blocked'
        ? <BlockingAlert key={alert.title} title={alert.title} description={alert.description} />
        : <WarningBanner key={alert.title} title={alert.title} description={alert.description} />)}
      <DashboardWorkoutsSection workouts={data.workouts ?? []} muscles={data.muscles} />
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={onEmergencyStopChange} />
    </FormaShell>
  )
}

function DashboardWorkoutsSection({ workouts, muscles }: { workouts: DashboardBuilderWorkout[]; muscles: DashboardData['muscles'] }) {
  const navigate = useNavigate()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const setSelectedProgramId = useAppStore((state) => state.setSelectedProgramId)
  const runtimeSession = useRuntimeStore((state) => state.session)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selectedWorkout = workouts.find((workout) => workout.id === selectedId)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const confirmingRef = useRef(false)
  const resumable = selectedWorkout ? canResumeWorkout(runtimeSession, selectedWorkout) : false
  const continueAvailable = resumable
  const serverProgressOnly = !resumable && (selectedWorkout?.todayStatus === 'in_progress' || selectedWorkout?.resumeAvailable === true)

  function handleConfirm(workout: DashboardBuilderWorkout) {
    if (!workout.exercises.length || confirmingRef.current) return
    confirmingRef.current = true
    setSelectedProgramId(workout.id)
    // Resolve against the latest store only after explicit confirmation. Browsing
    // and cancelling never advances exercise-summary or clears persisted results.
    const session = useRuntimeStore.getState().session
    const canResume = canResumeWorkout(session, workout)
    if (canResume && session?.view === 'exercise-summary') {
      useRuntimeStore.getState().continueAfterExerciseSummary()
    }
    const resumed = canResume ? useRuntimeStore.getState().session : null
    const path = resumed ? runtimeViewPath(getRuntimeResumeView(resumed)) : '/exercise-setup'
    navigate(`${path}?source=builder&programId=${encodeURIComponent(workout.id)}`)
  }

  return (
    <section className="home-workouts" aria-labelledby="home-workouts-title">
      <header className="home-heading">
        <h1 id="home-workouts-title" className="font-display font-bold text-white">Какую тренировку выберете?</h1>
      </header>
      {workouts.length === 0 ? <p className="text-center text-white/60">Тренировки не найдены. Создайте первую и добавьте упражнения.</p> : null}
      <div className="home-workouts-layout">
      <div className="home-workout-grid" data-count={workouts.length}>
        {workouts.map((workout, index) => (
          <button
            key={workout.id}
            type="button"
            className="home-workout-card"
            aria-label={`Выбрать тренировку «${workout.title}»`}
            aria-haspopup="dialog"
            onClick={(event) => {
              triggerRef.current = event.currentTarget
              confirmingRef.current = false
              setSelectedId(workout.id)
            }}
          >
            <span className="home-card-top"><span className="home-card-icon"><Dumbbell aria-hidden="true" /></span><span className="text-xs text-white/60">{String(index + 1).padStart(2, '0')}</span></span>
            <span className="home-card-title">{workout.title}</span>
            <span className="home-card-exercises">{workout.exercises.length ? workout.exercises.slice(0, 3).map((exercise) => exercise.name).join(' · ') : 'Пока нет упражнений'}</span>
            {workout.exercises.length > 3 ? <span className="text-xs text-white/60">Ещё {workout.exercises.length - 3}</span> : null}
            <span className="home-card-meta"><span className="inline-flex items-center gap-2"><Clock3 aria-hidden="true" className="h-5 w-5" />{workout.duration}</span><span>{workoutStatus(workout, canResumeWorkout(runtimeSession, workout))}</span></span>
            <span className="home-card-select">Выбрать <ArrowRight aria-hidden="true" className="h-5 w-5" /></span>
          </button>
        ))}
        {workouts.length < 4 ? (
          <button type="button" className="home-workout-card home-create-card" onClick={() => navigate('/builder?create=new')}>
            <Plus aria-hidden="true" />
            <span className="home-card-title">Новая тренировка</span>
            <span className="text-sm text-white/60">Соберите свой набор упражнений</span>
          </button>
        ) : null}
      </div>
      <HomeRecovery muscles={muscles} figureGender={selectedUserId === 'elena' ? 'female' : 'male'} />
      </div>
      <Dialog.Root open={Boolean(selectedWorkout)} onOpenChange={(open) => { if (!open) setSelectedId(null) }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="home-confirm-panel" onCloseAutoFocus={(event) => {
            // No automatic card selection: return to the exact card the user opened.
            event.preventDefault()
            if (triggerRef.current?.isConnected) triggerRef.current.focus()
          }}>
            {selectedWorkout ? <>
              <Dialog.Title className="font-display text-3xl font-bold text-white">{selectedWorkout.title}</Dialog.Title>
              <Dialog.Description className="mt-3 text-base text-white/60">{selectedWorkout.duration} · {workoutStatus(selectedWorkout, resumable)}</Dialog.Description>
              <ol className="home-confirm-exercises">
                {selectedWorkout.exercises.map((exercise, index) => <li key={`${exercise.slug}-${index}`}><span className="text-white/60">{index + 1}.</span> {exercise.name}</li>)}
              </ol>
              {!selectedWorkout.exercises.length ? <p className="text-sm text-white/60">Добавьте упражнения через «Изменить», прежде чем начинать.</p> : <p className="text-sm text-white/60">{continueAvailable ? 'Продолжение с сохранённого шага.' : serverProgressOnly ? 'Есть сохранённые результаты, но шаг продолжения на этом устройстве недоступен. Будет начата новая сессия с первого упражнения; история сохранится.' : 'Далее — настройка упражнения и проверка безопасности.'}</p>}
              <div className="home-confirm-actions">
                <Dialog.Close asChild><Button variant="secondary">Назад</Button></Dialog.Close>
                <Button disabled={!selectedWorkout.exercises.length} onClick={() => handleConfirm(selectedWorkout)}>{continueAvailable ? 'Продолжить' : 'Начать'}</Button>
                <Button variant="secondary" onClick={() => navigate(`/builder?programId=${encodeURIComponent(selectedWorkout.id)}`)}>Изменить</Button>
              </div>
            </> : null}
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  )
}
