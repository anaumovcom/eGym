import { render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { DashboardWorkoutMuscleLoad } from '@/entities/dashboard/model/types'
import type { CompactBodyMapGrid } from '@/shared/ui/stage2/screen-components'
import { WorkoutMuscleLoad } from '@/screens/dashboard/workout-muscle-load'

vi.mock('@/shared/ui/stage2/screen-components', () => ({
  CompactBodyMapGrid: ({ highlights }: ComponentProps<typeof CompactBodyMapGrid>) => (
    <div data-testid="map">{highlights.map((item) => <span key={item.label} data-tone={item.tone}>{item.label}</span>)}</div>
  ),
}))

const load = (patch: Partial<DashboardWorkoutMuscleLoad>): DashboardWorkoutMuscleLoad => ({
  name: 'Грудь', role: 'primary', addedScore: 20, currentScore: 5, projectedScore: 25,
  currentStatus: 'ready', projectedStatus: 'light', exercises: ['Жим'], ...patch,
})

describe('WorkoutMuscleLoad', () => {
  it('maps only the loaded muscles, coloured by fatigue after the workout', () => {
    render(<WorkoutMuscleLoad figureGender="male" muscles={[load({}), load({ name: 'Трицепс', role: 'secondary', currentScore: 10, projectedScore: 32, projectedStatus: 'medium' })]} />)
    const map = screen.getByTestId('map')
    expect(within(map).getAllByText(/./)).toHaveLength(2)
    expect(within(map).getByText('Трицепс')).toHaveAttribute('data-tone', 'medium')
    const list = screen.getByRole('list', { name: 'Мышцы, которые нагрузит тренировка' })
    expect(within(list).getByLabelText('Усталость сейчас 5, после тренировки 25')).toBeVisible()
    expect(within(list).getAllByText('основная')).toHaveLength(1)
    expect(screen.getByRole('note')).toHaveTextContent('Мышцы готовы.')
    expect(screen.getByText('Акцент:')).toHaveTextContent('Акцент: грудь')
  })

  it('warns about unrecovered and soon overloaded muscles', () => {
    render(<WorkoutMuscleLoad figureGender="male" muscles={[
      load({ name: 'Спина', currentScore: 70, currentStatus: 'high', projectedScore: 90, projectedStatus: 'high' }),
      load({ name: 'Бицепс', projectedScore: 65, projectedStatus: 'high' }),
    ]} />)
    const note = screen.getByRole('note')
    expect(note).toHaveTextContent('Ещё не восстановились: спина.')
    expect(note).toHaveTextContent('После тренировки будет высокая усталость: бицепс.')
    expect(note).not.toHaveTextContent('Мышцы готовы')
  })

  it('explains a workout without fatigue load', () => {
    render(<WorkoutMuscleLoad figureGender="male" muscles={[]} />)
    expect(screen.getByText('Упражнения этой тренировки не создают заметной усталости мышц.')).toBeVisible()
    expect(screen.queryByTestId('map')).not.toBeInTheDocument()
  })
})
