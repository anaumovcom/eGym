export type StrengthSetType = 'warmup' | 'work' | 'failure'

export type StrengthModeDayOption = {
  id: string
  label: string
  description: string
}

export type StrengthTrainingMode = {
  id: string
  title: string
  shortDescription: string
  goal: string
  level: string
  audience: string
  defaultDayType?: string | null
  dayOptions: StrengthModeDayOption[]
  safetyNote?: string | null
}

export type StrengthSetPlan = {
  setNumber: number
  setType: StrengthSetType
  label: string
  targetRepsLabel: string
  recommendedWeightLabel: string
  restSeconds: number
  rirLabel: string
  note: string
}
