import { expect, test } from '@playwright/test'
import { DEFAULT_COACH_PREFERENCES } from '../src/features/coach/model/preferences'

test('downloads the shipped Russian recordings once; reload and audition never request speech', async ({ page, context, baseURL }) => {
  test.setTimeout(90_000)
  const requests: string[] = [], unexpected: string[] = []
  let installed = false
  await page.route(url => url.pathname === '/src/main.tsx', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/e2e/fixtures/coach-pack-screen.tsx"' }))
  await page.route(url => url.pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() === 'GET') {
      if (path === '/api/coach/users/coach-e2e/settings') return installed ? route.abort('internetdisconnected') : route.fulfill({ json: { ...DEFAULT_COACH_PREFERENCES, enabled: true, consentVersion: 1 } })
      if (!installed && path.startsWith('/api/coach/packs/ru-base/')) { requests.push(path); return route.continue() }
    }
    unexpected.push(path); return route.abort()
  })
  // Observe real playback in this disposable browser context. No fake clock, synthetic unlock or mocked audio.
  await page.addInitScript(() => {
    const w = window as Window & { played?: number[] }; w.played = []
    const start = AudioBufferSourceNode.prototype.start
    AudioBufferSourceNode.prototype.start = function (...args) { w.played!.push(this.buffer?.duration ?? 0); return start.apply(this, args) }
  })
  await page.goto(process.env.EGYM_E2E_BASE_URL ?? baseURL ?? 'http://127.0.0.1:5173')
  await expect(page.getByRole('button', { name: 'Скачать голосовой пакет' })).toBeEnabled()
  expect(await page.evaluate(async () => {
    const path = '/src/features/runtime/lib/exercise-event-sounds.ts'
    const { exerciseSoundSources } = await import(path)
    return Object.values(exerciseSoundSources).map(src => typeof src === 'string' && /^data:audio\/[a-z0-9.+-]+;base64,/.test(src))
  })).toEqual([true, true, true, true])
  expect(requests).toEqual([])
  await page.getByRole('button', { name: 'Скачать голосовой пакет' }).click()
  await expect(page.getByTestId('coach-pack-status')).toContainText('Готово к воспроизведению: 129/129', { timeout: 60_000 })
  expect(requests[0]).toBe('/api/coach/packs/ru-base/manifest')
  expect(new Set(requests).size).toBe(requests.length)
  installed = true
  await page.reload()
  await expect(page.getByText(/Скачанные записи можно слушать/)).toBeVisible()
  await expect(page.getByTestId('coach-pack-status')).toContainText('129/129')
  await context.setOffline(true)
  try {
    await page.getByLabel('Фраза пакета').selectOption('count-2')
    await page.getByRole('button', { name: 'Прослушать', exact: true }).click()
    await expect.poll(() => page.evaluate(() => (window as Window & { played: number[] }).played.at(-1) ?? 0)).toBeGreaterThan(0)
    await expect(page.getByRole('button', { name: 'Прослушать', exact: true })).toBeEnabled()
    const before = await page.evaluate(() => (window as Window & { played: number[] }).played.length)
    await page.getByRole('button', { name: 'Тест: подтвердить повтор' }).click()
    await expect(page.getByTestId('rep-result')).toHaveText('count-1: admitted')
    await expect.poll(() => page.evaluate(() => (window as Window & { played: number[] }).played.length)).toBeGreaterThan(before)
    expect(unexpected).toEqual([])
  } finally { await context.setOffline(false) }
})