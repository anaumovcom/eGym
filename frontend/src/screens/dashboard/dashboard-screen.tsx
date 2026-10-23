import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Clock3, ListChecks, Play, Plus, RotateCcw } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { DashboardBuilderWorkout, DashboardData } from '@/entities/dashboard/model/types'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { getRuntimeResumeView, isSessionInCurrentTrainingDay, runtimeViewPath } from '@/features/runtime/lib/runtime-day'
import { getWorkoutResumeSummary } from '@/features/runtime/lib/workout-progress'
import { apiGet } from '@/shared/api/client'
import { exerciseCountLabel, shortDuration } from '@/shared/lib/ru-format'
import { workoutBadge } from '@/entities/dashboard/lib/workout-badge'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { getNextPendingExercise, useRuntimeStore } from '@/stores/runtime-store'
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
          {workouts.length ? <p>Нажмите на карточку, чтобы посмотреть упражнения и начать</p> : null}
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
      <div className="home-workout-grid" data-count={workouts.length}>
        {workouts.map((workout) => {
          const badge = workoutBadge(workout, canResumeWorkout(runtimeSession, workout))
          const count = workout.exercises.length
          return (
          <button
            key={workout.id}
            type="button"
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
            <span className="home-card-exercises">
              {count ? <>
                {workout.exercises.slice(0, 3).map((exercise) => exercise.name).join(' · ')}
                {count > 3 ? <span className="home-card-more"> и ещё {count - 3}</span> : null}
              </> : 'Пока нет упражнений'}
            </span>
            <span className="home-card-footer">
              <span className="home-card-meta">
                <span><ListChecks aria-hidden="true" />{exerciseCountLabel(count)}</span>
                <span><Clock3 aria-hidden="true" />{shortDuration(workout.duration)}</span>
              </span>
              <span className="home-card-select">{count ? 'Начать' : 'Добавить'} <ArrowRight aria-hidden="true" /></span>
            </span>
          </button>
          )
        })}
      </div>
      <HomeRecovery muscles={muscles} figureGender={selectedUserId === 'elena' ? 'female' : 'male'} />
      </div>
      <Dialog.Root open={Boolean(selectedWorkout)} onOpenChange={(open) => { if (!open && !restarting) setSelectedId(null) }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="home-confirm-panel" onCloseAutoFocus={(event) => {
            // No automatic card selection: return to the exact card the user opened.
            event.preventDefault()
            if (triggerRef.current?.isConnected) triggerRef.current.focus()
          }}>
            {selectedWorkout ? <>
              <Dialog.Title className="font-display text-3xl font-bold text-white">{restartConfirm ? 'Начать тренировку сначала?' : selectedWorkout.title}</Dialog.Title>
              <Dialog.Description className="mt-3 text-base text-white/60">{shortDuration(selectedWorkout.duration)} · {workoutStatus(selectedWorkout, resumable)}</Dialog.Description>
              <ol className="home-confirm-exercises">
                {selectedWorkout.exercises.map((exercise, index) => <li key={`${exercise.slug}-${index}`}><span className="text-white/60">{index + 1}.</span> {exercise.name}</li>)}
              </ol>
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
            </> : null}
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  )
}
