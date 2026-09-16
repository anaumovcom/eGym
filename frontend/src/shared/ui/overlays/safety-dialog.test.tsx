import * as Dialog from '@radix-ui/react-dialog'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode, type ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { machineScenarios } from '@/mocks/data'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { useHardwareStore } from '@/stores/hardware-store'

const stopName = 'Аварийная остановка'
const originalHardwareState = useHardwareStore.getState()
const hardwareCommand = vi.fn()
const fetchMock = vi.fn().mockRejectedValue(new Error('Network is forbidden in this UI test'))

function TestDialog({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger>Открыть {title}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay />
        <SafetyDialogContent>
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description>Проверка доступности без оборудования</Dialog.Description>
          {children}
          <Dialog.Close>Закрыть {title}</Dialog.Close>
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function renderShell(nested = false) {
  const onStop = vi.fn()
  const view = render(
    <StrictMode>
      <MemoryRouter>
        <FormaShell userName="Алексей" machine={machineScenarios.ready} onStop={onStop}>
          <TestDialog title="Карточка">
            {nested ? <TestDialog title="Подтверждение" /> : null}
          </TestDialog>
        </FormaShell>
      </MemoryRouter>
    </StrictMode>,
  )
  return { ...view, onStop }
}

function expectSingleStop(dialog?: HTMLElement) {
  // Include hidden controls so a duplicate left behind in the inert shell fails too.
  expect(screen.getAllByRole('button', { name: stopName, exact: true, hidden: true })).toHaveLength(1)
  const stop = screen.getByRole('button', { name: stopName, exact: true })
  expect(stop).toBeVisible()
  expect(stop).toBeEnabled()
  expect(stop.closest('[role="dialog"]')).toBe(dialog ?? null)
  if (dialog) expect(within(dialog).getByRole('button', { name: stopName })).toBe(stop)
  else expect(stop.closest('.forma-shell')).not.toBeNull()
  expect(stop.closest('.forma-system-dock')).not.toBeNull()
  return stop
}

beforeEach(() => {
  hardwareCommand.mockClear()
  fetchMock.mockClear()
  vi.stubGlobal('fetch', fetchMock)
  useHardwareStore.setState({ snapshot: null, runCommand: hardwareCommand })
})

afterEach(() => {
  cleanup()
  useHardwareStore.setState(originalHardwareState, true)
  vi.unstubAllGlobals()
  expect(hardwareCommand).not.toHaveBeenCalled()
  expect(fetchMock).not.toHaveBeenCalled()
})

describe('SafetyDialogContent with FormaShell', () => {
  it('moves the single STOP into the real Radix dialog and restores the shell dock after closing', async () => {
    const user = userEvent.setup()
    const { onStop } = renderShell()
    expectSingleStop()

    await user.click(screen.getByRole('button', { name: 'Открыть Карточка' }))
    const dialog = screen.getByRole('dialog', { name: 'Карточка' })
    expect(onStop).not.toHaveBeenCalled()
    await user.click(expectSingleStop(dialog))
    expect(onStop).toHaveBeenCalledOnce()
    expect(dialog).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Закрыть Карточка' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expectSingleStop()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Открыть Карточка' })).toHaveFocus())
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('reaches STOP with Tab inside the modal focus scope and invokes only the supplied mock with Enter', async () => {
    const user = userEvent.setup()
    const { onStop } = renderShell()
    await user.click(screen.getByRole('button', { name: 'Открыть Карточка' }))
    const dialog = screen.getByRole('dialog', { name: 'Карточка' })
    const stop = expectSingleStop(dialog)
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Закрыть Карточка' })).toHaveFocus())

    for (let index = 0; index < 5 && document.activeElement !== stop; index += 1) {
      await user.tab()
      expect(dialog).toContainElement(document.activeElement as HTMLElement)
    }
    expect(stop).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(onStop).toHaveBeenCalledOnce()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expectSingleStop()
  })

  it('keeps STOP only in the topmost nested dialog and restores each previous dock', async () => {
    const user = userEvent.setup()
    const { onStop } = renderShell(true)
    await user.click(screen.getByRole('button', { name: 'Открыть Карточка' }))
    const outerDialog = screen.getByRole('dialog', { name: 'Карточка' })
    expectSingleStop(outerDialog)

    await user.click(within(outerDialog).getByRole('button', { name: 'Открыть Подтверждение' }))
    const innerDialog = screen.getByRole('dialog', { name: 'Подтверждение' })
    await user.click(expectSingleStop(innerDialog))
    expect(within(outerDialog).queryByRole('button', { name: stopName, hidden: true })).not.toBeInTheDocument()
    expect(onStop).toHaveBeenCalledOnce()

    await user.click(within(innerDialog).getByRole('button', { name: 'Закрыть Подтверждение' }))
    await waitFor(() => expect(innerDialog).not.toBeInTheDocument())
    expectSingleStop(outerDialog)
    await user.click(expectSingleStop(outerDialog))
    expect(onStop).toHaveBeenCalledTimes(2)

    await user.click(within(outerDialog).getByRole('button', { name: 'Закрыть Карточка' }))
    await waitFor(() => expect(outerDialog).not.toBeInTheDocument())
    expectSingleStop()
  })
})