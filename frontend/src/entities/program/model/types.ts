export type ProgramDifficulty = 'novice' | 'easy' | 'medium' | 'advanced'

export type ProgramSummary = {
  id: string
  name: string
  subtitle: string
  exerciseCount: number
  setCount: number
  durationMinutes: number
  difficulty: ProgramDifficulty
  focusTags: string[]
  recommendedToday: boolean
  imageUrl?: string
}

export type ProgramCompatibility = {
  tone: 'great' | 'okay' | 'caution'
  title: string
  description: string
}

export type ProgramExerciseLine = {
  order: number
  name: string
  load: string
  rest: string
}

export type ProgramDetails = ProgramSummary & {
  compatibility: ProgramCompatibility
  equipmentCoverage: string
  blacklistIssues: number
  exerciseLines: ProgramExerciseLine[]
  actions: {
    primary: string
    secondary: string
    save: string
    calendar: string
    builder: string
  }
}