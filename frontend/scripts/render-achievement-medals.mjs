import { createHash, randomUUID } from 'node:crypto'
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { chromium } from '@playwright/test'
import { kioskDisplay } from '../e2e/kiosk-display.mjs'

// Each source is one illustrated 2×2 storyboard. The original v2 scenes serve all other series.
const root = new URL('../../backend/media/achievements/collection/', import.meta.url)
const editorial = new URL('../../backend/app/services/achievements/content/workout-titles.ru.json', import.meta.url)
const titles = JSON.parse(await readFile(editorial, 'utf8'))
const direction = JSON.parse(await readFile(new URL('scene-direction.json', root), 'utf8'))
const images = {}

async function publish(file, bytes) {
  const staging = new URL(file.href + '.' + randomUUID() + '.tmp')
  try {
    await writeFile(staging, bytes)
    await rename(staging, file)
  } finally {
    await rm(staging, { force: true })
  }
}

await mkdir(new URL('images/', root), { recursive: true })
const browser = await chromium.launch()
try {
  const page = await browser.newPage(kioskDisplay)
  for (const series of Object.keys(direction.stories)) {
    const count = titles[series].tiers.length
    const source = await readFile(new URL('storyboards/' + series + '.webp', root))
    const tiles = await page.evaluate(async ({ source, count }) => {
      const image = new Image()
      image.src = 'data:image/webp;base64,' + source
      await image.decode()
      if (count > 4 || image.width !== 1024 || image.height !== 1024) throw new Error('Invalid storyboard')
      return Array.from({ length: count }, (_, i) => {
        const canvas = document.createElement('canvas')
        canvas.width = canvas.height = 512
        canvas.getContext('2d').drawImage(image, (i % 2) * 512, Math.floor(i / 2) * 512, 512, 512, 0, 0, 512, 512)
        return canvas.toDataURL('image/webp', 0.95).split(',')[1]
      })
    }, { source: source.toString('base64'), count })
    for (const [i, tile] of tiles.entries()) {
      const id = series + ':t' + (i + 1)
      const bytes = Buffer.from(tile, 'base64')
      const hash = createHash('sha256').update(bytes).digest('hex').slice(0, 12)
      const file = id.replace(/[.:]/g, '-') + '.' + hash + '.webp'
      await publish(new URL('images/' + file, root), bytes)
      images[id] = file
    }
  }
  await publish(new URL('manifest.json', root), JSON.stringify({ images }, null, 2) + '\n')
  console.log(Object.keys(images).length + ' illustrated scenes published')
} finally {
  await browser.close()
}
