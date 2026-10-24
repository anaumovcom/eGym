import { Check } from 'lucide-react'
import type { RuntimeExercisePlan, RuntimeSetPlan, RuntimeSetResult } from '@/entities/runtime/model/types'
import { formatTimedSeconds } from '@/features/runtime/lib/timed-set'

const setTypeLabels: Record<string, string> = { warmup: 'Разминка', work: 'Рабочий', failure: 'До отказа' }

function formatKg(value: number) {
  return `${value.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} кг`
}

/** "10–12" / "12" / "60 сек" — what one set asks for. */
export function formatSetTarget(plan: RuntimeSetPlan) {
  if (plan.targetSeconds) return formatTimedSeconds(plan.targetSeconds)
  if (plan.targetMinReps && plan.targetMaxReps && plan.targetMinReps !== plan.targetMaxReps) return `${plan.targetMinReps}–${plan.targetMaxReps}`
  return String(plan.targetMaxReps ?? plan.targetReps ?? plan.targetMinReps ?? '—')
}

/** Planned weight of a set, or null for bodyweight/timed work. */
export function setWeightKg(plan: RuntimeSetPlan) {
  return plan.recommendedWeightKg && plan.recommendedWeightKg > 0 ? plan.recommendedWeightKg : null
}

/** One-line description of a planned set: "12 × 15 кг" or "60 сек". */
export function describeSetPlan(plan: RuntimeSetPlan) {
  const weight = setWeightKg(plan)
  return weight ? `${formatSetTarget(plan)} × ${formatKg(weight)}` : formatSetTarget(plan)
}

/** Warm-ups are "Р"; work sets are numbered on their own, per-side sets add "Л"/"П". */
function setBadge(plan: RuntimeSetPlan, workIndex: number) {
  if (plan.setType === 'warmup') return 'Р'
  const number = plan.roundNumber ?? workIndex
  return plan.side ? `${number}${plan.side === 'left' ? 'Л' : 'П'}` : String(number)
}

function resultLabel(result: RuntimeSetResult, plan: RuntimeSetPlan) {
  if (result.completionStatus === 'skipped') return 'пропущен'
  const value = plan.targetSeconds ? formatTimedSeconds(result.actualValue) : String(result.reps ?? result.actualValue)
  return result.weightKg ? `${value} × ${formatKg(result.weightKg)}` : value
}

/**
 * Every set of the exercise in order: done sets show what was actually done,
 * the current one is highlighted, the rest show their target.
 */
export function SetPlanTrack({ exercise, currentIndex, results = [], label = 'План подходов' }: {
  exercise: Pick<RuntimeExercisePlan, 'plan'>
  currentIndex: number
  results?: RuntimeSetResult[]
  label?: string
}) {
  let workIndex = 0
  return (
    <ol className="rt-set-track" aria-label={label}>
      {exercise.plan.map((plan, index) => {
        if (plan.setType !== 'warmup' && (!plan.side || plan.side === 'left')) workIndex += 1
        const result = results.find((item) => item.setNumber === (plan.setNumber ?? index + 1)) ?? (index < currentIndex ? results[index] : undefined)
        const state = index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'next'
        const tone = result?.completionStatus === 'partial' ? 'partial' : result?.completionStatus === 'skipped' ? 'skipped' : undefined
        return (
          <li key={plan.setNumber ?? index} data-state={state} data-type={plan.setType ?? 'work'} data-tone={tone}
            aria-current={state === 'current' ? 'step' : undefined}>
            <span className="rt-set-badge" aria-hidden="true">{state === 'done' && !tone ? <Check /> : setBadge(plan, workIndex)}</span>
            <span className="rt-set-text">
              <span className="rt-set-type">{state === 'current' ? 'Сейчас' : setTypeLabels[plan.setType ?? 'work'] ?? 'Рабочий'}</span>
              <strong>{state === 'done' && result ? resultLabel(result, plan) : describeSetPlan(plan)}</strong>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
