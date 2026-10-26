/** Which machine latches silence the coach (decisions 26.10.2026, D-V12.7).
 *
 * Only an emergency silences it: an emergency stop (estop modes), the panel STOP — and reported pain, handled by the
 * interpreter. Everything else the machine reports — a fault code, a blocked machine, a service request, a «fault»
 * mode, the spotter catching the weight, a detected failure — is shown in the panel while the coach keeps talking.
 */
export const SILENCING_MODES: readonly string[] = ['estop', 'emergency_stop']
export const FAULT_MODES: readonly string[] = ['fault']
export const ASSIST_MODES: readonly string[] = ['failure', 'spotter']
export const TALK_THROUGH_LATCHES: ReadonlySet<string> = new Set([
  'faultCode', 'blocked', 'requiresService', 'controlFault', 'motionFault', 'spotter', 'failure', 'controlAssist', 'motionAssist',
])
/** The spotter holds the weight or a failure is detected: the coach talks, but never cheers the set on. */
export const ASSIST_LATCHES: ReadonlySet<string> = new Set(['spotter', 'failure', 'controlAssist', 'motionAssist'])
/** The machine is merely working (training, moving): never a safety latch. */
const ACTIVITY_LATCHES: ReadonlySet<string> = new Set(['controlActive', 'motionActive', 'moving'])

export function silencesCoach(key: string): boolean {
  return !key.startsWith('active') && !ACTIVITY_LATCHES.has(key) && !TALK_THROUGH_LATCHES.has(key)
}
