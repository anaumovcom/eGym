import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import { MeasurementPlot } from './measurement-plot'
import { axis, brakeRuns, forcePoints, repeatRows } from './measurement-model'

afterEach(cleanup)
const inspect = () => within(screen.getByRole('complementary', { name: 'Подробности замера' }))

it('keeps each carriage speed and each direction, including F3 bar speeds and signed forces', () => {
  const d2 = { sides: { left: { table_up: [[90.1, 8], [45, 0]], table_down: [[42, 11]] },
    right: { table_up: [[46, -2], [92, 12]] } } }
  expect(forcePoints('D2', d2, 'left', 'up').map(p => [p.x, p.y])).toEqual([[45, 0], [90.1, 8]])
  expect(forcePoints('D2', d2, 'right', 'up')[0]).toMatchObject({ x: 46, y: -2 })
  const f3 = { points: { '-1': { left: [[73, 12]], right: [[73, 16]] } } }
  expect(forcePoints('F3', f3, 'right', 'down')[0]).toMatchObject({ x: 73, y: 16 })
  render(<MeasurementPlot code="D2" result={d2} />)
  fireEvent.click(inspect().getByRole('button', { name: 'Правая' }))
  expect(inspect().getByRole('option', { name: '92 мм/с' })).toHaveProperty('selected', true)
  fireEvent.click(screen.getByRole('button', { name: '↓ Спуск' }))
  expect(inspect().getByRole('button', { name: 'Правая' })).toBeDisabled()
  expect(inspect().getByRole('option', { name: '42 мм/с' })).toHaveProperty('selected', true)
  expect(axis([0, 0]).max).toBeGreaterThan(axis([0, 0]).min)
})

it('shows archived support without reconstructing missing breakaway forces and links to that height and source', () => {
  render(<MemoryRouter initialEntries={['/motor-calibration?tab=plots']}><MeasurementPlot code="S7" result={{ sides: { left: { map: [[700, 82]] } } }} mapSource="canopen" /></MemoryRouter>)
  expect(inspect().getByText(/сохранилось только усилие поддержки/)).toBeVisible()
  expect(inspect().getAllByText('Нет замера')).toHaveLength(3)
  expect(inspect().getByRole('link')).toHaveAttribute('href', '/motor-calibration?tab=friction&source=canopen&height=700&from=calibration')
})

it('uses recorded signed peaks and warning threshold, including a valid zero gain', () => {
  const result = { selectedK: 0, warningMm: 5, runs: [
    { k: 0, up: { peak: 1.125 }, down: { peak: -.75 }, max_mm: 1.125, rms_mm: .5, oscillation: 2 },
    { k: 3, up: { peak: -6 }, down: { peak: 2 }, max_mm: 6, rms_mm: 2, oscillation: 7 },
  ] }
  const { rerender } = render(<MeasurementPlot code="X3" result={result} />)
  expect(inspect().getByText('1,125 мм · левая выше')).toBeVisible()
  expect(inspect().getByText('0,75 мм · правая выше')).toBeVisible()
  expect(inspect().getByRole('option', { name: '0 Н/мм · выбор X3' })).toHaveProperty('selected', true)
  fireEvent.change(inspect().getByLabelText('Коэффициент выравнивания'), { target: { value: '1' } })
  expect(inspect().getByText('±5 мм · достигнут')).toBeVisible()
  rerender(<MeasurementPlot key="legacy" code="X3" result={{ runs: [{ k: 2, max_mm: 1, rms_mm: .5 }] }} />)
  expect(screen.getByText(/без разбивки на подъём и спуск/)).toBeVisible()
  expect(inspect().getByText('Не записан')).toBeVisible()
})

it('distinguishes a failed braking trial from measured zero travel and reads actual speed', () => {
  const result = { stopSpeedMmS: 20, runs: [
    { direction: 1, target_mm_s: 350, mode: 'brake', ok: false },
    { direction: -1, target_mm_s: 250, mode: 'coast', ok: true, v_mm_s: 247, brake_v_mm_s: 0, coast_mm: 41, brake_mm: 0, brake_s: 0 },
  ] }
  expect(brakeRuns(result).map(r => r.total)).toEqual([null, 41])
  render(<MeasurementPlot code="M5" result={result} />)
  expect(inspect().getByText(/путь не измерен/)).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '↓ Спуск' }))
  expect(inspect().getByText('247 мм/с')).toBeVisible()
  expect(inspect().getByText('0 мм')).toBeVisible()
  expect(inspect().getByText('0 с')).toBeVisible()
})

it('tracks completed passes separately from unstable samples and evaluates only matched triples against recorded limits', () => {
  const passes = [10, 12, null, 14, 16, 15].map((v, i) => ({ left: [v], right: [i % 2 ? 8 : 9] }))
  const limits = { up: { left: [null], right: [2] }, down: { left: [2], right: [2] } }
  const result = { heightsMm: [700], passes, spreadLimitsN: limits }
  expect(repeatRows(result, 'up')[0]).toMatchObject({ count: 2, spread: null, ok: null })
  expect(repeatRows(result, 'down')[0]).toMatchObject({ values: [12, 14, 15], spread: 3, limit: 2, ok: false })
  const { rerender } = render(<MeasurementPlot code="G4" result={{ heightsMm: [700], passes: passes.slice(0, 3), partial: true }} live />)
  expect(screen.getByText('Получено проходов · 3 из 6')).toBeVisible()
  expect(screen.getAllByLabelText('Проход не выполнен')).toHaveLength(2)
  expect(screen.getByLabelText('Недостаточно отсчётов')).toBeVisible()
  rerender(<MeasurementPlot code="G4" result={result} />)
  fireEvent.click(screen.getByRole('button', { name: '↓ Спуск' }))
  expect(inspect().getByText('Превышен')).toBeVisible()
  expect(inspect().getByText('1 из 2 оценённых')).toBeVisible()
})
