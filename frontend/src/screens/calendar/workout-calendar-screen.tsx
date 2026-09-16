import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight } from 'lucide-react'
import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { CalendarDay, CalendarWorkout, WorkoutCalendarData } from '@/entities/calendar/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { useAppStore } from '@/stores/app-store'

const statusLabels: Record<CalendarWorkout['status'], string> = { completed: 'Выполнена', partial: 'Выполнена частично', aborted: 'Прервана' }
const fallbackMachine: MachineHealth = { machineState: 'ready', machineLabel: 'Загрузка статуса', leftDrive: 'connected', rightDrive: 'connected', safety: 'enabled', calibration: 'Проверка подключения...' }

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function shiftMonth(month: string, delta: number) {
  const [year, index] = month.split('-').map(Number)
  const shifted = new Date(Date.UTC(year, index - 1 + delta, 1))
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}`
}

export function formatDayTitle(dayId: string) {
  const [year, month, day] = dayId.split('-').map(Number)
  const title = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', weekday: 'long' }).format(new Date(year, month - 1, day))
  return title.charAt(0).toUpperCase() + title.slice(1)
}

function workoutsWord(count: number) {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return 'тренировка'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'тренировки'
  return 'тренировок'
}

export function WorkoutCalendarScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userId = selectedUserId ?? 'alexey'
  const month = /^\d{4}-(0[1-9]|1[0-2])$/.test(searchParams.get('month') ?? '') ? searchParams.get('month') : null

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['workout-calendar', userId, month ?? 'current'],
    queryFn: () => apiGet<WorkoutCalendarData>(`/api/calendar?userId=${encodeURIComponent(userId)}${month ? `&month=${month}` : ''}`),
  })

  function goToMonth(next: string | null) {
    setSearchParams((current) => {
      const params = new URLSearchParams(current)
      if (next) params.set('month', next)
      else params.delete('month')
      return params
    })
  }

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      {isPending ? <div className="forma-state" role="status">Загрузка календаря…</div> : null}
      {error ? (
        <div className="forma-state" role="alert">
          <p>Не удалось загрузить календарь тренировок.</p>
          <Button variant="secondary" onClick={() => void refetch()}>Повторить</Button>
        </div>
      ) : null}
      {data ? <MonthJournal key={`${userId}-${data.month}`} data={data} onMonthChange={goToMonth} /> : null}
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function MonthJournal({ data, onMonthChange }: { data: WorkoutCalendarData; onMonthChange: (month: string | null) => void }) {
  const [selectedDayId, setSelectedDayId] = useState<string | null>(null)
  const triggerRef = useRef<HTMLElement | null>(null)
  const selectedDay = data.days.find((day) => day.id === selectedDayId && day.workouts.length > 0) ?? null
  const isCurrentMonth = data.month === data.today.slice(0, 7)

  return (
    <section className="calendar-journal" aria-labelledby="calendar-title">
      <header className="calendar-header">
        <Button variant="secondary" className="calendar-nav" aria-label="Предыдущий месяц" onClick={() => onMonthChange(shiftMonth(data.month, -1))}><ChevronLeft aria-hidden="true" /></Button>
        <div className="calendar-heading">
          <h1 id="calendar-title" className="font-display font-bold text-white">{data.title}</h1>
          <p>{data.workoutCount ? `${data.workoutCount} ${workoutsWord(data.workoutCount)} за месяц` : 'В этом месяце нет завершённых тренировок'}</p>
        </div>
        <Button variant="secondary" className="calendar-nav" aria-label="Следующий месяц" onClick={() => onMonthChange(shiftMonth(data.month, 1))}><ChevronRight aria-hidden="true" /></Button>
        <Button variant="secondary" className="calendar-today" disabled={isCurrentMonth} onClick={() => onMonthChange(null)}>Сегодня</Button>
      </header>
      <div className="calendar-weekdays" aria-hidden="true">{data.weekdays.map((weekday) => <span key={weekday}>{weekday}</span>)}</div>
      <div className="calendar-grid" role="grid" aria-label={`Выполненные тренировки: ${data.title}`}>
        {Array.from({ length: data.days.length / 7 }, (_, week) => (
          <div key={week} role="row" className="calendar-week">
            {data.days.slice(week * 7, week * 7 + 7).map((day) => <DayCell key={day.id} day={day} onOpen={(element) => { triggerRef.current = element; setSelectedDayId(day.id) }} />)}
          </div>
        ))}
      </div>
      <Dialog.Root open={Boolean(selectedDay)} onOpenChange={(open) => { if (!open) setSelectedDayId(null) }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="calendar-day-panel" onCloseAutoFocus={(event) => {
            event.preventDefault()
            if (triggerRef.current?.isConnected) triggerRef.current.focus()
          }}>
            {selectedDay ? <>
              <div className="calendar-day-heading">
                <div>
                  <Dialog.Title className="font-display text-3xl font-bold text-white">{formatDayTitle(selectedDay.id)}</Dialog.Title>
                  <Dialog.Description className="mt-2 text-sm text-white/60">{selectedDay.workouts.length} {workoutsWord(selectedDay.workouts.length)} · только просмотр сохранённых результатов</Dialog.Description>
                </div>
                <Dialog.Close asChild><Button variant="secondary">Закрыть</Button></Dialog.Close>
              </div>
              <div className="calendar-day-workouts">
                {selectedDay.workouts.map((workout) => <WorkoutRecord key={workout.id} workout={workout} />)}
              </div>
            </> : null}
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  )
}

function DayCell({ day, onOpen }: { day: CalendarDay; onOpen: (element: HTMLElement) => void }) {
  const count = day.workouts.length
  const label = `${formatDayTitle(day.id)}${count ? `, ${count} ${workoutsWord(count)}` : ''}`
  const content = <>
    <span className="calendar-day-number">{day.day}{day.isToday ? <small>сегодня</small> : null}</span>
    {count ? <span className="calendar-day-mark"><span className="calendar-day-check"><Check aria-hidden="true" />{count > 1 ? <b>×{count}</b> : null}</span><span className="calendar-day-title">{day.workouts[0].title}</span>{count > 1 ? <span className="calendar-day-more">и ещё {count - 1}</span> : null}</span> : null}
  </>
  if (!count) {
    return <div role="gridcell" aria-label={label} className="calendar-day" data-in-month={day.inMonth} data-today={day.isToday}>{content}</div>
  }
  return (
    <div role="gridcell" className="calendar-day calendar-day-done" data-in-month={day.inMonth} data-today={day.isToday}>
      <button type="button" aria-label={label} aria-haspopup="dialog" onClick={(event) => onOpen(event.currentTarget)}>{content}</button>
    </div>
  )
}

function WorkoutRecord({ workout }: { workout: CalendarWorkout }) {
  return (
    <article className="calendar-workout" data-status={workout.status} aria-label={workout.title}>
      <header>
        <h3>{workout.title}</h3>
        <span className="calendar-workout-status">{statusLabels[workout.status]}</span>
      </header>
      <dl className="calendar-workout-facts">
        <div><dt>Время</dt><dd>{workout.timeLabel}</dd></div>
        <div><dt>Длительность</dt><dd>{workout.duration}</dd></div>
        <div><dt>Объём</dt><dd>{workout.volume}</dd></div>
        <div><dt>Подходы</dt><dd>{workout.setCount}</dd></div>
      </dl>
      <ol className="calendar-workout-exercises" aria-label={`Упражнения: ${workout.title}`}>
        {workout.exercises.map((exercise, index) => <li key={`${exercise.name}-${index}`} data-status={exercise.status}><span>{exercise.name}</span><span>{exercise.result}</span></li>)}
      </ol>
    </article>
  )
}
