const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 })
const dayFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' })
const fullDayFormat = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' })

export function formatNumber(value: number) {
  return numberFormat.format(Math.abs(value) >= 100 ? Math.round(value) : value)
}

/** Accepts both plain ISO dates and full timestamps; plain dates are treated as local days. */
export function formatDay(value: string, full = false) {
  const date = value.length === 10 ? new Date(`${value}T12:00:00`) : new Date(value)
  return (full ? fullDayFormat : dayFormat).format(date).replace('.', '')
}

export function plural(value: number, one: string, few: string, many: string) {
  const mod10 = value % 10
  const mod100 = value % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

export function daysAgo(value: string) {
  const date = new Date(value)
  const today = new Date()
  const days = Math.round((new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()) / 86_400_000)
  if (days <= 0) return 'сегодня'
  if (days === 1) return 'вчера'
  return `${days} ${plural(days, 'день', 'дня', 'дней')} назад`
}
