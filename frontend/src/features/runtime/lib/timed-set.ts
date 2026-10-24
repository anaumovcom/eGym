/** "45 сек", "2 мин", "2 мин 30 сек". */
export function formatTimedSeconds(seconds: number) {
  const total = Math.max(0, Math.round(seconds))
  if (total < 60) {
    return `${total} сек`
  }
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return rest ? `${minutes} мин ${rest} сек` : `${minutes} мин`
}

/** Countdown clock: "0:45", "10:00", "1:02:03". */
export function formatTimerClock(seconds: number) {
  const total = Math.max(0, Math.ceil(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = String(total % 60).padStart(2, '0')
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${secs}` : `${minutes}:${secs}`
}
