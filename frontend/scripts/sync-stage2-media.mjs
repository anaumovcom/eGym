import { cpSync, existsSync, mkdirSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'

const frontendRoot = resolve(import.meta.dirname, '..')
const repoRoot = resolve(frontendRoot, '..')
const exercisesRoot = join(repoRoot, 'exercises')
const publicRoot = join(frontendRoot, 'public', 'mock-assets', 'exercises')

const stage2MediaSlugs = [
  'barbell-floor-press',
  'barbell-bench-press',
  'machine-pulldown',
  'machine-seated-cable-row',
  'underhand-pulldown',
  'barbell-curl',
  'forearm-plank',
  'forward-lunges',
  'barbell-front-squat-olympic',
  'barbell-heels-up-back-squat',
  'smith-machine-bench-press',
]

let copiedFiles = 0

for (const slug of stage2MediaSlugs) {
  const sourceDir = join(exercisesRoot, slug)

  if (!existsSync(sourceDir)) {
    continue
  }

  const targetDir = join(publicRoot, slug)
  mkdirSync(targetDir, { recursive: true })

  const mediaFiles = readdirSync(sourceDir).filter((fileName) => fileName.toLowerCase().endsWith('.mp4'))

  for (const fileName of mediaFiles) {
    cpSync(join(sourceDir, fileName), join(targetDir, fileName), { force: true })
    copiedFiles += 1
  }
}

console.log(`Copied ${copiedFiles} media files into ${publicRoot}`)