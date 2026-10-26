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
    expect(fault).toMatchObject({ tone: 'warn', title: 'Тренер на связи' })
    expect(fault.detail).toMatch(/ошибка тренажёра — тренер при этом продолжает говорить/)
  })

  it('says plainly when the live coach is not part of this build, without jargon', () => {
    const off = coachOverview({ ...base, liveBuild: false })
    expect(off).toMatchObject({ tone: 'info', title: 'Живой тренер не подключён в этой сборке' })
    expect(off.detail).toMatch(/локальные фразы/)
    expect(coachOverview({ ...base, liveBuild: false, saved: { ...hybrid, mode: 'local' } }).tone).toBe('ok')
  })

  it('follows the live connection: connecting, refused with its reason, on air with what was said', () => {
    expect(coachOverview({ ...base, network: net('connecting') }).title).toBe('Подключаю живого тренера…')
    expect(coachOverview({ ...base, network: net('refused', { reason: 'budget' }) })).toMatchObject({ tone: 'error', detail: 'Лимит бюджета' })
    expect(coachOverview({ ...base, network: net('ready', { spoken: 12, failed: 1 }) }))
      .toEqual({ tone: 'ok', title: 'Тренер на связи', detail: 'Сказано реплик: 12 · сбоев: 1' })
  })

  it('renders the sentence as a status and the numbers as tiles', () => {
    render(<CoachOverview overview={coachOverview({ ...base, network: net('ready') })}
      tiles={[{ label: 'новых ошибок', value: '2', tone: 'error', onClick: () => undefined }]} />)
    expect(screen.getByRole('status')).toHaveTextContent('Тренер на связи')
    expect(screen.getByRole('button', { name: /2\s*новых ошибок/ })).toBeInTheDocument()
  })
})
