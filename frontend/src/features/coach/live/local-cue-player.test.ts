import { describe, expect, it, vi } from 'vitest'
import type { LocalCue } from '../interpreter/coach-interpreter'
import type { CoachScope } from '../model/contracts'
import { OFFLINE_COUNT_GAIN, playCue, type CueManager } from './local-cue-player'

const scope: CoachScope = { schemaVersion: 1, userId: 'u', runId: 'run', exerciseId: 'exercise', setOrdinal: 1, scopeEpoch: 1 }

describe('local count volume', () => {
  it.each(['count', 'countdown', 'start', 'set-end', 'safety-stop'] as const)('scales %s without changing other cues or safety', kind => {
    const playLocal = vi.fn(() => true), cancelAll = vi.fn()
    const manager = { playLocal, cancelAll, snapshot: vi.fn() } as unknown as CueManager
    const buffer = {} as AudioBuffer
    const cue: LocalCue = { id: kind, key: kind, kind, clipId: kind, triggerId: 'T14', scope,
      priority: kind === 'safety-stop' ? 'safety' : 'ordinary', atMs: 0, deadlineMs: 1000, value: null }
    expect(playCue(manager, { get: () => buffer }, cue, 0, () => true).admitted).toBe(true)
    const count = kind === 'count' || kind === 'countdown'
    expect(playLocal).toHaveBeenCalledWith(expect.objectContaining({ baseGain: count ? OFFLINE_COUNT_GAIN : 1 }))
    expect(OFFLINE_COUNT_GAIN).toBe(0.7)
    expect(cancelAll).toHaveBeenCalledTimes(kind === 'safety-stop' ? 1 : 0)
  })
})