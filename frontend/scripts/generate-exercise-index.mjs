import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

const frontendRoot = resolve(import.meta.dirname, '..')
const repoRoot = resolve(frontendRoot, '..')
const exercisesRoot = join(repoRoot, 'exercises')
const translationsPath = join(repoRoot, 'exercise_name_translations.csv')
const outputDir = join(frontendRoot, 'src', 'mocks', 'generated')
const outputPath = join(outputDir, 'exercises.generated.ts')

function escapeString(value) {
  return JSON.stringify(value ?? '')
}

function parseCsv(text) {
  const rows = text.split(/\r?\n/).filter(Boolean)
  const [, ...dataRows] = rows
  const map = new Map()

  for (const row of dataRows) {
    const [slug, nameEn, nameRu] = row.split(';')

    if (!slug) {
      continue
    }

    map.set(slug, {
      nameEn: nameEn ?? '',
      nameRu: nameRu ?? '',
    })
  }

  return map
}

function normalizeDifficulty(value) {
  if (value === 'Beginner' || value === 'Intermediate' || value === 'Advanced') {
    return value
  }

  return 'Intermediate'
}

function normalizeForce(value) {
  if (value === 'Push' || value === 'Pull' || value === 'Static' || value === 'Stretch') {
    return value
  }

  return 'Static'
}

function normalizeMechanic(value) {
  if (value === 'Compound' || value === 'Isolation') {
    return value
  }

  return 'Mobility'
}

function toGuideArray(source, key) {
  const value = source?.[key]
  return Array.isArray(value) ? value.filter((item) => typeof item === 'string' && item.length > 0) : []
}

function buildVideoEntries(slug, json, dirPath) {
  const files = readdirSync(dirPath, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith('.mp4'))
    .map((entry) => entry.name)

  const declaredFiles = [...(json.male_videos ?? []), ...(json.female_videos ?? [])]
  const allFiles = Array.from(new Set([...declaredFiles, ...files]))

  return allFiles.map((fileName) => ({
    fileName,
    url: `/mock-assets/exercises/${slug}/${fileName}`,
    gender: fileName.startsWith('female-') ? 'female' : 'male',
    view: fileName.includes('-front') ? 'front' : 'side',
  }))
}

function buildEntry(slug, translations) {
  const dirPath = join(exercisesRoot, slug)
  const jsonPath = join(dirPath, `${slug}.json`)
  const raw = readFileSync(jsonPath, 'utf8')
  const parsed = JSON.parse(raw)
  const translated = translations.get(slug)
  const videos = buildVideoEntries(slug, parsed, dirPath)

  return {
    slug,
    name: parsed.name ?? translated?.nameEn ?? slug,
    nameRu: parsed.name_ru ?? translated?.nameRu ?? parsed.name ?? slug,
    equipment: parsed.equipment ?? 'Bodyweight',
    difficulty: normalizeDifficulty(parsed.difficulty),
    force: normalizeForce(parsed.force),
    grips: parsed.grips ?? 'Neutral',
    mechanic: normalizeMechanic(parsed.mechanic),
    muscles: Array.isArray(parsed.muscles) ? parsed.muscles : [],
    steps: Array.isArray(parsed.steps) ? parsed.steps : [],
    guide: {
      setup: toGuideArray(parsed.guide, 'Setup'),
      howToPerform: toGuideArray(parsed.guide, 'How to Perform'),
      technique: toGuideArray(parsed.guide, 'Technique'),
      thingsToAvoid: toGuideArray(parsed.guide, 'Things to Avoid'),
    },
    videos,
  }
}

function renderItem(item) {
  const videos = item.videos
    .map(
      (video) =>
        `    { fileName: ${escapeString(video.fileName)}, url: ${escapeString(video.url)}, gender: ${escapeString(video.gender)}, view: ${escapeString(video.view)} }`,
    )
    .join(',\n')

  const stringArray = (values, indent = '    ') => values.map((value) => `${indent}${escapeString(value)}`).join(',\n')

  return `  {\n    slug: ${escapeString(item.slug)},\n    name: ${escapeString(item.name)},\n    nameRu: ${escapeString(item.nameRu)},\n    equipment: ${escapeString(item.equipment)},\n    difficulty: ${escapeString(item.difficulty)},\n    force: ${escapeString(item.force)},\n    grips: ${escapeString(item.grips)},\n    mechanic: ${escapeString(item.mechanic)},\n    muscles: [\n${stringArray(item.muscles)}\n    ],\n    steps: [\n${stringArray(item.steps)}\n    ],\n    guide: {\n      setup: [\n${stringArray(item.guide.setup, '        ')}\n      ],\n      howToPerform: [\n${stringArray(item.guide.howToPerform, '        ')}\n      ],\n      technique: [\n${stringArray(item.guide.technique, '        ')}\n      ],\n      thingsToAvoid: [\n${stringArray(item.guide.thingsToAvoid, '        ')}\n      ],\n    },\n    videos: [\n${videos}\n    ],\n  }`
}

function main() {
  const translations = parseCsv(readFileSync(translationsPath, 'utf8'))
  const slugs = readdirSync(exercisesRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort((left, right) => left.localeCompare(right))

  const items = slugs.map((slug) => buildEntry(slug, translations))

  mkdirSync(outputDir, { recursive: true })

  const fileText = `export type GeneratedExerciseEntry = {\n  slug: string\n  name: string\n  nameRu: string\n  equipment: string\n  difficulty: 'Beginner' | 'Intermediate' | 'Advanced'\n  force: 'Push' | 'Pull' | 'Static' | 'Stretch'\n  grips: string\n  mechanic: 'Compound' | 'Isolation' | 'Mobility'\n  muscles: string[]\n  steps: string[]\n  guide: {\n    setup: string[]\n    howToPerform: string[]\n    technique: string[]\n    thingsToAvoid: string[]\n  }\n  videos: Array<{\n    fileName: string\n    url: string\n    gender: 'male' | 'female'\n    view: 'side' | 'front'\n  }>\n}\n\nexport const generatedExerciseEntries = [\n${items.map(renderItem).join(',\n')}\n] satisfies GeneratedExerciseEntry[]\n\nexport const generatedExerciseEntryCount = ${items.length}\n\nexport const generatedExerciseSource = ${escapeString(relative(frontendRoot, exercisesRoot).replace(/\\/g, '/'))}\n`

  writeFileSync(outputPath, fileText, 'utf8')
  console.log(`Generated ${items.length} exercises -> ${outputPath}`)
}

main()