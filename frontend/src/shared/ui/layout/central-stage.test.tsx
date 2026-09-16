import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { CentralStage } from '@/shared/ui/layout/central-stage'

afterEach(cleanup)

describe('CentralStage disclosure', () => {
  it('keeps primary content visible and toggles secondary content with accessible keyboard disclosure', async () => {
    const user = userEvent.setup()
    render(
      <CentralStage secondaryLabel="Подробности" secondary={<button>Дополнительное действие</button>}>
        <h1>Основное действие</h1>
      </CentralStage>,
    )
    const toggle = screen.getByRole('button', { name: 'Подробности' })
    const panel = document.getElementById(toggle.getAttribute('aria-controls')!)!
    expect(panel).toHaveAttribute('hidden')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('heading', { name: 'Основное действие' })).toBeVisible()
    expect(screen.queryByRole('complementary', { name: 'Подробности' })).not.toBeInTheDocument()
    expect(screen.queryByText('Дополнительное действие')).not.toBeInTheDocument()

    await user.tab()
    expect(toggle).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('complementary', { name: 'Подробности' })).toBe(panel)
    expect(panel).toBeVisible()
    expect(screen.getByRole('button', { name: 'Дополнительное действие' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Основное действие' })).toBeVisible()

    await user.tab()
    expect(screen.getByRole('button', { name: 'Дополнительное действие' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(toggle).toHaveFocus()
    await user.keyboard(' ')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(panel).toHaveAttribute('hidden')
    expect(screen.queryByText('Дополнительное действие')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Основное действие' })).toBeVisible()

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: 'Дополнительное действие' })).toBeVisible()
  })
})