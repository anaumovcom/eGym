import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { motorApi, type FrictionScan, type FrictionTrack } from '@/features/motor/api/motor-api'
import { FrictionArchiveTab } from './friction-archive'
import { LiveFrictionCoverage } from './friction-track-chart'
import { comparisonIssue, tightZones } from './friction-track-model'

const calibration = { zeroCounts: 0, sign: 1, nPerRaw: 0.8, mmPerPulse: .01 }
const current: FrictionTrack = {
  heightsMm: [90, 110, 130, 150, 170], speedMmS: 30, binMm: 20, zeroToleranceMm: 1,
  reference: { left: calibration, right: calibration },
  sides: { left: [8, 14, null, 9, 0], right: [0, 0, 0, 0, 17] },
  directionalN: {
    left: { up: [51, 57, 68, 52, 43], down: [49, 55, null, 50, 41] },
    right: { up: [52, 52, 52, 52, 69], down: [48, 48, 48, 48, 65] },
  },
}
const older: FrictionTrack = { ...current, sides: { ...current.sides, left: [0, 2, 0, 0, 50] },
  directionalN: { ...current.directionalN!, left: { up: [62, 68, 60, 65, 91], down: [60, 64, 60, 61, 93] } } }
const scan = (id: string, track: FrictionTrack): FrictionScan => ({ id, track, startedAt: '2026-09-10T10:00:00Z', code: 'S10', status: 'saved' })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('locates contiguous ranges per carriage without bridging holes or changed grids', () => {
  const zones = tightZones(current, 'left').map(z => [z.low, z.high, z.peakIndex])
  expect(zones).toEqual([[80, 120, 1], [140, 160, 3]])
  expect(tightZones(current, 'right').map(z => z.peakIndex)).toEqual([4])
  expect(comparisonIssue(current, older, 'twin')).toBeNull()
  expect(comparisonIssue(current, older, 'unknown')).toMatch(/источник/)
  expect(comparisonIssue(current, { ...older, speedMmS: 40 }, 'twin')).toMatch(/скорость/)
  expect(comparisonIssue(current, { ...older, reference: { left: calibration, right: { ...calibration, sign: -1 } } }, 'twin')).toMatch(/энкодера/)
  expect(comparisonIssue(current, { ...older, reference: { left: calibration, right: { ...calibration, zeroCounts: 2 } } }, 'twin')).toBeNull()
  expect(comparisonIssue(current, { ...older, reference: { left: calibration, right: { ...calibration, zeroCounts: 101 } } }, 'twin')).toMatch(/энкодера/)
  expect(comparisonIssue(current, { ...older, heightsMm: [95, 115, 135, 155, 175] }, 'twin')).toMatch(/общих высот/)
})

it('compares actual effort at the selected height, leaves one-leg gaps open and can revisit a vanished peak', async () => {
  vi.spyOn(motorApi, 'frictionTracks').mockImplementation(async (offset, source) => ({
    source: source ?? 'twin', hasMore: !source && !offset,
    items: source ? [] : offset ? [scan('before', older)] : [scan('now', current)],
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter><FrictionArchiveTab /></MemoryRouter></QueryClientProvider>)
  const plot = await screen.findByRole('slider')
  expect(plot).toHaveAttribute('aria-valuenow', '170')
  fireEvent.click(screen.getByRole('button', { name: 'Показать более ранние замеры' }))
  await screen.findAllByRole('option', { name: /10\.09\.2026/ })
  const compare = screen.getByLabelText('Сравнить с замером до регулировки')
  await within(compare).findByRole('option', { name: /10\.09\.2026/ })
  fireEvent.change(compare, { target: { value: 'before' } })
  fireEvent.click(screen.getByRole('button', { name: /Левая ШВП, 80–120 мм/ }))
  expect(plot).toHaveAttribute('aria-valuenow', '110')
  expect(within(screen.getByRole('row', { name: /Изменение среднего/ })).getByText('-10 Н')).toBeVisible()
  fireEvent.keyDown(plot, { key: 'ArrowUp' })
  expect(plot).toHaveAttribute('aria-valuenow', '130')
  expect(within(screen.getByRole('row', { name: /При подъёме/ })).getByText('68 Н')).toBeVisible()
  expect(within(screen.getByRole('row', { name: /Изменение среднего/ })).getByLabelText('Нет измерения')).toBeVisible()
  fireEvent.click(screen.getByText('Найти прежние тугие участки'))
  fireEvent.click(screen.getByRole('button', { name: 'Левая · 170 мм · было +50 Н' }))
  expect(plot).toHaveAttribute('aria-valuenow', '170')
  fireEvent.change(screen.getByLabelText('Источник'), { target: { value: 'modbus' } })
  expect(await screen.findByText('Для этого источника пока нет карты')).toBeVisible()
  expect(screen.queryByRole('slider')).toBeNull()
  client.clear()
})

it('shows live coverage only for directions that actually accumulated samples on each side', () => {
  render(<LiveFrictionCoverage coverage={{ heightsMm: [110, 130, 150], sides: { left: [0, 1, 3], right: [0, 2, 0] } }} />)
  const left = screen.getByRole('img', { name: 'Левая · оба прохода на 1 из 3 участков' })
  expect(left.querySelector('[data-pass="3"]')).toHaveAttribute('title', '150 мм · Оба прохода')
  expect(screen.getByRole('img', { name: 'Правая · оба прохода на 0 из 3 участков' })).toBeVisible()
})
