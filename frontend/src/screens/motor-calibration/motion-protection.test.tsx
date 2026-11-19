import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { motorApi, type CalibrationLog, type FaultCase } from '@/features/motor/api/motor-api'
import { FaultRehearsal } from './fault-rehearsal'
import { SessionChart } from './session-chart'

afterEach(() => vi.restoreAllMocks())

const log: CalibrationLog = {
  t: [0, 1, 2, 3], xL: [0, 700, 704, 0], xR: [0, 696, 701, 0], vL: [0, 1, 2, 0], vR: [0, 1, 2, 0],
  fL: [0, 90, 95, 0], fR: [0, 90, 95, 0],
}

it('shows only fixed-hold frames and distinguishes aligned skew from historical readings', () => {
  const { rerender } = render(<SessionChart code="H3" log={{ ...log, holdTargetMm: [null, 700, 700, null], skewMm: [null, 0, 0, null] }} />)
  expect(screen.getByRole('img', { name: 'Отклонение от фиксации во времени, от 1 до 2 секунд' })).toBeVisible()
  expect(screen.getByRole('slider', { name: 'Момент записи' })).toHaveAttribute('max', '1')
  expect(screen.getByText(/Зелёная полоса ±6 мм/)).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Перекос' }))
  fireEvent.change(screen.getByRole('slider'), { target: { value: '1' } })
  expect(screen.getByText('Левая минус правая')).toHaveTextContent('0')
  expect(screen.getByText(/совмещены по времени/)).toBeVisible()
  rerender(<SessionChart code="X3" log={log} />)
  expect(screen.queryByRole('button', { name: 'Отклонение от фиксации' })).toBeNull()
  expect(screen.getByText(/Архивная запись/)).toBeVisible()
  fireEvent.change(screen.getByRole('slider'), { target: { value: '1' } })
  expect(screen.getByText('Левая минус правая')).toHaveTextContent('4')
})

it('changes the fault and inspected frame without starting a calibration', async () => {
  const aligned: FaultCase = { id: 'level', title: 'Ровный быстрый ход', description: 'Последовательный опрос', expected: 'ok', actual: 'ok',
    matches: true, detail: '', frames: [{ ms: 0, rawMm: -18, deltaMm: null, state: 'ok' }, { ms: 40, rawMm: -18, deltaMm: 0, state: 'ok' }] }
  const lag: FaultCase = { id: 'left', title: 'Отстаёт левая каретка', description: 'Растёт перекос', expected: 'skew', actual: 'skew',
    matches: true, detail: 'Правая выше', frames: [{ ms: 0, rawMm: 0, deltaMm: 0, state: 'ok' }, { ms: 40, rawMm: -18, deltaMm: -18, state: 'stop' }] }
  const read = vi.spyOn(motorApi, 'faultRehearsal').mockResolvedValue({ version: 7, warningMm: 5, criticalMm: 15, cycleMs: 40, cases: [aligned, lag] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><FaultRehearsal version={7} /></QueryClientProvider>)
  const panel = within(await screen.findByRole('region', { name: 'Моделирование отказов' }))
  expect(await panel.findByText('Остановка по перекосу')).toBeVisible()
  fireEvent.change(panel.getByRole('combobox'), { target: { value: 'level' } })
  expect(panel.getByRole('status')).toHaveTextContent('Ровный ход')
  fireEvent.change(panel.getByRole('slider'), { target: { value: '0' } })
  expect(panel.getByText('Ожидание пары')).toBeVisible()
  expect(read).toHaveBeenCalledTimes(1)
  expect(panel.queryByRole('button')).toBeNull()
})
