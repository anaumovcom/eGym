import { useEffect, useRef } from 'react'
import { useStage4Store } from '@/stores/stage4-store'

type ExerciseSound = 'upper' | 'lower' | 'error' | 'success'
const sources: Record<ExerciseSound, string> = {
  upper: '/audio/pop-up.mp3',
  lower: '/audio/pop-down.mp3',
  error: '/audio/error-notification.mp3',
  success: '/audio/success.mp3',
}

/** Sound failure must never interrupt the exercise or create another error notification. */
export function playExerciseEventSound(kind: ExerciseSound) {
  const settings = useStage4Store.getState().settingsSaved
  const volume = Math.min(1, Math.max(0, Number(String(settings.signalVolume).replace('%', '')) / 100))
  if (!settings.soundEnabled || !Number.isFinite(volume) || volume === 0 || typeof Audio === 'undefined') return
  try {
    const audio = new Audio(sources[kind])
    audio.volume = volume
    void audio.play().catch(() => undefined)
  } catch {
    // Autoplay restrictions and unavailable audio devices are non-fatal.
  }
}

export function useExerciseEventSounds(scope: string, position: 'upper' | 'lower' | 'neutral' | null, problems: string[], partialReps: number) {
  const previous = useRef<{ scope: string; position: typeof position; problems: Set<string>; partialReps: number } | null>(null)
  const problemsKey = JSON.stringify([...new Set(problems)].sort())
  useEffect(() => {
    const old = previous.current?.scope === scope ? previous.current : null
    const currentProblems = new Set<string>(JSON.parse(problemsKey))
    const newProblem = [...currentProblems].some(problem => !old?.problems.has(problem))
      || (old !== null && partialReps > old.partialReps)
    // Initial telemetry establishes a baseline, not a new arrival at an endpoint.
    if (newProblem) playExerciseEventSound('error')
    else if (old && position && position !== 'neutral' && position !== old.position) playExerciseEventSound(position)
    previous.current = { scope, position, problems: currentProblems, partialReps }
  }, [scope, position, problemsKey, partialReps])
}