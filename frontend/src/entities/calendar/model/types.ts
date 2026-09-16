export type CalendarWorkoutStatus = 'completed' | 'partial' | 'aborted'

export type CalendarWorkoutExercise = {
  name: string
  status: string
  setCount: number
  result: string
}

export type CalendarWorkout = {
  id: number
  title: string
  status: CalendarWorkoutStatus
  startedAt: string
  finishedAt: string | null
  timeLabel: string
  duration: string
  exerciseCount: number
  setCount: number
  volume: string
  exercises: CalendarWorkoutExercise[]
}

export type CalendarDay = {
  id: string
  day: number
  inMonth: boolean
  isToday: boolean
  workouts: CalendarWorkout[]
}

export type WorkoutCalendarData = {
  month: string
  title: string
  today: string
  weekdays: string[]
  days: CalendarDay[]
  workoutCount: number
}
