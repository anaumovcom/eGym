import { beforeEach, describe, expect, it, vi } from 'vitest'
import { writeModbusRegister, runModbusCommand, readModbusRegisters, fetchModbusStatus } from '@/features/modbus/api/modbus-api'
import { useModbusStore } from './use-modbus-store'

vi.mock('@/features/modbus/api/modbus-api', () => ({
  writeModbusRegister: vi.fn(),
  readModbusRegisters: vi.fn(),
  runModbusCommand: vi.fn(),
  fetchModbusStatus: vi.fn(),
}))

describe('dual-drive Modbus control', () => {
  beforeEach(() => {
    vi.mocked(readModbusRegisters).mockResolvedValue({ success: true, registers: [] } as Awaited<ReturnType<typeof readModbusRegisters>>)
    vi.mocked(fetchModbusStatus).mockResolvedValue({ connected: true, port: '/dev/ttyUSB0', baudRate: 19200 } as Awaited<ReturnType<typeof fetchModbusStatus>>)
    vi.mocked(writeModbusRegister).mockReset().mockResolvedValue({ success: true } as Awaited<ReturnType<typeof writeModbusRegister>>)
    vi.mocked(runModbusCommand).mockReset().mockResolvedValue({ success: true } as Awaited<ReturnType<typeof runModbusCommand>>)
    useModbusStore.setState({ controlTarget: 'both', driveAddresses: { left: 1, right: 2 }, selectedSide: 'left' })
  })

  it('addresses both motors separately for each control write', async () => {
    await useModbusStore.getState().writeControlRegister(0x002, 1)
    expect(writeModbusRegister).toHaveBeenCalledWith(0x002, 1, 1)
    expect(writeModbusRegister).toHaveBeenCalledWith(0x002, 1, 2)
  })

  it('reports partial failure instead of claiming both motors were updated', async () => {
    vi.mocked(writeModbusRegister).mockResolvedValueOnce({ success: true } as Awaited<ReturnType<typeof writeModbusRegister>>)
      .mockResolvedValueOnce({ success: false, error: 'timeout' } as Awaited<ReturnType<typeof writeModbusRegister>>)
    await expect(useModbusStore.getState().writeControlRegister(0x002, 1)).rejects.toThrow('right (ID 2): timeout')
  })

  it('verifies torque segment zero on both motors before reporting success', async () => {
    vi.mocked(readModbusRegisters).mockResolvedValue({ success: true, registers: [{ value: 180, error: null }] } as Awaited<ReturnType<typeof readModbusRegisters>>)
    await useModbusStore.getState().writeControlRegister(0x12c, 180, true)
    expect(readModbusRegisters).toHaveBeenCalledWith(0x12c, 1, 1)
    expect(readModbusRegisters).toHaveBeenCalledWith(0x12c, 1, 2)
  })

  it('does not accept a mismatched torque readback from the right motor', async () => {
    vi.mocked(readModbusRegisters).mockResolvedValueOnce({ success: true, registers: [{ value: 180, error: null }] } as Awaited<ReturnType<typeof readModbusRegisters>>)
      .mockResolvedValueOnce({ success: true, registers: [{ value: 0, error: null }] } as Awaited<ReturnType<typeof readModbusRegisters>>)
    await expect(useModbusStore.getState().writeControlRegister(0x12c, 180, true)).rejects.toThrow('right (ID 2): запись не подтверждена')
  })

  it('sends commands to both IDs and returns the failure for the right motor', async () => {
    vi.mocked(runModbusCommand).mockResolvedValueOnce({ success: true } as Awaited<ReturnType<typeof runModbusCommand>>)
      .mockResolvedValueOnce({ success: false, error: 'unsupported' } as Awaited<ReturnType<typeof runModbusCommand>>)
    const result = await useModbusStore.getState().runCommand('servo_off', true)
    expect(runModbusCommand).toHaveBeenCalledWith('servo_off', true, undefined, 1)
    expect(runModbusCommand).toHaveBeenCalledWith('servo_off', true, undefined, 2)
    expect(result).toEqual({ success: false, error: 'right (ID 2): unsupported' })
  })
})
