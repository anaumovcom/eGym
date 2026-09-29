// Types for Modbus debug screen

export type Parity = 'N' | 'E' | 'O'

export type ModbusConnectionParams = {
  port: string
  baudRate: number
  dataBits: number
  parity: Parity
  stopBits: number
  slaveId: number
  rightSlaveId: number
  timeoutMs: number
  leftDirection: -1 | 1
  rightDirection: -1 | 1
}

export type PositionExercise = {
  exerciseKey?: string
  targetType: 'lower_boundary' | 'fixed_position'
  lowerBoundaryMm: number | null
  fixedPositionMm: number | null
  torqueLimit: number
  speedRpm: number
  minMm: number
  maxMm: number
}

export type PositionMotionStatus = {
  state: 'idle' | 'exercise' | 'raising' | 'weightless' | 'holding' | 'fault'
  targetType: PositionExercise['targetType'] | 'stop_raise' | 'weightless' | 'hold' | null
  targetMm: number | null
  torqueLimit: number | null
  speedRpm: number | null
  positions: ModbusPositions
  servoOn: Record<string, boolean | null>
  posLoad: Record<string, boolean | null>
  drives: Record<string, Record<string, number | null>>
  warning: string | null
  error: string | null
  simulationOnly: boolean
}

export type PositionCalibration = {
  exerciseKey: string
  zeroGeneration: number
  lowerMm: number | null
  upperMm: number | null
  fixedMm: number | null
}

export type ModbusConnectionStatus = {
  connected: boolean
  port: string | null
  baudRate: number | null
  parity: string | null
  slaveId: number | null
  rightSlaveId: number | null
  leftDirection: -1 | 1
  rightDirection: -1 | 1
  lastSuccessAt: string | null
  okCount: number
  errorCount: number
  errorMessage: string | null
  simulationMode: boolean
}

export type SerialPortInfo = {
  device: string
  description: string
  hardwareId: string | null
}

export type ModbusRegisterValue = {
  address: number
  addressHex: string
  value: number
  rawBytes: string | null
  error: string | null
  readAt: string | null
}

export type ModbusReadResult = {
  success: boolean
  registers: ModbusRegisterValue[]
  elapsedMs: number | null
  error: string | null
  rawRequest: string | null
  rawResponse: string | null
}

export type ModbusPositions = {
  connected: boolean
  simulationMode: boolean
  zeroed: boolean
  zeroGeneration: number
  readiness: ModbusReadiness
  left: { slaveId: number; currentPulses: number | null; zeroPulses: number | null; positionMm: number | null }
  right: { slaveId: number; currentPulses: number | null; zeroPulses: number | null; positionMm: number | null }
  skewMm: number | null
  error: string | null
}

export type ModbusReadiness = {
  communicationReady: boolean
  encoderReady: boolean
  torqueControlReady: boolean
  motionSafetyReady: boolean
  degradedManualMode: boolean
  allowEncoderRead: boolean
  allowZeroOffset: boolean
  allowStatusRead: boolean
  allowManualTorqueTest: boolean
  allowAutomaticMotion: boolean
  allowPositionAutoMove: boolean
  allowProgramWorkout: boolean
  allowHoming: boolean
  noBrake: boolean
  noLimitSwitches: boolean
  noHardwareStop: boolean
  noHardwareSync: boolean
  warning: string
}

export type SoftwareStopResult = {
  success: boolean
  torqueZeroed: Record<string, boolean>
  servoOffConfirmed: Record<string, boolean>
  errors: string[]
  warning: string
}

export type ModbusWriteResult = {
  success: boolean
  address: number
  value: number
  elapsedMs: number | null
  error: string | null
  rawRequest: string | null
  rawResponse: string | null
}

export type DriverDiagnostics = {
  responding: boolean
  slaveId: number | null
  baudRateCode: number | null
  controlMode: number | null
  extendedMode: number | null
  alarmCode: number | null
  hasAlarm: boolean
  motionSafe: boolean
  statusSummary: string
  checkedAt: string | null
}

export type ModbusCommand =
  | 'servo_on'
  | 'servo_off'
  | 'alarm_reset'
  | 'emergency_stop'
  | 'pos_load'
  | 'jog_start'
  | 'jog_stop'
  | 'homing'
  | 'save_parameters'
  | 'clear_alarm_history'

export type ModbusCommandResult = {
  success: boolean
  command: string
  message: string
  error: string | null
}

export type ExchangeDirection = 'TX' | 'RX' | 'INFO' | 'ERROR'

export type ExchangeLogEntry = {
  id: number
  ts: string
  direction: ExchangeDirection
  slaveId: number | null
  action: string
  parameter: string | null
  address: number | null
  value: number | null
  result: string | null
  rawRequest: string | null
  rawResponse: string | null
  error: string | null
  elapsedMs: number | null
}

export type ExchangeLogResponse = {
  entries: ExchangeLogEntry[]
  total: number
}

export type ControlMode = 'position' | 'speed' | 'torque'

// Parameter catalog types
export type ParameterGroup =
  | 'basic'
  | 'communication'
  | 'control_mode'
  | 'communication_control'
  | 'position'
  | 'speed'
  | 'torque'
  | 'di_do'
  | 'monitoring'
  | 'errors'
  | 'save_service'
  | 'service'
  | 'jog'
  | 'homing'
  | 'limits'
  | 'gains'
  | 'inertia'
  | 'manufacturer'

export type ParameterApplicableMode = 'ALL' | 'P' | 'S' | 'T'

export type ParameterDef = {
  name: string         // e.g. "PA_002"
  address: number      // decimal
  addressHex: string   // e.g. "0x002"
  label: string        // human label
  group: ParameterGroup
  mode: ParameterApplicableMode
  min: number
  max: number
  defaultValue: number
  unit: string
  description: string
  requiresReboot: boolean
  dangerous: boolean
  readOnly: boolean
  enumMap?: Record<number, string>
}

// UI state per parameter
export type ParameterState = {
  address: number
  driverValue: number | null
  uiValue: number | null   // what the user typed, not yet written
  dirty: boolean           // ui value differs from driver
  writtenButUnsaved: boolean
  readStatus: 'idle' | 'loading' | 'ok' | 'error'
  writeStatus: 'idle' | 'loading' | 'ok' | 'error'
  readError: string | null
  writeError: string | null
  readAt: string | null
}

export type ParameterProfile = {
  id: string | null
  name: string
  driverModel: string
  slaveId: number
  baudRate: number
  parameters: { address: number; name: string; value: number }[]
  comment: string
  createdAt: string | null
}

export type ProfileCompareResult = {
  differences: { address: number; addressHex: string; name: string; driverValue: number; profileValue: number }[]
  matching: number
  differing: number
}
