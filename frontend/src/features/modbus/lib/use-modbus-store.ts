import { create } from 'zustand'
import {
  clearModbusLog,
  compareModbusProfile,
  connectModbus,
  disconnectModbus,
  fetchModbusDiagnostics,
  fetchModbusLog,
  fetchModbusPorts,
  fetchModbusProfiles,
  fetchModbusStatus,
  pingModbus,
  readModbusRegisters,
  runModbusCommand,
  saveModbusProfile,
  writeModbusRegister,
} from '@/features/modbus/api/modbus-api'
import { PARAMETER_CATALOG } from '@/features/modbus/model/parameter-catalog'
import type {
  DriverDiagnostics,
  ExchangeLogEntry,
  ModbusCommand,
  ModbusConnectionParams,
  ModbusConnectionStatus,
  ParameterProfile,
  ParameterState,
  ProfileCompareResult,
  SerialPortInfo,
} from '@/features/modbus/model/types'

const DEFAULT_PARAMS: ModbusConnectionParams = {
  port: '/dev/ttyUSB0',
  baudRate: 19200,
  dataBits: 8,
  parity: 'E',
  stopBits: 1,
  slaveId: 1,
  rightSlaveId: 2,
  timeoutMs: 500,
}

function buildInitialParamState(): Map<number, ParameterState> {
  const m = new Map<number, ParameterState>()
  for (const p of PARAMETER_CATALOG) {
    m.set(p.address, {
      address: p.address,
      driverValue: null,
      uiValue: null,
      dirty: false,
      writtenButUnsaved: false,
      readStatus: 'idle',
      writeStatus: 'idle',
      readError: null,
      writeError: null,
      readAt: null,
    })
  }
  return m
}

type ModbusStore = {
  controlTarget: 'left' | 'right' | 'both'
  setControlTarget: (target: 'left' | 'right' | 'both') => void
  selectedSide: 'left' | 'right'
  driveAddresses: { left: number; right: number }
  selectSide: (side: 'left' | 'right') => void
  setDriveAddress: (side: 'left' | 'right', address: number) => void
  // Connection
  connectionParams: ModbusConnectionParams
  connectionStatus: ModbusConnectionStatus | null
  ports: SerialPortInfo[]
  setConnectionParams: (params: Partial<ModbusConnectionParams>) => void

  // Diagnostics
  diagnostics: DriverDiagnostics | null

  // Parameters
  paramStates: Map<number, ParameterState>
  setUiValue: (address: number, value: number | null) => void
  discardUiChanges: () => void

  // Log
  logEntries: ExchangeLogEntry[]
  logTotal: number
  logFilter: { direction?: string; action?: string }
  setLogFilter: (f: Partial<ModbusStore['logFilter']>) => void

  // Profiles
  profiles: ParameterProfile[]
  lastCompare: ProfileCompareResult | null

  // Motor protection
  motorEnabled: boolean
  setMotorEnabled: (v: boolean) => void

  // Async actions
  loadPorts: () => Promise<void>
  loadStatus: () => Promise<void>
  connect: () => Promise<void>
  disconnect: () => Promise<void>
  ping: () => Promise<boolean>
  readRegister: (address: number, count?: number) => Promise<void>
  readBatch: (addresses: number[]) => Promise<void>
  writeRegister: (address: number, value: number) => Promise<void>
  writeControlRegister: (address: number, value: number, verify?: boolean) => Promise<void>
  writeAllDirty: () => Promise<void>
  loadDiagnostics: () => Promise<void>
  runCommand: (command: ModbusCommand, confirmed: boolean, params?: Record<string, number>) => Promise<{ success: boolean; error?: string }>
  loadLog: () => Promise<void>
  clearLog: () => Promise<void>
  loadProfiles: () => Promise<void>
  saveProfile: (name: string, comment?: string, addresses?: number[]) => Promise<void>
  compareProfile: (id: string) => Promise<void>
}

export const useModbusStore = create<ModbusStore>((set, get) => ({
  controlTarget: 'both',
  setControlTarget(controlTarget) { set({ controlTarget }) },
  selectedSide: 'left',
  driveAddresses: { left: 1, right: 2 },
  selectSide(side) {
    set({ selectedSide: side, paramStates: buildInitialParamState(), diagnostics: null, lastCompare: null })
  },
  setDriveAddress(side, address) {
    if (!Number.isInteger(address) || address < 1 || address > 247) return
    if (address === get().driveAddresses[side === 'left' ? 'right' : 'left']) return
    set((s) => ({ driveAddresses: { ...s.driveAddresses, [side]: address }, paramStates: buildInitialParamState(), diagnostics: null }))
  },
  connectionParams: DEFAULT_PARAMS,
  connectionStatus: null,
  ports: [],
  diagnostics: null,
  paramStates: buildInitialParamState(),
  logEntries: [],
  logTotal: 0,
  logFilter: {},
  profiles: [],
  lastCompare: null,
  motorEnabled: false,

  setConnectionParams(params) {
    set((s) => ({ connectionParams: { ...s.connectionParams, ...params } }))
  },

  setUiValue(address, value) {
    set((s) => {
      const next = new Map(s.paramStates)
      const cur = next.get(address)
      if (!cur) return {}
      next.set(address, {
        ...cur,
        uiValue: value,
        dirty: value !== null && value !== cur.driverValue,
      })
      return { paramStates: next }
    })
  },

  discardUiChanges() {
    set((s) => {
      const next = new Map(s.paramStates)
      for (const [addr, st] of next) {
        next.set(addr, { ...st, uiValue: null, dirty: false })
      }
      return { paramStates: next }
    })
  },

  setLogFilter(f) {
    set((s) => ({ logFilter: { ...s.logFilter, ...f } }))
  },

  setMotorEnabled(v) {
    set({ motorEnabled: v })
  },

  // ---------------------------------------------------------------------------
  // Connection
  // ---------------------------------------------------------------------------

  async loadPorts() {
    const ports = await fetchModbusPorts()
    set({ ports })
  },

  async loadStatus() {
    const status = await fetchModbusStatus()
    set((state) => ({
      connectionStatus: status,
      driveAddresses: status.slaveId && status.rightSlaveId && status.slaveId !== status.rightSlaveId
        ? { left: status.slaveId, right: status.rightSlaveId } : state.driveAddresses,
      connectionParams: status.port && status.baudRate
        ? { ...state.connectionParams, port: status.port, baudRate: status.baudRate, slaveId: status.slaveId ?? state.connectionParams.slaveId, rightSlaveId: status.rightSlaveId ?? state.connectionParams.rightSlaveId }
        : state.connectionParams,
    }))
  },

  async connect() {
    const { connectionParams, driveAddresses } = get()
    const status = await connectModbus({ ...connectionParams, slaveId: driveAddresses.left, rightSlaveId: driveAddresses.right })
    set({ connectionStatus: status })
  },

  async disconnect() {
    const status = await disconnectModbus()
    set({ connectionStatus: status })
  },

  async ping() {
    const { selectedSide, driveAddresses } = get()
    const result = await pingModbus(driveAddresses[selectedSide])
    void get().loadStatus()
    return result.success
  },

  // ---------------------------------------------------------------------------
  // Read / Write
  // ---------------------------------------------------------------------------

  async readRegister(address, count = 1) {
    const { selectedSide, driveAddresses } = get()
    // Set loading for all target addresses
    set((s) => {
      const next = new Map(s.paramStates)
      for (let i = 0; i < count; i++) {
        const addr = address + i
        const cur = next.get(addr)
        if (cur) next.set(addr, { ...cur, readStatus: 'loading', readError: null })
      }
      return { paramStates: next }
    })

    const result = await readModbusRegisters(address, count, driveAddresses[selectedSide])
    if (get().selectedSide !== selectedSide || get().driveAddresses[selectedSide] !== driveAddresses[selectedSide]) return

    set((s) => {
      const next = new Map(s.paramStates)
      if (result.success) {
        for (const reg of result.registers) {
          const cur = next.get(reg.address)
          if (cur) {
            next.set(reg.address, {
              ...cur,
              driverValue: reg.value,
              readStatus: reg.error ? 'error' : 'ok',
              readError: reg.error,
              readAt: reg.readAt,
            })
          }
        }
      } else {
        for (let i = 0; i < count; i++) {
          const addr = address + i
          const cur = next.get(addr)
          if (cur) next.set(addr, { ...cur, readStatus: 'error', readError: result.error })
        }
      }
      return { paramStates: next }
    })
  },

  async readBatch(addresses) {
    for (const addr of addresses) {
      await get().readRegister(addr)
    }
  },

  async writeRegister(address, value) {
    const { selectedSide, driveAddresses } = get()
    set((s) => {
      const next = new Map(s.paramStates)
      const cur = next.get(address)
      if (cur) next.set(address, { ...cur, writeStatus: 'loading', writeError: null })
      return { paramStates: next }
    })

    const result = await writeModbusRegister(address, value, driveAddresses[selectedSide])
    if (get().selectedSide !== selectedSide || get().driveAddresses[selectedSide] !== driveAddresses[selectedSide]) return

    set((s) => {
      const next = new Map(s.paramStates)
      const cur = next.get(address)
      if (cur) {
        next.set(address, {
          ...cur,
          writeStatus: result.success ? 'ok' : 'error',
          writeError: result.error,
          driverValue: result.success ? value : cur.driverValue,
          uiValue: result.success ? null : cur.uiValue,
          dirty: !result.success,
          writtenButUnsaved: result.success,
        })
      }
      return { paramStates: next }
    })
  },

  async writeControlRegister(address, value, verify = false) {
    const { controlTarget, driveAddresses } = get()
    const sides = controlTarget === 'both' ? (['left', 'right'] as const) : [controlTarget]
    const errors: string[] = []
    for (const side of sides) {
      try {
        const result = await writeModbusRegister(address, value, driveAddresses[side])
        if (!result.success) {
          errors.push(`${side} (ID ${driveAddresses[side]}): ${result.error ?? 'нет ответа'}`)
          continue
        }
        if (verify) {
          const readback = await readModbusRegisters(address, 1, driveAddresses[side])
          const reg = readback.registers[0]
          if (!readback.success || !reg || reg.error || (reg.value & 0xffff) !== (value & 0xffff)) {
            errors.push(`${side} (ID ${driveAddresses[side]}): запись не подтверждена чтением (${reg?.error ?? readback.error ?? reg?.value ?? 'нет ответа'})`)
          }
        }
      } catch (error) {
        errors.push(`${side} (ID ${driveAddresses[side]}): ${error instanceof Error ? error.message : 'нет ответа'}`)
      }
    }
    if (errors.length) throw new Error(errors.join('; '))
    // Values in the parameter table refer only to the selected drive.
    if (sides.includes(get().selectedSide)) void get().readRegister(address).catch(() => undefined)
  },

  async writeAllDirty() {
    const dirty = [...get().paramStates.values()].filter((s) => s.dirty && s.uiValue !== null)
    for (const st of dirty) {
      await get().writeRegister(st.address, st.uiValue!)
    }
  },

  // ---------------------------------------------------------------------------
  // Diagnostics
  // ---------------------------------------------------------------------------

  async loadDiagnostics() {
    const { selectedSide, driveAddresses } = get()
    const diag = await fetchModbusDiagnostics(driveAddresses[selectedSide])
    if (get().selectedSide === selectedSide) set({ diagnostics: diag })
  },

  // ---------------------------------------------------------------------------
  // Commands
  // ---------------------------------------------------------------------------

  async runCommand(command, confirmed, params) {
    const { controlTarget, driveAddresses } = get()
    const sides = controlTarget === 'both' ? (['left', 'right'] as const) : [controlTarget]
    const errors: string[] = []
    for (const side of sides) {
      try {
        const result = await runModbusCommand(command, confirmed, params, driveAddresses[side])
        if (!result.success) errors.push(`${side} (ID ${driveAddresses[side]}): ${result.error ?? 'нет ответа'}`)
      } catch (error) {
        errors.push(`${side} (ID ${driveAddresses[side]}): ${error instanceof Error ? error.message : 'нет ответа'}`)
      }
    }
    const success = errors.length === 0
    if (success && command === 'save_parameters') {
      set((s) => {
        const next = new Map(s.paramStates)
        for (const [address, state] of next.entries()) {
          next.set(address, {
            ...state,
            writtenButUnsaved: false,
          })
        }
        return { paramStates: next }
      })
    }
    void get().loadStatus()
    return { success, error: errors.length ? errors.join('; ') : undefined }
  },

  // ---------------------------------------------------------------------------
  // Log
  // ---------------------------------------------------------------------------

  async loadLog() {
    const { logFilter } = get()
    const data = await fetchModbusLog(200, logFilter.direction, logFilter.action)
    set({ logEntries: data.entries, logTotal: data.total })
  },

  async clearLog() {
    await clearModbusLog()
    set({ logEntries: [], logTotal: 0 })
  },

  // ---------------------------------------------------------------------------
  // Profiles
  // ---------------------------------------------------------------------------

  async loadProfiles() {
    const profiles = await fetchModbusProfiles()
    set({ profiles })
  },

  async saveProfile(name, comment = '', addresses) {
    await saveModbusProfile(name, comment, addresses)
    await get().loadProfiles()
  },

  async compareProfile(id) {
    const result = await compareModbusProfile(id)
    set({ lastCompare: result })
  },
}))
