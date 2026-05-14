export type CalendarViewMode = 'week' | 'month'

export type CalendarDayStatus = 'completed' | 'planned' | 'skipped' | 'rest' | 'overload' | 'today' | 'empty'

export type CalendarDayCard = {
  id: string
  dateLabel: string
  title: string
  badges: string[]
  status: CalendarDayStatus
  readinessPercent?: number
  duration?: string
  exerciseCount?: number
  selected?: boolean
}

export type CalendarDayDetails = {
  dateLabel: string
  title: string
  subtitle: string
  exerciseCount: number
  setCount: number
  duration: string
  targetMuscles: string
  statusText: string
  readinessPercent: number
  recommendation: string
}

export type WorkoutCalendarData = {
  mode: CalendarViewMode
  title: string
  legend: string[]
  days: CalendarDayCard[]
  selectedDayId: string
  selectedDay: CalendarDayDetails
  quickActions: string[]
  summary: Array<{ label: string; value: string }>
  muscleBalance: Array<{ label: string; value: string; tone: 'low' | 'medium' | 'high' }>
}