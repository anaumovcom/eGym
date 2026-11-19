import { readdirSync } from 'node:fs'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { motorApi, type CalibrationLog, type SetObservation } from '@/features/motor/api/motor-api'
import { CalibrationGuide } from './calibration-guide'
import { ExerciseObservations } from './exercise-observations'

afterEach(() => vi.restoreAllMocks())

it('has a distinct generated illustration and a readable caption for every catalog image', () => {
  const images = readdirSync('public/calibration-guide').filter(name => name.endsWith('.webp'))
  expect(images.length).toBeGreaterThan(65)
  for (const name of images) {
    const code = name.slice(0, -5)
    const html = renderToStaticMarkup(<CalibrationGuide code={code} title={code} />)
    expect(html).toContain(`/calibration-guide/${name}`)
    expect(html).toMatch(/<figcaption>[^<]{40,}/)
  }
})

it('shows actual sides and limits, breaks lines across a pause and keeps twin and machine records separate', async () => {
  const record: SetObservation = { id: 'set1', startedAt: '2026-11-18T08:00:00Z', source: 'twin', exerciseName: 'Жим', exerciseSlug: 'press',
    profileVersion: 3, setNumber: 2, status: 'completed', reason: null, mode: 'constant', targetReps: 8,
    loadDirection: 'down', initialKg: 8, lowerMm: 100, upperMm: 900, fixedMm: null, startPoint: 'lower',
    elapsedS: 20, workS: 10, validFrames: 40, invalidFrames: 1, segments: 2, maxGapMs: 80,
    fullReps: 3, partialReps: 1, minHeightMm: 120, maxHeightMm: 880, maxSkewMm: 7, skewHeightMm: 600,
    upMmS: [150, 155], downMmS: [100, 110], skewWarningMm: 5, ascentLimitMmS: 700, descentLimitMmS: 400 }
  const log: CalibrationLog = { t: [1, 2, 9, 10], xL: [10, 20, 20, 10], xR: [10, 21, 20, 11], vL: [20, 30, -10, -20], vR: [19, 29, -11, -21],
    fL: [50, 52, 55, 60], fR: [49, 51, 54, 59], loadKg: [4, 8, 8, 8], targetKg: [8, 8, 8, 8], segment: [1, 1, 2, 2] }
  vi.spyOn(motorApi, 'observations').mockImplementation(async source => ({ items: source === 'twin' ? [record] : [], hasMore: false }))
  vi.spyOn(motorApi, 'observation').mockResolvedValue({ ...record, trace: log })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter><ExerciseObservations adapter="twin" /></MemoryRouter></QueryClientProvider>)
  expect(await screen.findByRole('heading', { name: 'Жим · подход 2' })).toBeVisible()
  expect(screen.getByText('0,15 / 0,155 м/с')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Карта трения по высоте' })).toHaveAttribute('href', '/?tab=friction&source=twin&height=600')
  const chart = await screen.findByRole('region', { name: 'График подхода' })
  expect(chart.querySelector('svg path')?.getAttribute('d')?.match(/M/g)).toHaveLength(2)
  fireEvent.click(within(chart).getByRole('button', { name: 'Нагрузка' }))
  expect(within(chart).getByText('Нагрузка, кг')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Тренажёр · Modbus' }))
  expect(await screen.findByText(/Записей для источника «Тренажёр · Modbus» пока нет/)).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Жим · подход 2' })).not.toBeInTheDocument()
})
