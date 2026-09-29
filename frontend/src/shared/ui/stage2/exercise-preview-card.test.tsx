import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ExerciseSummary } from '@/entities/exercise/model/types'
import { ExercisePreviewCard } from '@/shared/ui/stage2/screen-components'

const exercise: ExerciseSummary = {
  slug: 'test-exercise',
  name: 'Тестовое упражнение',
  secondaryName: 'Test exercise',
  equipment: 'Без оборудования',
  difficulty: 'Beginner',
  force: 'Stretch',
  grips: 'Без хвата',
  mechanic: 'Mobility',
  muscles: ['Пресс'],
  favorite: false,
  blacklisted: false,
  recommended: false,
  compatibilityTone: 'okay',
  readinessStatus: 'ready',
  difficultyLabel: 'Начальный',
  badges: [],
}

describe('ExercisePreviewCard', () => {
  it('opens from the card surface but not from the favorite button', () => {
    const onOpen = vi.fn()
    const onFavorite = vi.fn()
    render(<ExercisePreviewCard exercise={exercise} onOpen={onOpen} onFavorite={onFavorite} />)

    const card = screen.getByRole('article', { name: exercise.name })
    expect(card).not.toHaveTextContent('Можно выполнять')
    expect(card).not.toHaveTextContent('Открыть')

    fireEvent.click(screen.getByRole('button', { name: `Добавить в избранное: ${exercise.name}` }))
    expect(onFavorite).toHaveBeenCalledOnce()
    expect(onOpen).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: `Открыть ${exercise.name}` }))
    expect(onOpen).toHaveBeenCalledOnce()
  })
})