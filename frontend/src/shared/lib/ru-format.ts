export function plural(count: number, one: string, few: string, many: string) {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

export function exerciseCountLabel(count: number) {
  return `${count} ${plural(count, 'упражнение', 'упражнения', 'упражнений')}`
}

/** "≈ 39 минут" -> "≈ 39 мин" (the backend wording does not agree with numbers). */
export function shortDuration(duration: string) {
  return duration.replace(/\s*минут[а-я]*/i, ' мин')
}
