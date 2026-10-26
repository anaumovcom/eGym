/** Which machine latches silence the coach (decision 26.10.2026, D-V12.7).
 *
 * A machine ERROR — a fault code, a blocked machine, a service request, a control/motion «fault» mode — no longer
 * silences the coach: the motors are stopped and talking is harmless. Emergency stop, the panel STOP, estop modes,
 * the spotter catching the weight and a detected failure still silence it, as does reported pain.
 */
export const SILENCING_MODES: readonly string[] = ['estop', 'emergency_stop', 'failure', 'spotter']
export const FAULT_MODES: readonly string[] = ['fault']
export const MACHINE_ERROR_LATCHES: ReadonlySet<string> = new Set(['faultCode', 'blocked', 'requiresService', 'controlFault', 'motionFault'])
/** The machine is merely working (training, moving): never a safety latch. */
const ACTIVITY_LATCHES: ReadonlySet<string> = new Set(['controlActive', 'motionActive', 'moving'])

export function silencesCoach(key: string): boolean {
  return !key.startsWith('active') && !ACTIVITY_LATCHES.has(key) && !MACHINE_ERROR_LATCHES.has(key)
}
