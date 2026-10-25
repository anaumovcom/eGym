import { describe, expect, it } from 'vitest'
import { DEFAULT_COACH_PREFERENCES as defaults, effectiveCoachState, preferencesValid, type CoachPreferences } from './preferences'
import { useStage4Store } from '@/stores/stage4-store'
import { buildSystemSettingsData, defaultStage4DevFlags } from '@/mocks/stage4-data'

const general = { soundEnabled: true, voiceHintsEnabled: true, volume: 0.7 }
const enabled: CoachPreferences = { ...defaults, enabled: true, consentVersion: 1 }
describe('Coach preference admission (no providers)', () => {
  it('keeps conversation memory and separate cross-workout opt-in independent of history consent', () => {
    expect(defaults.memoryEnabled).toBe(true)
    expect(defaults.crossWorkoutMemory).toBe(false)
    expect(preferencesValid({ ...defaults, memoryEnabled: false, historyConsent: true })).toBe(true)
    expect(preferencesValid({ ...defaults, crossWorkoutMemory: true, historyConsent: false })).toBe(true)
  })
  it.each(['memoryEnabled', 'crossWorkoutMemory'] as const)('requires a real boolean for %s', key => {
    expect(preferencesValid({ ...defaults, [key]: 'true' } as unknown as CoachPreferences)).toBe(false)
  })
  it('defaults signals and inherited coach voice to full volume', () => {
    expect(useStage4Store.getState().settingsSaved.signalVolume).toBe('100%')
    expect(buildSystemSettingsData(defaultStage4DevFlags).common.signalVolume).toBe('100%')
    expect(effectiveCoachState(enabled, { ...general, volume: 1 }, true).volume).toBe(1)
  })
  it('defaults off and never inherits activation from legacy voice hints', () => {
    expect(effectiveCoachState(defaults, general, true)).toEqual({ audioEnabled: false, textEnabled: false, volume: 0, paidProductionReady: false })
  })
  it.each([
    [null, true], [enabled, false], [{ ...enabled, consentVersion: null }, true],
    [{ ...enabled, mode: 'hybrid', networkConsentVersion: null }, true],
  ] as const)('fails closed for missing gates %j / %s', (p, flag) => {
    expect(effectiveCoachState(p, general, flag).audioEnabled).toBe(false)
    expect(effectiveCoachState(p, general, flag).textEnabled).toBe(false)
  })
  it.each([
    { ...general, soundEnabled: false }, { ...general, voiceHintsEnabled: false }, { ...general, volume: 0 },
  ])('mute blocks audio but never enables text: %j', audio => {
    expect(effectiveCoachState(enabled, audio, true)).toMatchObject({ audioEnabled: false, textEnabled: false })
  })
  it('explicit text-only remains eligible with audio fully disabled', () => {
    expect(effectiveCoachState({ ...enabled, mode: 'text-only', networkConsentVersion: 1 },
      { soundEnabled: false, voiceHintsEnabled: false, volume: 0 }, true)).toEqual({ audioEnabled: false, textEnabled: true, volume: 0, paidProductionReady: false })
  })
  it('inherits volume; override never bypasses general mute', () => {
    expect(effectiveCoachState(enabled, general, true).volume).toBe(0.7)
    expect(effectiveCoachState({ ...enabled, voiceVolume: 0.25 }, general, true).volume).toBe(0.25)
    expect(effectiveCoachState({ ...enabled, voiceVolume: 1 }, { ...general, volume: 0 }, true).audioEnabled).toBe(false)
    expect(effectiveCoachState({ ...enabled, voiceVolume: 0 }, general, true).audioEnabled).toBe(false)
  })
  it.each(['0', '-1', '10.01', 'Infinity', 'NaN', '', '0.00001'])('rejects invalid budget %s', budgetUsd => {
    expect(preferencesValid({ ...defaults, budgetUsd })).toBe(false)
  })
  it.each(['0.001', '0.01', '1.5', '2.00', '10.00'])('accepts bounded budget %s', budgetUsd => {
    expect(preferencesValid({ ...defaults, budgetUsd })).toBe(true)
  })
})