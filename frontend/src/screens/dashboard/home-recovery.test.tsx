import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HomeRecovery } from './home-recovery'
import type { MuscleCard } from '@/entities/muscle/model/types'
import type { CompactBodyMapGrid } from '@/shared/ui/stage2/screen-components'

vi.mock('@/shared/ui/stage2/screen-components', () => ({
  CompactBodyMapGrid: ({ figureGender, highlights, onHighlightHover, plainFigures, showFigureTitles }: ComponentProps<typeof CompactBodyMapGrid>) => (
    <div data-testid="map" data-gender={figureGender} data-plain={plainFigures} data-titles={showFigureTitles}>
      {highlights.map(({ label, tone, description }) => (
        <button key={label} type="button" aria-label={description}
          onPointerEnter={() => onHighlightHover?.({ label, tone, anchor: { top: 40, left: 100 } })}
          onFocus={() => onHighlightHover?.({ label, tone })}
          onClick={() => onHighlightHover?.({ label, tone })}
          onPointerLeave={() => onHighlightHover?.(null)} onBlur={() => onHighlightHover?.(null)}>
          {label}
        </button>
      ))}
    </div>
  ),
}))

function show(muscles: MuscleCard[], gender: 'male' | 'female' = 'male') {
  return render(<HomeRecovery muscles={muscles} figureGender={gender} />)
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('HomeRecovery', () => {
  it('always shows the map with all supplied descriptions, without a summary or dialog', () => {
    const muscles: MuscleCard[] = [
      { name: 'Спина', score: 0, status: 'no_data' }, { name: 'Икры', score: 10, status: 'ready' },
      { name: 'Грудь', score: 150, status: 'critical' }, { name: 'Бицепс', score: 80, status: 'high' },
      { name: 'Пресс', score: 40, status: 'medium' },
    ]
    const original = structuredClone(muscles)
    show(muscles)
    expect(screen.getByTestId('map')).toBeVisible()
    expect(screen.getByTestId('map')).toHaveAttribute('data-gender', 'male')
    expect(screen.getByTestId('map')).toHaveAttribute('data-plain', 'true')
    expect(screen.getByTestId('map')).toHaveAttribute('data-titles', 'false')
    for (const name of ['Спина: Нет данных', 'Икры: Готова к нагрузке, 10 балл.', 'Грудь: Перегрузка, 150 балл.', 'Бицепс: Высокая усталость, 80 балл.', 'Пресс: Умеренная усталость, 40 балл.']) {
      expect(screen.getByRole('button', { name, exact: true })).toBeVisible()
    }
    expect(screen.getByText('Наведите на мышцу')).toBeVisible()
    expect(screen.queryByRole('list', { name: 'Краткая сводка усталости' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Карта мышц', exact: true })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(muscles).toEqual(original)
  })

  it.each([{ muscles: [] }, { muscles: [{ name: 'Грудь', score: 150, status: 'no_data' as const }] }])('shows missing data without any score, including placeholder regions: $muscles', async ({ muscles }) => {
    const user = userEvent.setup()
    show(muscles)
    expect(screen.getByText('Пока нет данных о нагрузке')).toBeVisible()
    expect(screen.getByTestId('map')).toBeVisible()
    await user.hover(screen.getByRole('button', { name: 'Грудь: Нет данных', exact: true }))
    const tooltip = within(screen.getByRole('tooltip'))
    expect(tooltip.getByText('Грудь', { exact: true })).toBeVisible()
    expect(tooltip.getByText('Нет данных', { exact: true })).toBeVisible()
    expect(tooltip.getByText('Нет сохранённых данных о нагрузке')).toBeVisible()
    expect(tooltip.queryByText(/балл|150|^0$/)).not.toBeInTheDocument()
    expect(tooltip.queryByText('Готова к нагрузке')).not.toBeInTheDocument()
    expect(screen.queryByText(/мышцы готовы/)).not.toBeInTheDocument()
  })

  it('shows name, status and an uncapped score on hover and hides exactly 120ms after leave', () => {
    vi.useFakeTimers()
    show([{ name: 'Грудь', score: 150, status: 'critical' }])
    const region = screen.getByRole('button', { name: 'Грудь: Перегрузка, 150 балл.' })
    fireEvent.pointerEnter(region)
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveAttribute('data-tone', 'critical')
    expect(within(tooltip).getByText('Грудь', { exact: true })).toBeVisible()
    expect(within(tooltip).getByText('Перегрузка', { exact: true })).toBeVisible()
    expect(within(tooltip).getByText('150', { exact: true })).toHaveTextContent('150 балл. усталости')
    fireEvent.pointerLeave(region)
    act(() => vi.advanceTimersByTime(119))
    expect(tooltip).toBeVisible()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('cancels pending hide when entering the tooltip or another muscle', () => {
    vi.useFakeTimers()
    show([{ name: 'Грудь', score: 150, status: 'critical' }, { name: 'Икры', score: 10, status: 'ready' }])
    const chest = screen.getByRole('button', { name: /^Грудь:/ })
    fireEvent.pointerEnter(chest)
    fireEvent.pointerLeave(chest)
    act(() => vi.advanceTimersByTime(119))
    fireEvent.pointerEnter(screen.getByRole('tooltip'))
    act(() => vi.advanceTimersByTime(120))
    expect(screen.getByRole('tooltip')).toBeVisible()
    fireEvent.pointerLeave(screen.getByRole('tooltip'))
    fireEvent.pointerEnter(screen.getByRole('button', { name: /^Икры:/ }))
    act(() => vi.advanceTimersByTime(120))
    expect(within(screen.getByRole('tooltip')).getByText('Икры', { exact: true })).toBeVisible()
    expect(within(screen.getByRole('tooltip')).getByText('10', { exact: true })).toBeVisible()
    fireEvent.pointerLeave(screen.getByRole('tooltip'))
    act(() => vi.advanceTimersByTime(120))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('shows the tooltip on focus and click, closes on Escape and keeps focus without opening a dialog', async () => {
    const user = userEvent.setup()
    show([{ name: 'Грудь', score: 150, status: 'critical' }], 'female')
    expect(screen.getByTestId('map')).toHaveAttribute('data-gender', 'female')
    const region = screen.getByRole('button', { name: /^Грудь:/ })
    act(() => region.focus())
    expect(within(screen.getByRole('tooltip')).getByText('150', { exact: true })).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(region).toHaveFocus()
    fireEvent.click(region)
    expect(screen.getByRole('tooltip')).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(region).toHaveFocus()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByTestId('map')).toBeVisible()
  })

  it('hides 120ms after blur and clears pending hide on Escape', () => {
    vi.useFakeTimers()
    show([{ name: 'Грудь', score: 150, status: 'critical' }])
    const region = screen.getByRole('button', { name: /^Грудь:/ })
    act(() => region.focus())
    act(() => region.blur())
    act(() => vi.advanceTimersByTime(119))
    expect(screen.getByRole('tooltip')).toBeVisible()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    act(() => region.focus())
    fireEvent.pointerLeave(region)
    fireEvent.keyDown(region, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.click(region)
    act(() => vi.advanceTimersByTime(120))
    expect(screen.getByRole('tooltip')).toBeVisible()
  })

  it('updates the hovered muscle, descriptions and gender without mutating either input', async () => {
    const user = userEvent.setup()
    const muscles: MuscleCard[] = [{ name: 'Грудь', score: 150, status: 'critical' }]
    const updated: MuscleCard[] = [{ name: 'Грудь', score: 35, status: 'light' }]
    const originals = structuredClone([muscles, updated])
    const { rerender } = show(muscles)
    await user.hover(screen.getByRole('button', { name: /^Грудь:/ }))
    rerender(<HomeRecovery muscles={updated} figureGender="female" />)
    expect(screen.getByTestId('map')).toHaveAttribute('data-gender', 'female')
    expect(screen.getByRole('button', { name: 'Грудь: Лёгкая усталость, 35 балл.' })).toBeVisible()
    expect(screen.getByRole('tooltip')).toHaveAttribute('data-tone', 'light')
    expect(within(screen.getByRole('tooltip')).getByText('Лёгкая усталость', { exact: true })).toBeVisible()
    expect(within(screen.getByRole('tooltip')).getByText('35', { exact: true })).toBeVisible()
    expect(within(screen.getByRole('tooltip')).queryByText(/150|Перегрузка/)).not.toBeInTheDocument()
    rerender(<HomeRecovery muscles={[]} />)
    expect(screen.getByTestId('map')).toHaveAttribute('data-gender', 'male')
    expect(screen.getByRole('button', { name: 'Грудь: Нет данных', exact: true })).toBeVisible()
    expect(screen.getByRole('tooltip')).toHaveAttribute('data-tone', 'no_data')
    expect(within(screen.getByRole('tooltip')).queryByText(/балл|35|150/)).not.toBeInTheDocument()
    expect([muscles, updated]).toEqual(originals)
  })
})