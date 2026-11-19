import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { NetworkSnapshot } from '../live/coach-network-client'
import type { CoachPreferences } from '../model/preferences'
import { CoachOverview, coachOverview, type OverviewInput } from './coach-panel-overview'

const hybrid = { enabled: true, mode: 'hybrid' } as CoachPreferences
const base: OverviewInput = { liveBuild: true, saved: hybrid, reason: 'ready', network: null, workout: false }
const net = (state: NetworkSnapshot['state'], extra: Partial<NetworkSnapshot> = {}) =>
  ({ state, reason: null, spoken: 0, failed: 0, degraded: false, ...extra }) as NetworkSnapshot

describe('coachOverview — one plain sentence for every state', () => {
  it('explains why the coach is silent before anything else', () => {
    const safety = coachOverview({ ...base, reason: 'safety', network: net('ready') })
    expect(safety).toMatchObject({ tone: 'warn', title: 'Тренер молчит: аварийная остановка' })
    expect(safety.detail).toMatch(/снова заговорит/)
    expect(coachOverview({ ...base, reason: 'audio_locked' }).detail).toMatch(/Нажмите/)
    expect(coachOverview({ ...base, saved: { ...hybrid, enabled: false } }).title).toBe('Тренер выключен')
  })

  it('reports a machine error but says the coach keeps talking (D-V12.7)', () => {
    const fault = coachOverview({ ...base, network: net('ready', { spoken: 3 }), machineNotices: ['faultCode'] })
    expect(fault).toMatchObject({ tone: 'warn', title: 'Локальный голос включён' })
    expect(fault.detail).toMatch(/ошибка тренажёра — тренер при этом продолжает говорить/)
  })

  it('explains how to fix a missing recording without a workout download', () => {
    expect(coachOverview({ ...base, reason: 'missing_clip' })).toMatchObject({ tone: 'warn', title: 'Нет скачанной записи' })
  })

  it('does not present historical live state as a workout mode', () => {
    for (const state of ['connecting', 'refused', 'ready'] as const) expect(coachOverview({ ...base, network: net(state), workout: true }).title).toBe('Тренер работает локально')
  })

  it('renders the sentence as a status and the numbers as tiles', () => {
    render(<CoachOverview overview={coachOverview({ ...base, network: net('ready') })}
      tiles={[{ label: 'новых ошибок', value: '2', tone: 'error', onClick: () => undefined }]} />)
    expect(screen.getByRole('status')).toHaveTextContent('Локальный голос включён')
    expect(screen.getByRole('button', { name: /2\s*новых ошибок/ })).toBeInTheDocument()
  })
})
