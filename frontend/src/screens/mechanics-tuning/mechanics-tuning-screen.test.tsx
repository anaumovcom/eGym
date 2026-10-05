import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { updateTuning } from '@/features/hardware/api/tuning-api'
import { fetchModbusPositions, zeroModbusPositions } from '@/features/modbus/api/modbus-api'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { MechanicsTuningScreen } from '@/screens/mechanics-tuning/mechanics-tuning-screen'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'

vi.mock('@/features/modbus/api/modbus-api', () => ({
  fetchModbusPositions: vi.fn(),
  zeroModbusPositions: vi.fn(),
}))

vi.mock('@/features/hardware/api/tuning-api', () => ({
  fetchTuningSchema: vi.fn().mockResolvedValue({
    groups: [{ id: 'compensation', label: 'Компенсации', description: '' }, { id: 'homing', label: 'Поиск границ', description: '' }],
    parameters: [
      { key: 'compensation.barMassKg', group: 'compensation', label: 'Масса грифа', description: 'Масса грифа', type: 'number', default: 20, unit: 'кг', min: 0, max: 80, hardMin: 0, hardMax: 80, step: 0.1, options: [], requiresRestart: false, safetyCritical: false },
      { key: 'compensation.gravityEnabled', group: 'compensation', label: 'Компенсация веса', description: '', type: 'boolean', default: true, unit: '', min: null, max: null, hardMin: null, hardMax: null, step: null, options: [], requiresRestart: false, safetyCritical: false },
      { key: 'homing.limitSwitchesEnabled', group: 'homing', label: 'Концевые датчики установлены', description: 'Требуется перезапуск.', type: 'boolean', default: true, unit: '', min: null, max: null, hardMin: null, hardMax: null, step: null, options: [], requiresRestart: true, safetyCritical: true },
    ],
    procedures: { measurements: [{ id: 'bar_mass', label: 'Масса грифа и подвижных частей' }], scenarios: [{ id: 'weightless_drift', label: 'Дрейф' }] },
  }),
  fetchTuning: vi.fn().mockResolvedValue({ values: { 'compensation.barMassKg': 20, 'compensation.gravityEnabled': true, 'homing.limitSwitchesEnabled': true }, persisted: {}, temporary: {}, serviceMode: false, adapter: 'physics-emulator' }),
  fetchEvents: vi.fn().mockResolvedValue([]),
  updateTuning: vi.fn(),
  revertTuning: vi.fn(),
  resetTuning: vi.fn(),
  fetchPresets: vi.fn().mockResolvedValue([]),
  savePreset: vi.fn(),
  deletePreset: vi.fn(),
  diffPreset: vi.fn(),
  applyPreset: vi.fn(),
  startProcedure: vi.fn(),
  abortProcedure: vi.fn(),
  fetchEmulator: vi.fn().mockResolvedValue({ active: true }),
  controlEmulator: vi.fn(),
  fetchRecordings: vi.fn().mockResolvedValue({ recording: false, recordings: [], incidents: [] }),
  controlRecording: vi.fn(),
  fetchRecording: vi.fn(),
  deleteRecording: vi.fn(),
}))

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  addEventListener = vi.fn()
  close = vi.fn()
  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }
}

const snapshot = {
  eventType: 'hardware.snapshot',
  emittedAt: '',
  machine: { machineState: 'ready', machineLabel: 'Тренажёр готов', safety: 'enabled', leftDrive: 'connected', rightDrive: 'connected', calibration: '—' },
  safety: { state: 'enabled', label: '', message: '', requiresService: false, activeEventId: null },
  emulatorMode: true,
  serviceMode: false,
  selectedUserId: 'alexey',
  userSelected: true,
  drives: [],
  motion: { moving: false, motionProfile: 'normal', barPositionMm: 860, leftPositionMm: 860, rightPositionMm: 860, syncDeltaMm: 0.4, amplitudePercent: 0, tempoLabel: '—', repetitionCount: 0, currentSet: 1, targetSet: 1, targetReps: 10, direction: 'up' },
  control: {
    mode: 'idle', label: 'Тренажёр готов', message: '', positionMm: 860.2, velocityMmPerSec: 0, accelerationMmPerSec2: 0, userForceKg: 0, userForceLeftKg: 0, userForceRightKg: 0, loadTargetKg: 0, loadEffectiveKg: 0, components: {},
    repetitionCount: 0, partialReps: 0, concentricS: 0, eccentricS: 0, tempoLabel: '—', repQuality: 0, targetReached: false, syncDeltaMm: 0.4, syncStatus: 'norm', asymmetryPercent: 0, gripDetected: false, released: false, stallS: 0,
    spotterActive: false, failureDetected: false, stillMs: 0, postStatus: 'passed', postResults: [], homed: true, positionKnown: true, heartbeatOk: true, commOk: true, powerOk: true, brakeEngaged: true, fixedHoldTestPassed: false, fixedDriftMm: 0,
    isometricElapsedS: 0, moveTargetMm: null, moveProgressPercent: 0, faultCode: null, tickLatencyMs: 20, missedTicks: 0, counters: { travelMmTotal: 0, cyclesTotal: 0, loadedSecondsTotal: 0 },
    config: { lowerMm: 640, upperMm: 1320, startPoint: 'lower', loadKg: 20, loadMode: 'normal_weight', targetReps: 10, fixedPositionMm: null }, brakes: { left: true, right: true }, limitSwitches: {}, adapter: 'physics-emulator', temporaryParameters: 0,
  },
  procedure: { name: null, label: '', status: 'idle', step: '', progressTicks: 0, result: null, startedAt: null, finishedAt: null },
  calibrationRequired: false,
  calibrationActual: false,
  activeCalibrationId: null,
  commandQueueDepth: 0,
  lastCommand: null,
  diagnosticsStatus: 'ready',
  lastDiagnosticsAt: null,
  alerts: [],
} as unknown as HardwareSnapshot

describe('MechanicsTuningScreen', () => {
  beforeEach(() => {
    vi.mocked(fetchModbusPositions).mockReset().mockResolvedValue({ connected: false, simulationMode: false, zeroed: false, left: { slaveId: 1, currentPulses: null, zeroPulses: null, positionMm: null }, right: { slaveId: 2, currentPulses: null, zeroPulses: null, positionMm: null }, skewMm: null, error: null })
    vi.mocked(zeroModbusPositions).mockReset()
    vi.stubGlobal('WebSocket', FakeWebSocket)
    FakeWebSocket.instances = []
    useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
    useHardwareStore.setState({ snapshot, runCommand: vi.fn().mockResolvedValue({}) })
    useTuningStore.setState({ schema: null, tuning: null, pending: {}, liveSamples: [], events: [] })
  })

  it('renders registry-driven parameters read-only outside service mode and shows control state', async () => {
    render(<MemoryRouter><MechanicsTuningScreen /></MemoryRouter>)
    expect(await screen.findByRole('spinbutton', { name: 'Масса грифа' })).toBeInTheDocument()
    expect(screen.getByText(/Изменение параметров, запуск процедур/)).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Масса грифа' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'Компенсация веса' })).toBeDisabled()
    expect(screen.getByText('860.2 мм')).toBeInTheDocument()
    expect(FakeWebSocket.instances.some((socket) => socket.url.includes('/api/hardware/telemetry-debug'))).toBe(true)
  })

  it('shows fresh real servo heights even while the hardware controller runs the emulator', async () => {
    let left = 10000
    let right = 20000
    vi.mocked(fetchModbusPositions).mockImplementation(async () => ({
      connected: true, simulationMode: false, zeroed: true,
      left: { slaveId: 1, currentPulses: left, zeroPulses: 0, positionMm: left * 1703 / 6980387 },
      right: { slaveId: 2, currentPulses: right, zeroPulses: 0, positionMm: right * 1703 / 6980387 },
      skewMm: (left - right) * 1703 / 6980387, error: null,
    }))

    const view = render(<MemoryRouter><MechanicsTuningScreen /></MemoryRouter>)
    expect(await screen.findByText('2.4397 мм')).toBeInTheDocument()
    expect(screen.getAllByText('4.8794 мм')).toHaveLength(2)
    expect(screen.getByText('9.7588 мм')).toBeInTheDocument()
    expect(fetchModbusPositions).toHaveBeenCalled()

    left = 20000
    right = 30000
    await waitFor(() => expect(screen.getByText('80.0000 мм')).toBeInTheDocument(), { timeout: 2500 })
    expect(screen.getByText('96.0000 мм')).toBeInTheDocument()
    view.unmount()
  })

  it('rezeros both drives and displays zero immediately without restarting', async () => {
    vi.mocked(fetchModbusPositions).mockResolvedValue({
      connected: true, simulationMode: false, zeroed: true,
      left: { slaveId: 1, currentPulses: 10000, zeroPulses: 0, positionMm: 32 },
      right: { slaveId: 2, currentPulses: 20000, zeroPulses: 0, positionMm: 64 },
      skewMm: -32, error: null,
    })
    vi.mocked(zeroModbusPositions).mockResolvedValue({
      connected: true, simulationMode: false, zeroed: true,
      left: { slaveId: 1, currentPulses: 10000, zeroPulses: 10000, positionMm: 0 },
      right: { slaveId: 2, currentPulses: 20000, zeroPulses: 20000, positionMm: 0 },
      skewMm: 0, error: null,
    })
    render(<MemoryRouter><MechanicsTuningScreen /></MemoryRouter>)
    expect(await screen.findByText('48.0000 мм')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Обнулить позицию' }))
    await waitFor(() => expect(screen.getAllByText('0.0000 мм')).toHaveLength(4))
    expect(zeroModbusPositions).toHaveBeenCalledOnce()
  })

  it('enables editing in service mode and sends the STOP command from the header', async () => {
    useHardwareStore.setState({ snapshot: { ...snapshot, serviceMode: true } })
    render(<MemoryRouter><MechanicsTuningScreen /></MemoryRouter>)
    const input = await screen.findByRole('spinbutton', { name: 'Масса грифа' })
    expect(input).toBeEnabled()
    screen.getByRole('button', { name: 'СТОП' }).click()
    expect(useHardwareStore.getState().runCommand).toHaveBeenCalledWith({ action: 'trigger_emergency_stop', userId: 'alexey' })
  })

  it('saves the limit-switch setting only from service mode and requires a restart', async () => {
    render(<MemoryRouter><MechanicsTuningScreen /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Поиск границ' }))
    expect(screen.getByRole('switch', { name: 'Концевые датчики установлены' })).toBeDisabled()

    useHardwareStore.setState({ snapshot: { ...snapshot, serviceMode: true } })
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Концевые датчики установлены' })).toBeEnabled())
    fireEvent.click(screen.getByRole('switch', { name: 'Концевые датчики установлены' }))
    expect(useTuningStore.getState().pending).toEqual({ 'homing.limitSwitchesEnabled': false })
    expect(screen.getByText('После перезапуска')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Применить временно' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(updateTuning).toHaveBeenCalledWith({ 'homing.limitSwitchesEnabled': false }, 'persist', 'alexey'))
  })
})
