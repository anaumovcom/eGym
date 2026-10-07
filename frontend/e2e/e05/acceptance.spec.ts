import { test as base, expect, type Page, type TestInfo } from '@playwright/test'
import { writeFile } from 'node:fs/promises'
import type { acceptance } from '../../e05-harness/main'
import type { LocalAudioSnapshot } from '../../src/features/coach/audio/local-coach-audio-manager'

declare global { interface Window { e05: typeof acceptance } }
const entry = '/e05-harness/index.html'
const aiName = 'AI-тренер: локальная диагностика'
// Narrow production CSS contributes the visible ::after text to the name.
const stopName = /^Аварийная остановка(?: СТОП)?$/
const test = base.extend<{ isolation: void }>({
  isolation: [async ({ page }, use, info) => {
    const forbidden: string[] = [], errors: string[] = [], requests: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/*', route => {
      const url = new URL(route.request().url())
      requests.push(`${route.request().method()} ${url.href}`)
      const permitted = url.origin === 'http://127.0.0.1:5179' &&
        /^\/(e05-harness\/|src\/|node_modules\/|@vite\/|@react-refresh)/.test(url.pathname) &&
        !url.pathname.startsWith('/src/app/main') && !url.pathname.startsWith('/src/app/app') &&
        !url.pathname.includes('/stores/')
      if (!permitted) { forbidden.push(`${route.request().method()} ${url.href}`); return route.abort() }
      return route.continue()
    })
    await use()
    await attachJson(info, 'isolation.json', { requests, forbidden, errors })
    expect(forbidden, 'No backend/provider/font/app-store requests, even attempted').toEqual([])
    expect(errors, 'No browser exceptions').toEqual([])
  }, { auto: true }],
})

async function open(page: Page, query = '') {
  await page.goto(entry + query)
  await expect(page.getByRole('button', { name: 'Тестовый тон', exact: true })).toBeEnabled()
}
async function state(page: Page) { return page.evaluate(() => window.e05.snapshot()) }
async function attachJson(info: TestInfo, name: string, data: unknown) {
  const path = info.outputPath(name)
  await writeFile(path, JSON.stringify(data, null, 2))
  await info.attach(name, { path, contentType: 'application/json' })
}
async function assertStop(page: Page, width: number, height: number) {
  const stop = page.getByRole('button', { name: stopName, exact: true })
  await expect(stop).toHaveCount(1)
  await expect(stop).toBeVisible()
  const box = (await stop.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.y).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(width + 1)
  expect(box.y + box.height).toBeLessThanOrEqual(height + 1)
  expect(box.height).toBeGreaterThanOrEqual(44)
  await stop.click({ trial: true })
}

async function assertMotors(page: Page, width: number, height: number) {
  const motors = page.getByLabel('Усилие на двигателях', { exact: true })
  await expect(motors).toHaveCount(1)
  await expect(motors).toBeVisible()
  const box = (await motors.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.y).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(width + 1)
  expect(box.y + box.height).toBeLessThanOrEqual(height + 1)
  // Visibility alone permits an opaque overlay. Check all readout lines and
  // actionability without dispatching a hardware-affecting click.
  await motors.click({ trial: true })
  expect(await motors.evaluate(node => [...node.querySelectorAll('span')].every(span => {
    const rect = span.getBoundingClientRect()
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)
    return hit !== null && node.contains(hit)
  }))).toBe(true)
}

for (const count of [1, 2, 3] as const) {
  test(`native OfflineAudioContext: ${count} correlated tones, mixer and restore`, async ({ page }, info) => {
    await open(page)
    const result = await page.evaluate(count => window.e05.renderOffline(count), count)
    await attachJson(info, `offline-${count}.json`, result)
    console.log(`E05 render ${count}: peak=${result.samplePeak}, rms=${result.rms}, adjacentDelta=${result.maxAdjacentDelta}, samples=${result.sampleCount}`)
    expect(result.admissions).toEqual(Array(count).fill(true))
    expect(result.finite).toBe(true)
    expect(result.sampleCount).toBe(72_000)
    expect(result.samplePeak).toBeGreaterThan(0.05)
    expect(result.samplePeak).toBeLessThan(1)
    expect(result.maxAdjacentDelta).toBeLessThan(0.025)
    const full = result.snapshots.find(({ audio }) => audio.active === count && audio.utterances.every(u => Math.abs(u.gain - u.targetGain) < 1e-6))
    expect(full, 'All voices really started and reached automation targets').toBeTruthy()
    expect(full!.audio.foreground).toBe(`tone-${count}`)
    for (const { audio } of result.snapshots) {
      const voices = audio.utterances.filter(u => u.state === 'started')
      if (!voices.length) continue
      const latest = voices.reduce((a, b) => a.startOrdinal! > b.startOrdinal! ? a : b)
      expect(audio.foreground).toBe(latest.id)
      for (const u of voices) {
        expect(u.coefficient).toBeCloseTo(u.id === latest.id ? 1 : 0.65 / (voices.length - 1), 8)
        expect(Number.isFinite(u.gain)).toBe(true)
      }
    }
    // Notifications bracket remix at the SAME native audio time: no value jump.
    let sameTimeChecks = 0
    const restores: { id: string; time: number; gain: number; target: number; midpointError: number }[] = []
    for (let i = 1; i < result.events.length; i++) {
      const prev = result.events[i - 1], next = result.events[i]
      for (const u of next.audio.utterances) {
        const before = prev.audio.utterances.find(v => v.id === u.id)
        if (!before || before.state !== 'started' || u.state !== 'started') continue
        if (prev.time === next.time) { expect(u.gain).toBeCloseTo(before.gain, 7); sameTimeChecks++ }
        if (u.targetGain > before.targetGain) {
          // All preceding attacks settled before these natural endings. The
          // first post-end notification must retain the prior anchored value.
          expect(before.gain).toBeCloseTo(before.targetGain, 7)
          expect(u.gain).toBeCloseTo(before.gain, 7)
          const midpoint = result.snapshots.find(s => s.time >= next.time + 0.07 && s.time <= next.time + 0.10)
          const midVoice = midpoint?.audio.utterances.find(v => v.id === u.id)
          expect(midVoice).toBeTruthy()
          const expected = u.gain + (u.targetGain - u.gain) * (midpoint!.time - next.time) / 0.15
          expect(midVoice!.gain).toBeCloseTo(expected, 5)
          restores.push({ id: u.id, time: next.time, gain: u.gain, target: u.targetGain, midpointError: Math.abs(midVoice!.gain - expected) })
        }
      }
    }
    expect(sameTimeChecks).toBeGreaterThan(0)
    if (count > 1) expect(restores.length, 'Natural ended events restore remaining voice over 150ms').toBeGreaterThan(0)
    // Reconstruct only target-change envelopes from the event log, then verify
    // native post-GainNode PCM taps against them (50ms attack / 150ms restore).
    let pcmGainMaxError = 0
    for (const probe of result.probes) {
      let target = 0, from = 0, start = 0, duration = 0.05, initialized = false
      for (const event of result.events) {
        if (event.time > probe.time) break
        const voice = event.audio.utterances.find(u => u.id === probe.id && u.state === 'started')
        if (!voice || (initialized && voice.targetGain === target)) continue
        duration = initialized && voice.targetGain > target ? 0.15 : 0.05
        target = voice.targetGain; from = voice.gain; start = event.time; initialized = true
      }
      const expected = from + (target - from) * Math.min(1, (probe.time - start) / duration)
      pcmGainMaxError = Math.max(pcmGainMaxError, Math.abs(probe.gain - expected))
    }
    expect(result.probes.length).toBeGreaterThan(50)
    expect(pcmGainMaxError, 'Actual rendered PCM obeys attack/duck/continuous restore envelopes').toBeLessThan(0.0001)
    const last = result.snapshots.at(-1)!.audio
    expect(last.counters.started).toBe(count)
    expect(last.counters.finished).toBe(count)
    expect(last.active).toBe(0)
    await attachJson(info, 'render-summary.json', { count, samplePeak: result.samplePeak, rms: result.rms,
      maxAdjacentDelta: result.maxAdjacentDelta, pcmGainMaxError, fullCoefficients: full!.audio.utterances.map(u => u.coefficient), sameTimeChecks, restores })
  })
}

test('real AudioContext: trusted gestures, verified fixtures, overlap, mute and safety cancel', async ({ page }, info) => {
  await open(page)
  expect(await page.evaluate(() => window.e05.contextState())).toBeNull()
  const ai = page.getByRole('button', { name: aiName, exact: true })
  await ai.click()
  await expect(page.getByLabel('Локальная диагностика AI-тренера', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.e05.contextState())).toBeNull()
  await page.keyboard.press('Escape')
  await expect(ai).toBeFocused()
  await page.getByRole('button', { name: 'Подготовить тестовые клипы', exact: true }).click()
  expect(await page.evaluate(() => window.e05.contextState())).toBeNull()
  expect((await state(page)).audio).toBeNull()
  await page.getByRole('button', { name: 'Тестовый тон', exact: true }).click()
  await expect.poll(async () => (await state(page)).audio?.counters.started).toBe(1)
  await expect.poll(async () => (await state(page)).audio?.counters.finished).toBe(1)
  expect((await state(page)).prepared.entries).toBe(2)
  expect((await state(page)).prepared.bytes).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Подготовить тестовые клипы', exact: true }).click()
  expect((await state(page)).audio!.counters.started).toBe(1)
  const observations: LocalAudioSnapshot[] = []
  // Browser-side event collection cannot miss the short three-tone overlap.
  await page.evaluate(() => { window.e05.history.length = 0 })
  await page.getByRole('button', { name: 'Перекрытие трёх тонов', exact: true }).click()
  await expect.poll(async () => (await state(page)).audio?.counters.finished).toBe(4)
  observations.push(...await page.evaluate(() => window.e05.history))
  expect(observations.some(audio => audio.active === 3 && audio.utterances.filter(u => u.state === 'started').map(u => u.coefficient).join(',') === '0.325,0.325,1')).toBe(true)
  await page.getByRole('button', { name: 'Перекрытие трёх тонов', exact: true }).click()
  await expect.poll(async () => (await state(page)).audio?.active).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Mute TEST', exact: true }).click()
  const muted = await state(page)
  expect(muted.reason).toBe('mute'); expect(muted.audio!.active).toBe(0); expect(muted.audio!.pending).toBe(0)
  expect(muted.audio!.muted).toBe(true)
  const starts = muted.audio!.counters.started
  await expect(page.getByRole('button', { name: 'Тестовый тон', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Unmute TEST', exact: true }).click()
  expect((await state(page)).audio!.counters.started).toBe(starts)
  await page.getByRole('button', { name: 'Перекрытие трёх тонов', exact: true }).click()
  await expect.poll(async () => (await state(page)).audio?.active).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Open TEST safety modal', exact: true }).click()
  const safe = await state(page)
  expect(safe.reason).toBe('safety'); expect(safe.audio!.active).toBe(0); expect(safe.audio!.pending).toBe(0)
  expect(safe.audio!.counters.cancelled).toBeGreaterThan(0)
  expect(safe.paidRequests).toBe(0)
  expect(await page.evaluate(() => window.e05.contextState())).toBe('running')
  await page.getByRole('button', { name: 'Close TEST safety modal', exact: true }).click()
  expect((await state(page)).audio!.active).toBe(0)
  expect((await state(page)).audio!.counters.started).toBe(safe.audio!.counters.started)
  await page.getByRole('button', { name: 'Перекрытие трёх тонов', exact: true }).click()
  await expect.poll(async () => (await state(page)).audio?.active).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Остановить тест', exact: true }).click()
  const stopped = await state(page)
  expect(stopped.reason).toBe('cancelled'); expect(stopped.audio!.active).toBe(0); expect(stopped.audio!.pending).toBe(0)
  expect(await page.evaluate(() => window.e05.commands)).toEqual([])
  const activations = await page.evaluate(() => window.e05.activations)
  expect(activations.length).toBe(5)
  for (const activation of activations) {
    expect(activation.active).toBe(true); expect(activation.trusted).toBe(true); expect(activation.after).toBe('running')
  }
  await attachJson(info, 'real-context.json', { activations, observations, muted, safe, stopped,
    fixtures: await page.evaluate(() => window.e05.fixtureCatalog) })
})

for (const zoom of [false, true]) for (const physicalWidth of [360, 722, 1024, 1920, 3840]) for (const scale of [1, 1.25, 1.5]) for (const compact of [false, true]) {
  test.describe(`${zoom ? 'zoom emulation' : 'rem scale'} ${physicalWidth}/${scale}/${compact}`, () => {
  // Desktop zoom equivalence: fixed physical output, reduced CSS viewport,
  // increased device pixel ratio. This is not Chromium's menu zoom control.
  test.use({ deviceScaleFactor: zoom ? scale : 1 })
  test(`actual shell + AI popover: ${physicalWidth}px scale ${scale} ${compact ? 'compact' : 'normal'}`, async ({ page }, info) => {
    const physicalHeight = physicalWidth >= 3840 ? 2160 : physicalWidth >= 1920 ? 1080 : 900
    const width = zoom ? Math.floor(physicalWidth / scale) : physicalWidth
    const height = zoom ? Math.floor(physicalHeight / scale) : physicalHeight
    await page.setViewportSize({ width, height })
    await open(page, `?scale=${zoom ? 1 : scale}&compact=${compact ? 1 : 0}`)
    await assertStop(page, width, height)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1)
    const ai = page.getByRole('button', { name: aiName, exact: true })
    await expect(ai).toBeInViewport()
    await ai.focus(); await page.keyboard.press('Enter')
    const popover = page.getByLabel('Локальная диагностика AI-тренера', { exact: true })
    await expect(popover).toBeVisible()
    await assertStop(page, width, height)
    await assertMotors(page, width, height)
    await expect(popover).toBeVisible()
    const box = (await popover.boundingBox())!
    const protectedBottom = await ai.evaluate(node => Math.max(
      node.closest('.forma-system-dock')!.getBoundingClientRect().bottom,
      node.closest('header')!.getBoundingClientRect().bottom,
    ))
    expect(box.y).toBeGreaterThanOrEqual(protectedBottom + 7)
    expect(box.y + box.height).toBeLessThanOrEqual(height - 11)
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1)
    expect(await popover.evaluate(node => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(1)
    await page.screenshot({ path: info.outputPath('ai-popover.png') })
    if (zoom && physicalWidth === 360 && scale === 1.5) {
      // Reflow the already-open native portal, without close/reopen masking
      // stale geometry or a trigger-only anchor on wrapped headers.
      await page.setViewportSize({ width: width + 120, height: height - 60 })
      await expect.poll(async () => {
        const panel = (await popover.boundingBox())!
        const bottom = await ai.evaluate(node => node.closest('header')!.getBoundingClientRect().bottom)
        return panel.y >= bottom + 7 && panel.y + panel.height <= height - 71
      }).toBe(true)
      await assertStop(page, width + 120, height - 60)
      await assertMotors(page, width + 120, height - 60)
      await expect(popover).toBeVisible()
      await page.setViewportSize({ width, height })
      await expect.poll(async () => {
        const panel = (await popover.boundingBox())!
        return panel.x >= 0 && panel.x + panel.width <= width + 1 && panel.y + panel.height <= height - 11
      }).toBe(true)
      await assertStop(page, width, height)
      await assertMotors(page, width, height)
    }
    await page.keyboard.press('Escape')
    await expect(popover).toHaveCount(0); await expect(ai).toBeFocused()
    // Open safety while AI is open, without an outside click pre-closing it.
    await ai.press('Space'); await expect(popover).toBeVisible()
    await assertStop(page, width, height)
    await assertMotors(page, width, height)
    await page.evaluate(() => window.e05.openSafety())
    const dialog = page.getByRole('dialog', { name: 'TEST safety modal — no motor', exact: true })
    await expect(dialog).toBeVisible(); await expect(popover).toHaveCount(0)
    await expect(page.getByRole('button', { name: aiName, exact: true })).toBeDisabled()
    await assertStop(page, width, height)
    await assertMotors(page, width, height)
    await page.getByRole('button', { name: stopName, exact: true }).focus()
    for (const key of ['Tab', 'Tab', 'Shift+Tab', 'Shift+Tab']) {
      await page.keyboard.press(key)
      expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true)
    }
    await page.screenshot({ path: info.outputPath('safety-modal.png') })
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(page.getByRole('button', { name: aiName, exact: true })).toBeEnabled()
    expect(await page.evaluate(() => window.e05.contextState())).toBeNull()
    expect(await page.evaluate(() => window.e05.commands)).toEqual([])
    await assertStop(page, width, height)
    await attachJson(info, 'layout.json', { width, height, physicalWidth, physicalHeight, scale, compact,
      scaleMethod: zoom ? 'desktop zoom emulation: CSS viewport / scale, deviceScaleFactor = scale' : 'root rem font scale',
      rootFontSize: await page.evaluate(() => getComputedStyle(document.documentElement).fontSize), protectedBottom, popover: box })
  })
  })
}