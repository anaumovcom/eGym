import { readFileSync } from 'node:fs'
import { expect } from '@playwright/test'
import { test } from './fixtures/navigation'

type Tier = Record<string, unknown> & { id: string; tier: number; title: string; threshold: number; minimumEvidenceDays?: number }
type Line = Record<string, unknown> & { id: string; name: string; group: string; groupName: string; description: string; tiers: Tier[] }

const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
const source = read('../../backend/app/services/achievements/content/v2/catalog.json')
const titles: Record<string, { name: string; tiers: string[]; phrases?: string[] }> = read('../../backend/app/services/achievements/content/workout-titles.ru.json')
const manifest = read('../../backend/media/achievements/v2/manifest.json')
const edition = read('../../backend/media/achievements/collection/manifest.json').images
function byId(id: string): Line {
  const line: Line = source.lines.find((item: Line) => item.id === id)
  return { ...line, name: titles[id].name, tiers: line.tiers.map((tier, i) => ({
    ...tier, title: titles[id].tiers[i], phrase: titles[id].phrases?.[i] ?? tier.phrase,
  })) }
}
const imageUrl = (tier: Tier) => `/api/achievements/tiers/${encodeURIComponent(tier.id)}/image?userId=alexey`
const groupNames = { journal: 'Дневник тренировок', muscle: 'Атлас мышц', calendar: 'Календарь практики', discovery: 'Открытия', return: 'Возвращения' }

// A line with its first `earned` tiers earned; the rest is redacted exactly like the backend does.
function projected(id: string, group: keyof typeof groupNames, description: string, earned: number): Line {
  const item = byId(id)
  const next = item.tiers[earned]
  const lastThreshold = item.tiers[earned - 1]?.threshold ?? 0
  const currentValue = next && earned ? lastThreshold + Math.floor((next.threshold - lastThreshold) / 2) : lastThreshold
  return {
    ...item, group, groupName: groupNames[group], description, currentValue,
    evidenceDays: earned ? 30 : 0, highestTier: earned, state: 'available', isNew: false,
    nextTierId: next?.id ?? null, progressPercent: next ? (currentValue - lastThreshold) * 100 / (next.threshold - lastThreshold) : 100,
    tiers: item.tiers.map((tier, index) => index < earned
      ? { ...tier, imageUrl: imageUrl(tier), thumbnailUrl: imageUrl(tier), audioUrl: `/audio/${tier.id}`, imageState: 'ready', audioState: 'ready',
        earned: true, earnedAt: '2026-11-05T12:00:00Z', awardedAt: '2026-11-05T12:00:00Z', status: 'earned' }
      : { ...tier, title: '', phrase: '', imageUrl: null, thumbnailUrl: null, audioUrl: null, imageState: 'locked', audioState: 'locked',
        earned: false, earnedAt: null, awardedAt: null, status: 'not_started' }),
  }
}

const full = projected('practice.workouts', 'journal', 'Здесь собираются все занятия с выполненной работой, в том числе частично завершённые.', byId('practice.workouts').tiers.length)
full.isNew = true
full.tiers.forEach((tier, i) => { tier.isNew = i < 2 })
const cards = [
  full,
  projected('start.first_workout', 'journal', 'Каждая сохранённая тренировка хотя бы с одним выполненным подходом пополняет дневник.', 1),
  projected('muscle.front-shoulders', 'muscle', 'Группа мышц — передние дельты. День засчитывается за два полных рабочих подхода или 60 секунд силового удержания с основной нагрузкой на эту группу.', 3),
  projected('rhythm.active_days', 'calendar', 'День с одной или несколькими тренировками даёт одну отметку.', 4),
  projected('practice.sets', 'journal', 'Каждый сохранённый подход с повторениями или секундами добавляет строку.', 0),
  projected('repertoire.familiar', 'discovery', 'Упражнение становится знакомым, когда встречается в три разных дня.', 0),
  projected('rhythm.return', 'return', 'После перерыва в 14 полных дней каждый новый день практики продолжает эту серию.', 0),
  projected('chapter.365_days', 'calendar', 'Глава складывается из года с первой тренировки и 40 дней практики.', 0),
]
const groups = Object.entries(groupNames).map(([id, name]) => ({ id, name }))
const counts = { lines: cards.length, tiers: cards.reduce((sum, row) => sum + row.tiers.length, 0), images: 0, audio: 0 }
const oldLine = projected('start.first_set', 'journal', 'Подходы первой коллекции.', 3)
const archived = { ...oldLine, group: 'archive', groupName: 'Архив', archived: true, tiers: [oldLine.tiers[2]] }

test('achievement collection (4K @150%) and six-tier detail', async ({ page }, testInfo) => {
  const consoleErrors: string[] = []
  const receipts: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  // Scale-provider heartbeats are fulfilled locally too; no actual device/API.
  await page.route((url) => url.pathname.startsWith('/api/scales/'), async (route) => {
    await route.fulfill({ json: { connected: false, state: 'disconnected', active: false } })
  })
  // Page routes override the read-only navigation fixture. No real API/DB/device.
  await page.route((url) => url.pathname.startsWith('/api/achievements/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    const tier = decodeURIComponent(path.split('/')[4] ?? '')
    if (path.includes('/tiers/') && path.endsWith('/image')) {
      const file = edition[tier] ?? manifest.assets[tier]?.image?.['512']
      await route.fulfill(file
        ? { contentType: 'image/webp', body: readFileSync(new URL(`../../backend/media/achievements/${edition[tier] ? 'collection' : 'v2'}/images/${file}`, import.meta.url)) }
        : { status: 404 })
    } else if (path.endsWith('/catalog')) {
      await route.fulfill({ json: { lines: [...cards, archived], total: cards.length + 1, nextCursor: null,
        computedThrough: null, isRebuilding: false, groups: [...groups, { id: 'archive', name: 'Архив' }], media: counts } })
    } else if (path.includes('/receipts/')) {
      receipts.push(route.request().url())
      await route.fulfill({ json: { isNew: false } })
    } else {
      await route.fulfill({ json: [...cards, archived].find((line) => line.id === path.split('/').at(-1)) })
    }
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  const navigation = page.getByRole('navigation', { name: 'Основная навигация' })
  await navigation.getByRole('link', { name: 'Достижения' }).click()
  await expect(navigation.getByRole('link', { name: 'Достижения' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('heading', { name: 'Достижения', exact: true })).toBeVisible()
  await expect(page.getByText('Диван взял отгул', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Получено ступеней: 6 из 6')).toBeVisible()
  await expect(page.locator('.discovery-count')).toHaveText(`${cards.length} серий`)
  const totals = page.getByLabel('Сводка коллекции')
  await expect(totals.locator('dd').nth(0)).toHaveText(`14 из ${counts.tiers}`)
  await expect(totals.locator('dd').nth(1)).toHaveText('4 из 8')

  // Every earned tier of a card has its icon and the title underneath.
  const sixTiers = page.locator('.ach-earned-tiers').first().locator('li')
  await expect(sixTiers).toHaveCount(full.tiers.length)
  for (let index = 0; index < full.tiers.length; index += 1) {
    const item = sixTiers.nth(index)
    const title = item.locator('.ach-earned-title')
    await expect(item.locator('.ach-image')).toBeVisible()
    await expect(title).toHaveText(full.tiers[index].title)
    expect(await title.evaluate((element) => element.scrollHeight <= element.clientHeight + 1)).toBe(true)
    const [icon, text] = await Promise.all([item.locator('.ach-image').boundingBox(), title.boundingBox()])
    expect(text!.y).toBeGreaterThanOrEqual(icon!.y + icon!.height - 1)
  }
  // Series conditions are browsable. Tier art, speech and reward titles unlock at the finish.
  const hidden = byId(cards[6].id)
  await expect(page.getByText(cards[6].description, { exact: true })).toBeVisible()
  await expect(page.getByText(hidden.tiers[0].title, { exact: true })).toHaveCount(0)
  await expect(page.locator('audio')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: cards[6].name })).toBeVisible()

  const overflowing = await page.locator('.ach-card').evaluateAll((nodes) => nodes.flatMap((card) => {
    const bounds = card.getBoundingClientRect()
    return [...card.querySelectorAll<HTMLElement>('*')].filter((element) => {
      const rect = element.getBoundingClientRect()
      return rect.width > 0 && rect.height > 0 && (rect.left < bounds.left - 1 || rect.right > bounds.right + 1)
    }).map((element) => `${card.querySelector('h3')?.textContent}:${element.className}`)
  }))
  expect(overflowing).toEqual([])
  const columns = await page.locator('.ach-grid').evaluate((grid) => getComputedStyle(grid).gridTemplateColumns.split(' ').length)
  expect(columns).toBeGreaterThanOrEqual(3)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('achievements-collection-4k150.png') })
  await page.getByRole('heading', { name: cards[6].name }).scrollIntoViewIfNeeded()
  await page.locator('.forma-main').evaluate((element) => element.scrollTo({ top: 0 }))

  await page.getByRole('link', { name: `Открыть достижение «${full.name}»` }).click()
  await expect(page.getByRole('heading', { name: full.name, exact: true })).toBeVisible()
  await expect(page.getByText(`Открыто ступеней — ${full.tiers.length} из ${full.tiers.length}`, { exact: true })).toBeVisible()
  await expect(page.locator('.ach-tier-detail')).toHaveCount(full.tiers.length)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('achievements-detail-4k150.png') })
  await page.getByRole('link', { name: 'Все достижения' }).click()
  await page.getByRole('button', { name: /^Мои награды/ }).click()
  await expect(page.locator('.ach-earned-card')).toHaveCount(14)
  await expect(page.locator('.discovery-count')).toHaveText('14 наград')
  await expect(page.locator('.ach-earned-card[data-rarity="common"] .ach-rarity').first()).toHaveCSS('color', 'rgb(167, 204, 237)')
  await expect.poll(() => page.locator('.ach-earned-card img').evaluateAll((images) =>
    images.filter((image) => (image as HTMLImageElement).naturalWidth === 512).length)).toBe(14)
  await page.locator('.ach-earned-card img').evaluateAll(async (nodes) => {
    await Promise.all(nodes.map((node) => (node as HTMLImageElement).decode()))
  })
  await page.screenshot({ path: testInfo.outputPath('achievements-gallery-4k150.png') })
  await page.getByRole('link', { name: 'Открыть награду «Диван взял отгул»' }).click()
  await expect(page.getByRole('heading', { name: 'Диван взял отгул', level: 1 })).toBeVisible()
  await expect(page.locator('.ach-detail-hero .ach-award-facts dd').first()).toHaveText('1 тренировка')
  await expect(page.locator('.ach-detail-hero time')).toBeVisible()
  await expect.poll(() => receipts.some((url) => url.includes('start.first_workout/receipts/detail') && new URL(url).searchParams.get('tier') === '1')).toBe(true)
  await page.goBack()
  await expect(page.locator('.ach-earned-card')).toHaveCount(14)
  await page.getByRole('button', { name: /^Новые/ }).click()
  await expect(page.locator('.ach-earned-card')).toHaveCount(2)
  await page.getByRole('button', { name: /^Архив/ }).first().click()
  await expect(page.locator('.ach-earned-card')).toHaveCount(1)
  await expect(page.locator('.ach-earned-card')).toHaveAttribute('href', '/achievements/start.first_set?tier=3')
  await expect(totals.locator('dd').nth(0)).toHaveText(`14 из ${counts.tiers}`)
  expect(consoleErrors.filter((text) => !/favicon|WebSocket|ECONNREFUSED/i.test(text))).toEqual([])
})

test('collection navigation, search and filters fit the kiosk', async ({ page, viewport }) => {
  await page.route((url) => url.pathname.startsWith('/api/scales/'), (route) => route.fulfill({ json: { active: false } }))
  await page.route((url) => url.pathname === '/api/achievements/catalog', (route) => route.fulfill({ json: {
    lines: cards.slice(4), total: cards.length - 4, nextCursor: null, isRebuilding: false,
    groups: [{ id: cards[4].group, name: cards[4].groupName }],
  } }))
  await page.goto('/')
  await page.getByRole('button', { name: 'Выбрать профиль Алексей' }).click()
  const menuLink = page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Достижения' })
  await menuLink.click()
  await expect(page.getByRole('heading', { name: cards[4].name })).toBeVisible()
  await expect(page.getByRole('button', { name: new RegExp(String(cards[4].groupName)) })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Поиск достижений' }).fill(cards[6].name)
  await expect(page.locator('.ach-card')).toHaveCount(1)
  await expect(menuLink).toBeInViewport({ ratio: 1 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport!.width)
  await expect(page.locator('.ach-card')).toBeInViewport({ ratio: 1 })
})
