export type MachineHealth = {
  machineState: 'ready' | 'warning' | 'blocked'
  machineLabel: string
  leftDrive: 'connected' | 'warning' | 'error'
  rightDrive: 'connected' | 'warning' | 'error'
  safety: 'enabled' | 'disabled' | 'emergency_stop'
  calibration: string
}