import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { buildSystemSettingsData, defaultStage4DevFlags } from '@/mocks/stage4-data'
import { ModbusDebugScreen } from '@/screens/modbus-debug/modbus-debug-screen'
import { SystemSettingsScreen } from '@/screens/settings/system-settings-screen'
import { SettingsLayout } from '@/shared/ui/layout/service-access'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useStage4Store } from '@/stores/stage4-store'

const originalAppState = useAppStore.getState()
const originalHardwareState = useHardwareStore.getState()
const originalStage4State = useStage4Store.getState()
const originalModbusState = useModbusStore.getState()
const runCommand = vi.fn().mockResolvedValue({})
const loadSettings = vi.fn()
const loadPorts = vi.fn().mockResolvedValue(undefined)
const loadStatus = vi.fn().mockResolvedValue(undefined)
let queryClient: QueryClient

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderSettings(initialEntry = '/settings?tab=overview') {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LocationProbe />
        <Routes>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<SystemSettingsScreen />} />
            <Route path="service/modbus" element={<Navigate to="/modbus" replace />} />
          </Route>
          <Route path="/modbus" element={<ModbusDebugScreen />} />
          <Route path="/dashboard" element={<Link to="/settings?tab=service">Вернуться в настройки</Link>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function confirmAccess(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('checkbox', { name: 'Понимаю риски изменения технических настроек' }))
  await user.click(screen.getByRole('button', { name: 'Открыть сервисный раздел' }))
}

function expectNormalTabs() {
  const nav = screen.getByRole('navigation', { name: 'Настройки' })
  expect(within(nav).getAllByRole('button').map((button) => button.textContent)).toEqual(['Обзор', 'Безопасность', 'Общие', 'Сервис'])
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))
  localStorage.clear()
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  useStage4Store.setState(originalStage4State, true)
  useStage4Store.getState().resetDevFlags()
  const settings = buildSystemSettingsData(defaultStage4DevFlags)
  loadSettings.mockReset().mockResolvedValue(settings)
  runCommand.mockClear()
  loadPorts.mockClear()
  loadStatus.mockClear()
  useHardwareStore.setState({ settings, snapshot: null, errorMessage: null, loadSettings, runCommand })
  useModbusStore.setState({ ...originalModbusState, loadPorts, loadStatus }, true)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(() => {
  cleanup()
  queryClient.clear()
  useAppStore.setState(originalAppState, true)
  useHardwareStore.setState(originalHardwareState, true)
  useStage4Store.setState(originalStage4State, true)
  useModbusStore.setState(originalModbusState, true)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('System settings service access', () => {
  it.each(['overview', 'safety', 'common'])('keeps normal %s settings available without acknowledgement', async (tab) => {
    renderSettings(`/settings?tab=${tab}`)
    expectNormalTabs()
    expect(screen.queryByRole('checkbox', { name: 'Понимаю риски изменения технических настроек' })).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Сервисные настройки' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('main')).queryByRole('link', { name: 'Modbus Debug', exact: true })).not.toBeInTheDocument()
    expect(runCommand).not.toHaveBeenCalled()
    if (tab === 'common') {
      expect(screen.getByRole('region', { name: 'AI-тренер' })).toBeInTheDocument()
      await screen.findByText(/Сервер Coach недоступен/)
    }
    else expect(screen.queryByRole('region', { name: 'AI-тренер' })).not.toBeInTheDocument()
  })

  it('replaces technical overview actions with one link to the service gate', async () => {
    const user = userEvent.setup()
    renderSettings()
    expect(screen.queryByRole('button', { name: 'Запустить диагностику', exact: true })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Открыть журнал', exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Открыть сервисный раздел' })).toHaveAttribute('href', '/settings?tab=service')
    await user.click(screen.getByRole('link', { name: 'Открыть сервисный раздел' }))
    expect(screen.getByRole('button', { name: 'Открыть сервисный раздел' })).toBeDisabled()
    expect(runCommand).not.toHaveBeenCalled()
  })

  it.each([
    ['mechanics', 'Механика готова к работе'],
    ['diagnostics', 'Диагностика завершена успешно'],
    ['calibrations', 'Сохранённые калибровки'],
    ['service', 'Текущие позиции'],
    ['journal', 'Журнал событий'],
  ])('gates direct %s URLs even when mock service state is unlocked', async (tab, panelText) => {
    const user = userEvent.setup()
    expect(useHardwareStore.getState().settings?.service.unlocked).toBe(true)
    renderSettings(`/settings?tab=${tab}&unlocked=true&serviceMode=true`)
    expectNormalTabs()
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveLength(1)
    expect(screen.queryByText(panelText)).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Сервисные настройки' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Запустить полную диагностику' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Выключить сервисный режим/ })).not.toBeInTheDocument()
    await confirmAccess(user)

    expect(screen.getAllByText(panelText)[0]).toBeVisible()
    expect(within(screen.getByRole('navigation', { name: 'Сервисные настройки' })).getAllByRole('button').map((button) => button.textContent)).toEqual(['Приводы и ШВП', 'Диагностика', 'Калибровки', 'Сервис', 'Журнал'])
    expect(screen.getByTestId('location')).toHaveTextContent(`/settings?tab=${tab}&unlocked=true&serviceMode=true`)
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('cancels a direct diagnostic URL to overview without a hardware command', async () => {
    const user = userEvent.setup()
    renderSettings('/settings?tab=diagnostics')
    await user.click(screen.getByRole('link', { name: 'Отмена — к настройкам' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/settings?tab=overview')
    expectNormalTabs()
    expect(screen.queryByRole('button', { name: 'Запустить полную диагностику' })).not.toBeInTheDocument()
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('runs diagnostics only on its separate command button after UI confirmation', async () => {
    const user = userEvent.setup()
    renderSettings('/settings?tab=diagnostics')
    await confirmAccess(user)
    expect(runCommand).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Запустить полную диагностику' }))
    expect(runCommand).toHaveBeenCalledExactlyOnceWith({ action: 'run_diagnostics', userId: 'alexey' })
  })

  it('keeps acknowledgement independent of live service mode and preserves command parameters', async () => {
    const user = userEvent.setup()
    const snapshot: HardwareSnapshot = {
      eventType: 'snapshot', emittedAt: '2026-09-15T10:00:00Z',
      machine: { machineState: 'ready', machineLabel: 'Готово', safety: 'enabled', leftDrive: 'connected', rightDrive: 'connected', calibration: 'Актуальна' },
      safety: { state: 'enabled', label: 'Готово', message: '', requiresService: false, activeEventId: null },
      emulatorMode: true, serviceMode: true, selectedUserId: 'alexey', userSelected: true, drives: [],
      motion: { moving: false, motionProfile: 'service', barPositionMm: 0, leftPositionMm: 0, rightPositionMm: 0, syncDeltaMm: 0, amplitudePercent: 0, tempoLabel: '—', repetitionCount: 0, currentSet: 0, targetSet: 0, targetReps: 0, direction: 'stopped' },
      calibrationRequired: false, calibrationActual: true, activeCalibrationId: null, commandQueueDepth: 0,
      lastCommand: null, diagnosticsStatus: 'idle', lastDiagnosticsAt: null, alerts: [],
    }
    const settings = buildSystemSettingsData(defaultStage4DevFlags)
    useHardwareStore.setState({
      snapshot,
      settings: { ...settings, service: { ...settings.service, actions: [{ title: 'Homing', description: 'Возврат в исходное положение' }] } },
    })
    renderSettings('/settings?tab=service')
    expect(screen.getByRole('button', { name: 'Открыть сервисный раздел' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Выключить сервисный режим/ })).not.toBeInTheDocument()
    act(() => { useHardwareStore.setState({ snapshot: { ...snapshot, serviceMode: false } }) })
    await confirmAccess(user)
    expect(runCommand).not.toHaveBeenCalled()
    expect(useHardwareStore.getState().snapshot?.serviceMode).toBe(false)
    await user.click(screen.getByRole('button', { name: /^Homing/ }))
    expect(runCommand).toHaveBeenLastCalledWith({ action: 'home', userId: 'alexey', serviceMode: false })
    await user.click(screen.getByRole('button', { name: 'Включить сервисный режим' }))
    expect(runCommand).toHaveBeenLastCalledWith({ action: 'toggle_service_mode', userId: 'alexey', serviceMode: true })
  })

  it('links the service section to the standalone Modbus page in the main header', async () => {
    const user = userEvent.setup()
    renderSettings('/settings?tab=service')
    expect(loadPorts).not.toHaveBeenCalled()
    expect(loadStatus).not.toHaveBeenCalled()
    await confirmAccess(user)
    await user.click(within(screen.getByRole('navigation', { name: 'Настройки' })).getByRole('button', { name: 'Обзор' }))
    await user.click(screen.getByRole('link', { name: 'Открыть сервисный раздел' }))
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()

    const link = within(screen.getByRole('region', { name: 'Сервисный раздел' })).getByRole('link', { name: 'Modbus Debug' })
    expect(link).toHaveAttribute('href', '/modbus')
    expect(within(screen.getByRole('navigation', { name: 'Основная навигация' })).getByRole('link', { name: 'Modbus' })).toHaveAttribute('href', '/modbus')
    await user.click(link)
    expect(screen.getByRole('heading', { name: /Lichuan A6/ })).toBeVisible()
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveLength(1)
    expect(loadPorts).toHaveBeenCalledTimes(1)
    expect(loadStatus).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('location')).toHaveTextContent('/modbus')
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('redirects the legacy nested Modbus URL to the standalone page', () => {
    renderSettings('/settings/service/modbus')
    expect(screen.getByTestId('location')).toHaveTextContent('/modbus')
    expect(screen.getByRole('heading', { name: /Lichuan A6/ })).toBeVisible()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(runCommand).not.toHaveBeenCalled()
  })
})