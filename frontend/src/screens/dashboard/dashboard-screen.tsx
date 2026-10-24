import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Check, Clock3, Flame, Layers, ListChecks, Play, Plus, RotateCcw } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { DashboardBuilderWorkout, DashboardData } from '@/entities/dashboard/model/types'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { getRuntimeResumeView, isSessionInCurrentTrainingDay, runtimeViewPath } from '@/features/runtime/lib/runtime-day'
import { getWorkoutResumeSummary } from '@/features/runtime/lib/workout-progress'
import { useWorkoutOrder } from '@/features/workout-order/use-workout-order'
import { apiGet } from '@/shared/api/client'
import { exerciseCountLabel, plural, shortDuration } from '@/shared/lib/ru-format'
import { workoutBadge } from '@/entities/dashboard/lib/workout-badge'
import { WorkoutCardExercises } from '@/entities/dashboard/ui/workout-card-exercises'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { SortableCard, SortableGrid } from '@/shared/ui/sortable-grid'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { getNextPendingExercise, useRuntimeStore } from '@/stores/runtime-store'
import { HomeRecovery } from '@/screens/dashboard/home-recovery'
import { WorkoutMuscleLoad } from '@/screens/dashboard/workout-muscle-load'
import './workout-dialog.css'

export type DashboardViewProps = {
  data: DashboardData
  userName: string
  emergencyStopActive: boolean
  onStop: () => void
  onEmergencyStopChange: (open: boolean) => void
  onReorderWorkouts?: (programIds: string[]) => void
}

function canResumeWorkout(session: RuntimeWorkoutSession | null, workout: DashboardBuilderWorkout) {
  return Boolean(session?.source === 'builder'
    && session.programId === workout.id
    && isSessionInCurrentTrainingDay(session)
    && session.exercises.length === workout.exercises.length
    && session.exercises.every((exercise, index) => exercise.slug === workout.exercises[index].slug))
}

/** A run that was left before its summary: the home indicator continues it from the saved step. */
function isUnfinishedWorkout(session: RuntimeWorkoutSession | null, workout: DashboardBuilderWorkout, userId: string | null) {
  return Boolean(session
    && session.view !== 'workout-summary'
    && (!session.userId || session.userId === userId)
    && canResumeWorkout(session, workout))
}

function UnfinishedWorkoutIndicator({ session, workout, onContinue }: { session: RuntimeWorkoutSession; workout: DashboardBuilderWorkout; onContinue: () => void }) {
  const summary = getWorkoutResumeSummary(session)
  const nextLabel = summary.nextLabel ?? getNextPendingExercise(session)?.name ?? null
  const percent = summary.totalSets > 0 ? Math.round((summary.doneSets / summary.totalSets) * 100) : 0
  return (
    <button type="button" className="home-resume" onClick={onContinue} aria-label={`Продолжить незавершённую тренировку «${workout.title}»${nextLabel ? `: дальше ${nextLabel}` : ''}`}>
      <span className="home-resume-icon" aria-hidden="true"><Play /></span>
      <span className="home-resume-body">
        <span className="home-resume-eyebrow">Незавершённая тренировка</span>
        <strong className="home-resume-title">{workout.title}</strong>
        <span className="home-resume-meta">
          <span>Упражнений {summary.doneExercises} из {summary.totalExercises}</span>
          <span>Подходов {summary.doneSets} из {summary.totalSets}</span>
          {nextLabel ? <span>Дальше: <b>{nextLabel}</b></span> : null}
        </span>
        <span className="home-resume-progress" aria-hidden="true"><span style={{ width: `${percent}%` }} /></span>
      </span>
      <span className="home-resume-action">Продолжить <ArrowRight aria-hidden="true" /></span>
    </button>
  )
}

function WorkoutStats({ workout }: { workout: DashboardBuilderWorkout }) {
  const sets = workout.totalSets ?? workout.exercises.reduce((total, exercise) => total + (exercise.targetSets ?? 0), 0)
  const muscles = workout.muscleLoad?.length ?? 0
  return (
    <ul className="wd-stats" aria-label="Коротко о тренировке">
      <li><ListChecks aria-hidden="true" /><b>{workout.exercises.length}</b> {plural(workout.exercises.length, 'упражнение', 'упражнения', 'упражнений')}</li>
      {sets ? <li><Layers aria-hidden="true" /><b>{sets}</b> {plural(sets, 'подход', 'подхода', 'подходов')}</li> : null}
      <li><Clock3 aria-hidden="true" /><b>{shortDuration(workout.duration).replace(/\s*мин$/, '')}</b> мин</li>
      {muscles ? <li><Flame aria-hidden="true" /><b>{muscles}</b> {plural(muscles, 'мышца', 'мышцы', 'мышц')}</li> : null}
    </ul>
  )
}

function WorkoutPlanRow({ exercise, index }: { exercise: DashboardBuilderWorkout['exercises'][number]; index: number }) {
  const target = exercise.targetSets ?? 0
  const plan = exercise.planLabel || (target ? `${target} ${plural(target, 'подход', 'подхода', 'подходов')}` : '')
  return (
    <li className="wd-plan-row" data-status={exercise.status}>
      <span className="home-card-exercise-index" aria-hidden="true">{exercise.status === 'completed' ? <Check /> : index + 1}</span>
      <span className="wd-plan-text">
        <span className="wd-plan-name">{exercise.name}</span>
        {plan ? <span className="wd-plan-sets">{plan}</span> : null}
      </span>
      {exercise.status === 'completed' ? <span className="wd-plan-state">Готово</span>
        : exercise.status === 'in_progress' && target ? <span className="wd-plan-state">{exercise.completedSets ?? 0} из {target}</span> : null}
    </li>
  )
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
  const saveWorkoutOrder = useWorkoutOrder(userId)

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

  return <DashboardView key={userId} data={data} userName={userName} emergencyStopActive={emergencyStopActive} onEmergencyStopChange={setEmergencyStopActive} onStop={() => setEmergencyStopActive(true)} onReorderWorkouts={(ids) => void saveWorkoutOrder(ids)} />
}

export function DashboardView({ data, userName, emergencyStopActive, onStop, onEmergencyStopChange, onReorderWorkouts }: DashboardViewProps) {
  return (
    <FormaShell userName={userName} machine={data.machine} onStop={onStop}>
      {data.alerts.map((alert) => alert.tone === 'blocked'
        ? <BlockingAlert key={alert.title} title={alert.title} description={alert.description} />
        : <WarningBanner key={alert.title} title={alert.title} description={alert.description} />)}
      <DashboardWorkoutsSection workouts={data.workouts ?? []} muscles={data.muscles} onReorder={onReorderWorkouts} />
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={onEmergencyStopChange} />
    </FormaShell>
  )
}

function DashboardWorkoutsSection({ workouts, muscles, onReorder }: { workouts: DashboardBuilderWorkout[]; muscles: DashboardData['muscles']; onReorder?: (programIds: string[]) => void }) {
  const navigate = useNavigate()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const setSelectedProgramId = useAppStore((state) => state.setSelectedProgramId)
  const runtimeSession = useRuntimeStore((state) => state.session)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [restartConfirm, setRestartConfirm] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [restartError, setRestartError] = useState<string | null>(null)
  const selectedWorkout = workouts.find((workout) => workout.id === selectedId)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const confirmingRef = useRef(false)
  const resumable = selectedWorkout ? canResumeWorkout(runtimeSession, selectedWorkout) : false
  const continueAvailable = resumable
  const serverProgressOnly = !resumable && (selectedWorkout?.todayStatus === 'in_progress' || selectedWorkout?.resumeAvailable === true)
  const unfinishedWorkout = workouts.find((workout) => isUnfinishedWorkout(runtimeSession, workout, selectedUserId))

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
    const runQuery = resumed?.runId ? `&runId=${encodeURIComponent(resumed.runId)}` : ''
    navigate(`${path}?source=builder&programId=${encodeURIComponent(workout.id)}${runQuery}`)
  }

  async function handleRestart(workout: DashboardBuilderWorkout) {
    if (!workout.exercises.length || confirmingRef.current) return
    confirmingRef.current = true
    setRestarting(true)
    setRestartError(null)
    try {
      // Do not discard the runtime while an interrupted set still owns the motor.
      const hardware = useHardwareStore.getState()
      const session = useRuntimeStore.getState().session
      if (['moving', 'start_hold', 'training', 'paused', 'fixed_hold'].includes(hardware.snapshot?.control?.mode ?? '')) {
        await hardware.runCommand({ action: 'complete_set', userId: selectedUserId })
      }
      // A new run must not reuse cached builder data or any saved backend result IDs.
      // Existing exercise/workout records remain in history; this is not a deletion.
      if (useRuntimeStore.getState().session !== session) {
        throw new Error('Тренировка изменилась. Закройте окно и попробуйте ещё раз.')
      }
      const runId = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
      useRuntimeStore.getState().resetSession()
      setSelectedProgramId(workout.id)
      navigate(`/exercise-setup?source=builder&programId=${encodeURIComponent(workout.id)}&runId=${runId}`)
    } catch (error) {
      confirmingRef.current = false
      setRestartError(error instanceof Error ? error.message : 'Не удалось начать тренировку сначала. Попробуйте ещё раз.')
    } finally {
      setRestarting(false)
    }
  }

  return (
    <section className="home-workouts" aria-labelledby="home-workouts-title">
      <header className="home-heading">
        <div className="min-w-0">
          <h1 id="home-workouts-title" className="font-display font-bold text-white">Какую тренировку выберете?</h1>
          {workouts.length ? <p>Нажмите на карточку, чтобы посмотреть упражнения и начать. Перетащите, чтобы изменить порядок</p> : null}
        </div>
        <div className="home-heading-actions">
          <Button variant="secondary" iconLeft={<Plus aria-hidden="true" />} onClick={() => navigate('/builder?create=new')}>Новая тренировка</Button>
        </div>
      </header>
      {unfinishedWorkout && runtimeSession ? (
        <UnfinishedWorkoutIndicator
          session={runtimeSession}
          workout={unfinishedWorkout}
          onContinue={() => handleConfirm(unfinishedWorkout)}
        />
      ) : null}
      {workouts.length === 0 ? <p className="text-center text-white/60">Тренировки не найдены. Создайте первую и добавьте упражнения.</p> : null}
      <div className="home-workouts-layout">
      <SortableGrid className="home-workout-grid" data-count={workouts.length} ids={workouts.map((workout) => workout.id)} onReorder={(ids) => onReorder?.(ids)}>
        {workouts.map((workout) => {
          const badge = workoutBadge(workout, canResumeWorkout(runtimeSession, workout))
          const count = workout.exercises.length
          return (
          <SortableCard
            key={workout.id}
            sortableId={workout.id}
            className="home-workout-card"
            data-tone={badge.tone}
            aria-label={`Выбрать тренировку «${workout.title}»`}
            aria-haspopup="dialog"
            onClick={(event) => {
              triggerRef.current = event.currentTarget
              confirmingRef.current = false
              setRestartConfirm(false)
              setRestartError(null)
              setSelectedId(workout.id)
            }}
          >
            <span className="home-card-badge" data-tone={badge.tone}>{badge.label}</span>
            <span className="home-card-title">{workout.title}</span>
            <WorkoutCardExercises exercises={workout.exercises} />
            <span className="home-card-footer">
              <span className="home-card-meta">
                <span><ListChecks aria-hidden="true" />{exerciseCountLabel(count)}</span>
                {count ? <span><Clock3 aria-hidden="true" />{shortDuration(workout.duration)}</span> : null}
              </span>
              <span className="home-card-select">{count ? 'Начать' : 'Добавить'} <ArrowRight aria-hidden="true" /></span>
            </span>
          </SortableCard>
          )
        })}
      </SortableGrid>
      <HomeRecovery muscles={muscles} figureGender={selectedUserId === 'elena' ? 'female' : 'male'} />
      </div>
      <Dialog.Root open={Boolean(selectedWorkout)} onOpenChange={(open) => { if (!open && !restarting) setSelectedId(null) }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className={restartConfirm ? 'home-confirm-panel' : 'home-confirm-panel wd-panel'} rootClassName={restartConfirm ? undefined : 'wd-root'} onOpenAutoFocus={(event) => {
            // Start on the main action, not on the first muscle of the map.
            const primary = (event.currentTarget as HTMLElement | null)?.querySelector<HTMLButtonElement>('.home-confirm-actions [data-variant="primary"]:not(:disabled)')
            if (primary) { event.preventDefault(); primary.focus() }
          }} onCloseAutoFocus={(event) => {
            // No automatic card selection: return to the exact card the user opened.
            event.preventDefault()
            if (triggerRef.current?.isConnected) triggerRef.current.focus()
          }}>
            {selectedWorkout ? <>
              <header className="wd-header">
                {!restartConfirm ? <span className="home-card-badge" data-tone={workoutBadge(selectedWorkout, resumable).tone}>{workoutBadge(selectedWorkout, resumable).label}</span> : null}
                <Dialog.Title className="font-display text-3xl font-bold text-white">{restartConfirm ? 'Начать тренировку сначала?' : selectedWorkout.title}</Dialog.Title>
                <Dialog.Description className="text-base text-white/60">{shortDuration(selectedWorkout.duration)} · {workoutStatus(selectedWorkout, resumable)}</Dialog.Description>
                {!restartConfirm && selectedWorkout.exercises.length ? <WorkoutStats workout={selectedWorkout} /> : null}
              </header>
              {!restartConfirm && selectedWorkout.exercises.length ? <div className="wd-body">
                <section className="wd-plan" aria-labelledby="wd-plan-title">
                  <h3 id="wd-plan-title" className="wd-section-title">План тренировки</h3>
                  <ol className="wd-plan-list" aria-labelledby="wd-plan-title">
                    {selectedWorkout.exercises.map((exercise, index) => <WorkoutPlanRow key={`${exercise.slug}-${index}`} exercise={exercise} index={index} />)}
                  </ol>
                </section>
                <WorkoutMuscleLoad muscles={selectedWorkout.muscleLoad ?? []} figureGender={selectedUserId === 'elena' ? 'female' : 'male'} />
              </div> : null}
              <footer className="wd-footer">
                {restartConfirm ? <p className="text-sm text-white/60">«{selectedWorkout.title}» начнётся с первого упражнения и первого подхода. Продолжить текущую сессию после этого будет нельзя. Уже сохранённые результаты останутся в истории.</p> : !selectedWorkout.exercises.length ? <p className="text-sm text-white/60">Добавьте упражнения через «Изменить», прежде чем начинать.</p> : <p className="text-sm text-white/60">{continueAvailable ? 'Продолжение с сохранённого шага.' : serverProgressOnly ? 'Есть сохранённые результаты, но шаг продолжения на этом устройстве недоступен. Будет начата новая сессия с первого упражнения; история сохранится.' : 'Далее — настройка упражнения и проверка безопасности.'}</p>}
                {restartError ? <p role="alert" className="text-sm text-red-400">{restartError}</p> : null}
                {restartConfirm ? <div className="home-confirm-actions">
                  <Button variant="secondary" disabled={restarting} onClick={() => { setRestartConfirm(false); setRestartError(null) }}>Отмена</Button>
                  <Button disabled={restarting} iconLeft={<RotateCcw aria-hidden="true" />} onClick={() => void handleRestart(selectedWorkout)}>{restarting ? 'Начинаем…' : 'Начать сначала'}</Button>
                </div> : <div className="home-confirm-actions">
                  <Dialog.Close asChild><Button variant="secondary">Назад</Button></Dialog.Close>
                  <Button disabled={!selectedWorkout.exercises.length} onClick={() => handleConfirm(selectedWorkout)}>{continueAvailable ? 'Продолжить' : 'Начать'}</Button>
                  {continueAvailable ? <Button variant="secondary" iconLeft={<RotateCcw aria-hidden="true" />} onClick={() => setRestartConfirm(true)}>Начать сначала</Button> : null}
                  <Button variant="secondary" onClick={() => navigate(`/builder?programId=${encodeURIComponent(selectedWorkout.id)}`)}>Изменить</Button>
                </div>}
              </footer>
            </> : null}
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  )
}
