import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { PositionExercisePanel } from './position-exercise-panel'
import { enterPositionWeightless, fetchPositionStatus } from '@/features/modbus/api/modbus-api'

const mode = vi.hoisted(() => ({ connected: false, simulationMode: false }))

vi.mock('@/features/modbus/lib/use-modbus-store', () => ({
  useModbusStore: (selector: (state: object) => unknown) => selector({ connectionStatus: mode }),
}))
vi.mock('@/features/modbus/api/modbus-api', () => ({
  fetchPositionStatus: vi.fn(), fetchPositionCalibration: vi.fn().mockResolvedValue(null),
  enterPositionWeightless: vi.fn(), capturePositionCalibration: vi.fn(),
  changePositionLimit: vi.fn(), startPositionExercise: vi.fn(), stopRaisePosition: vi.fn(),
  holdPosition: vi.fn(), zeroModbusPositions: vi.fn(),
}))

describe('Position exercise safety UI', () => {
  beforeEach(() => { mode.connected = false; mode.simulationMode = false; vi.clearAllMocks() })
  it('shows both target settings and does not enable movement on real drives', () => {
    render(<MemoryRouter initialEntries={['/modbus?tab=position-exercise&exercise=bench-press']}><PositionExercisePanel /></MemoryRouter>)
    expect(screen.getByDisplayValue('bench-press')).toBeInTheDocument()
    expect(screen.getByText(/STOP выполняет управляемый подъём грифа вверх/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /STOP · подъём к 2000 мм/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Запустить упражнение/ })).toBeDisabled()
    expect(screen.getByText(/Цель из калибровки/)).toBeInTheDocument()
  })

  it('requires an entered motion threshold before weightless mode can be activated', async () => {
    mode.connected = true; mode.simulationMode = true
    const state = {
      state: 'idle', targetType: null, targetMm: null, torqueLimit: null, speedRpm: null,
      positions: { connected: true, zeroed: true, zeroGeneration: 1, readiness: { communicationReady: true },
        left: { positionMm: 0 }, right: { positionMm: 0 }, skewMm: 0 },
      drives: {}, servoOn: {}, posLoad: {}, warning: null, error: null, simulationOnly: true,
    }
    vi.mocked(fetchPositionStatus).mockResolvedValue(state as never)
    vi.mocked(enterPositionWeightless).mockResolvedValue({ ...state, state: 'weightless', targetType: 'weightless', targetMm: 2000, torqueLimit: 1 } as never)
    render(<MemoryRouter><PositionExercisePanel /></MemoryRouter>)
    const button = screen.getByRole('button', { name: 'Невесомый гриф (симуляция)' })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByRole('spinbutton', { name: /Измеренный порог движения/ }), { target: { value: '10' } })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    await waitFor(() => expect(enterPositionWeightless).toHaveBeenCalledWith(1, 10, 30))
  })
})
