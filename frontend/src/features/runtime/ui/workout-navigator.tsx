import * as Dialog from '@radix-ui/react-dialog'
import { CheckCircle2, CircleDashed, ListOrdered, Play, RotateCcw, SkipForward } from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { truncateExerciseOnBackend } from '@/features/runtime/lib/runtime-persistence'
import { withSearch } from '@/features/runtime/lib/runtime-query'
import { canJumpToWorkoutStep, describeWorkoutSet, getWorkoutProgress, type WorkoutExerciseProgress } from '@/features/runtime/lib/workout-progress'
import { plural } from '@/shared/lib/ru-format'
import { Button } from '@/shared/ui/button'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'

const ACTIVE_SET_MODES = ['moving', 'start_hold', 'training', 'paused', 'fixed_hold']

type PendingRedo = { exerciseId: string; setIndex: number }

const statusText: Record<WorkoutExerciseProgress['status'], string> = {
  done: 'Выполнено',
  partial: 'Частично',
  skipped: 'Пропущено',
  current: 'Сейчас',
  pending: 'Не начато',
}

function setsLabel(count: number) {
  return `${count} ${plural(count, 'подход', 'подхода', 'подходов')}`
}

/**
 * Workout plan between sets: shows what is done and opens any exercise or set.
 * Only offered when no set is running, so a jump never interrupts a loaded bar.
 */
export function WorkoutNavigator({ session, disabled = false, onOpenChange }: { session: RuntimeWorkoutSession; disabled?: boolean; onOpenChange?: (open: boolean) => void }) {
  const navigate = useNavigate()
  const location = useLocation()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const jumpToWorkoutStep = useRuntimeStore((state) => state.jumpToWorkoutStep)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const [open, setOpen] = useState(false)
  const [pendingRedo, setPendingRedo] = useState<PendingRedo | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const progress = getWorkoutProgress(session)
  const doneExercises = progress.filter((item) => item.status === 'done').length
  const redoExercise = pendingRedo ? session.exercises.find((item) => item.id === pendingRedo.exerciseId) : undefined
  const redoDoneSets = pendingRedo ? session.completedSets[pendingRedo.exerciseId]?.length ?? 0 : 0

  function changeOpen(next: boolean) {
    if (busy) return
    setOpen(next)
    setPendingRedo(null)
    setError(null)
    onOpenChange?.(next)
  }

  async function jump(exerciseId: string, setIndex: number) {
    if (busy) return
    const latest = useRuntimeStore.getState().session
    if (!latest || !canJumpToWorkoutStep(latest, exerciseId, setIndex)) return
    const target = latest.exercises.find((item) => item.id === exerciseId)!
    const current = latest.exercises.find((item) => item.id === latest.currentExerciseId) ?? latest.exercises[0]
    setBusy(true)
    setError(null)
    try {
      // A set the bar may still hold is closed first, as on every other exercise change.
      const mode = useHardwareStore.getState().snapshot?.control?.mode ?? ''
      if (selectedUserId && ACTIVE_SET_MODES.includes(mode)) {
        await runCommand({ action: 'complete_set', userId: selectedUserId, exerciseSlug: current.slug })
      }
      const staleIds = await truncateExerciseOnBackend(latest, target, setIndex, selectedUserId ?? 'alexey')
      const now = useRuntimeStore.getState().session
      if (!now || now.id !== latest.id || now.currentExerciseId !== latest.currentExerciseId || now.view !== latest.view) {
        throw new Error('Тренировка изменилась. Откройте список упражнений ещё раз.')
      }
      if (!jumpToWorkoutStep(exerciseId, setIndex, staleIds)) {
        throw new Error('Этот подход сейчас недоступен.')
      }
      setBusy(false)
      setPendingRedo(null)
      setOpen(false)
      onOpenChange?.(false)
      // The rest, summary or set screen left behind no longer exists: history back must not land on it.
      navigate(withSearch('/exercise-setup', location.search), { replace: true })
    } catch (jumpError) {
      setError(jumpError instanceof Error ? jumpError.message : 'Не удалось перейти к упражнению. Попробуйте ещё раз.')
      setBusy(false)
    }
  }

  function openSet(item: WorkoutExerciseProgress, setIndex: number) {
    const step = item.sets[setIndex]
    if (!step?.available) return
    if (step.redo) {
      setError(null)
      setPendingRedo({ exerciseId: item.exercise.id, setIndex })
      return
    }
    void jump(item.exercise.id, setIndex)
  }

  return (
    <Dialog.Root open={open} onOpenChange={changeOpen}>
      <Dialog.Trigger asChild>
        <Button variant="secondary" className="rt-nav-trigger" disabled={disabled} iconLeft={<ListOrdered aria-hidden="true" />} aria-label={`Упражнения тренировки: выполнено ${doneExercises} из ${progress.length}`}>
          <span>Упражнения</span>
          <span className="rt-nav-dots" aria-hidden="true">
            {progress.map((item) => <span key={item.exercise.id} data-status={item.status} />)}
          </span>
          <span className="rt-nav-count" aria-hidden="true">{doneExercises}/{progress.length}</span>
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
        <SafetyDialogContent className="rt-nav-panel">
          {pendingRedo && redoExercise ? (
            <>
              <Dialog.Title className="font-display text-3xl font-bold">Повторить {describeWorkoutSet(redoExercise, pendingRedo.setIndex)}?</Dialog.Title>
              <Dialog.Description className="mt-2 text-sm text-white/70">
                «{redoExercise.name}»: {redoDoneSets - pendingRedo.setIndex > 1
                  ? `этот и следующие подходы (всего ${redoDoneSets - pendingRedo.setIndex}) будут выполнены заново, их прежние результаты удалятся.`
                  : 'подход будет выполнен заново, его прежний результат удалится.'} Остальные результаты тренировки сохранятся.
              </Dialog.Description>
              {error ? <p className="mt-3 text-sm text-[#ffb4a7]" role="alert">{error}</p> : null}
              <div className="builder-dialog-actions">
                <Button variant="secondary" disabled={busy} onClick={() => { setPendingRedo(null); setError(null) }}>Назад к списку</Button>
                <Button disabled={busy} iconLeft={<RotateCcw aria-hidden="true" />} onClick={() => void jump(pendingRedo.exerciseId, pendingRedo.setIndex)}>
                  {busy ? 'Переходим…' : 'Повторить'}
                </Button>
              </div>
            </>
          ) : (
            <>
              <Dialog.Title className="font-display text-3xl font-bold">Упражнения тренировки</Dialog.Title>
              <Dialog.Description className="mt-2 text-sm text-white/70">
                Выполнено {doneExercises} из {progress.length}. Нажмите на упражнение, чтобы перейти к его следующему подходу, или на номер подхода, чтобы повторить его.
              </Dialog.Description>
              {error ? <p className="mt-3 text-sm text-[#ffb4a7]" role="alert">{error}</p> : null}
              <ol className="rt-nav-list" aria-label="Упражнения тренировки">
                {progress.map((item) => {
                  const canOpen = item.nextSetIndex != null && item.sets[item.nextSetIndex]?.available
                  return (
                    <li key={item.exercise.id} className="rt-nav-item" data-status={item.status} aria-current={item.status === 'current' ? 'step' : undefined}>
                      <button
                        type="button"
                        className="rt-nav-exercise"
                        disabled={busy || !canOpen}
                        aria-label={`${item.exercise.name}: ${statusText[item.status].toLowerCase()}, ${item.doneSets} из ${item.totalSets}${canOpen ? '. Перейти к следующему подходу' : ''}`}
                        onClick={() => item.nextSetIndex != null && openSet(item, item.nextSetIndex)}
                      >
                        <span className="rt-nav-icon" aria-hidden="true">
                          {item.status === 'done' ? <CheckCircle2 /> : item.status === 'skipped' ? <SkipForward /> : item.status === 'current' ? <Play /> : item.status === 'partial' ? <CircleDashed /> : item.exercise.order}
                        </span>
                        <span className="rt-nav-name">
                          <strong>{item.exercise.name}</strong>
                          <span>
                            {statusText[item.status]} · {item.status === 'pending' ? setsLabel(item.totalSets) : `${item.doneSets} из ${item.totalSets}`}
                            {item.status === 'current' ? ` · ${describeWorkoutSet(item.exercise, item.sets.find((set) => set.status === 'current')?.index ?? item.doneSets)}` : ''}
                          </span>
                        </span>
                      </button>
                      <div className="rt-nav-sets" role="group" aria-label={`Подходы: ${item.exercise.name}`}>
                        {item.sets.map((set) => (
                          <button
                            key={set.index}
                            type="button"
                            className="rt-nav-set"
                            data-status={set.status}
                            disabled={busy || !set.available}
                            aria-label={`${describeWorkoutSet(item.exercise, set.index)}: ${
                              set.status === 'current' ? 'сейчас' : set.redo ? 'повторить' : set.available ? 'перейти' : 'ещё не доступен'
                            }`}
                            onClick={() => openSet(item, set.index)}
                          >
                            {set.label}
                          </button>
                        ))}
                      </div>
                    </li>
                  )
                })}
              </ol>
              <div className="rt-nav-legend" aria-hidden="true">
                <span data-status="done">выполнено</span>
                <span data-status="partial">частично</span>
                <span data-status="current">сейчас</span>
                <span data-status="skipped">пропущено</span>
              </div>
              <div className="builder-dialog-actions">
                <Dialog.Close asChild><Button variant="secondary" disabled={busy}>Закрыть</Button></Dialog.Close>
              </div>
            </>
          )}
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
