import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RuntimeSetPlan, RuntimeSetResult } from '@/entities/runtime/model/types'
import { describeSetPlan, SetPlanTrack } from '@/features/runtime/ui/set-plan-track'

const set = (patch: Partial<RuntimeSetPlan>): RuntimeSetPlan => ({ weightLabel: '', restSeconds: 60, setType: 'work', targetReps: 12, recommendedWeightKg: 15, ...patch })
const plan = [set({ setNumber: 1, setType: 'warmup', targetMinReps: 10, targetMaxReps: 12, recommendedWeightKg: 8 }), set({ setNumber: 2 }), set({ setNumber: 3 })]

describe('SetPlanTrack', () => {
  it('describes reps, ranges, weight and timed sets', () => {
    expect(describeSetPlan(plan[0])).toBe('10–12 × 8 кг')
    expect(describeSetPlan(set({ recommendedWeightKg: 0 }))).toBe('12')
    expect(describeSetPlan(set({ targetSeconds: 60, recommendedWeightKg: undefined }))).toBe('1 мин')
  })

  it('shows done sets with their result, highlights the current one and numbers work sets apart from the warm-up', () => {
    const results: RuntimeSetResult[] = [{ setNumber: 1, plannedValue: 12, actualValue: 11, reps: 11, weightKg: 8, completionStatus: 'completed', tempoLabel: '' }]
    render(<SetPlanTrack exercise={{ plan }} currentIndex={1} results={results} />)
    const items = within(screen.getByRole('list', { name: 'План подходов' })).getAllByRole('listitem')
    expect(items.map((item) => item.dataset.state)).toEqual(['done', 'current', 'next'])
    expect(items[0]).toHaveTextContent('11 × 8 кг')
    expect(items[1]).toHaveAttribute('aria-current', 'step')
    expect(items[1]).toHaveTextContent('Сейчас12 × 15 кг')
    expect(items[1]).toHaveTextContent('1')
    expect(items[2]).toHaveTextContent('2Рабочий12 × 15 кг')
  })
})
