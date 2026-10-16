import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { LoadDirectionSelector } from './load-direction-selector'

describe('LoadDirectionSelector', () => {
  it('defaults down and emits up, without implicitly selecting a start point', async () => {
    const onChange = vi.fn()
    render(<LoadDirectionSelector onChange={onChange} />)
    expect(screen.getByRole('button', { name: 'Нагрузка вниз' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Нагрузка вниз' }))
    expect(onChange).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Тяга вверх' }))
    expect(onChange).toHaveBeenCalledExactlyOnceWith('up')
  })
  it('explains upper start as a separate choice and blocks changes while saving', async () => {
    const onChange = vi.fn()
    render(<LoadDirectionSelector value="up" disabled nextSet onChange={onChange} />)
    expect(screen.getByText(/Начальное положение выбирается отдельно/)).toHaveTextContent('только со следующего подхода')
    await userEvent.click(screen.getByRole('button', { name: 'Нагрузка вниз' }))
    expect(onChange).not.toHaveBeenCalled()
  })
})