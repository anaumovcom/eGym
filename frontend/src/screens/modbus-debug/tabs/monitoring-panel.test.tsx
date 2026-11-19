import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import type { ModbusConnectionStatus } from '@/features/modbus/model/types'
import { apiGet } from '@/shared/api/client'
import { ErrorsPanel } from './errors-panel'
import { MonitoringPanel } from './monitoring-panel'

vi.mock('@/shared/api/client', () => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiDelete: vi.fn() }))

it('subscribes after late power, shares one cached frame, and clears stale feedback and alarms', async () => {
  const client = new QueryClient()
  const status: ModbusConnectionStatus = {
    connected: true, port: 'USB-test', baudRate: 115200, parity: 'E', slaveId: 1, rightSlaveId: 2, timeoutMs: 300,
    lastSuccessAt: null, okCount: 0, errorCount: 0, errorMessage: null, simulationMode: false,
  }
  useModbusStore.setState({ connectionStatus: null, selectedSide: 'left', driveAddresses: { left: 1, right: 2 } })
  const read = vi.mocked(apiGet)
  read.mockResolvedValueOnce({ slave_id: 1, alarm: 16, feedback_torque_raw: -143, read_at: '2026-11-18T12:00:00Z' })
      .mockResolvedValueOnce({ slave_id: 1, error: 'Кадр привода устарел' })
      .mockResolvedValue({ slave_id: 2, alarm: 0, feedback_torque_raw: 120 })
  const view = render(<QueryClientProvider client={client}><MonitoringPanel /><ErrorsPanel /></QueryClientProvider>)
  try {
    expect(screen.getByText('Ожидание подключения приводов')).toBeInTheDocument()
    expect(read).not.toHaveBeenCalled()
    act(() => useModbusStore.setState({ connectionStatus: status }))
    expect(await screen.findByText('Err 16')).toBeInTheDocument()
    expect(screen.getAllByText('-143').length).toBeGreaterThan(0)
    expect(read.mock.calls.map(([path]) => path)).toEqual(['/api/modbus/torque/telemetry?slave_id=1&cached=true'])
    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }))
    await waitFor(() => expect(screen.queryByText('Err 16')).not.toBeInTheDocument())
    expect(screen.queryByText('-143')).not.toBeInTheDocument()
    expect(screen.queryByText('Нет активных ошибок')).not.toBeInTheDocument()
    act(() => useModbusStore.getState().selectSide('right'))
    expect(await screen.findByText('Нет активных ошибок')).toBeInTheDocument()
    expect(read.mock.lastCall?.[0]).toBe('/api/modbus/torque/telemetry?slave_id=2&cached=true')
  } finally {
    view.unmount()
    client.clear()
  }
})
