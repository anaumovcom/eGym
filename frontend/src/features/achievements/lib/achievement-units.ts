import { plural } from '@/shared/lib/ru-format'

// Series descriptions carry the qualifiers (e.g. days of stretching). Keep counters short.
const forms: [string, string, string][] = [
  ['день', 'дня', 'дней'], ['неделя', 'недели', 'недель'], ['месяц', 'месяца', 'месяцев'],
  ['квартал', 'квартала', 'кварталов'], ['сезон', 'сезона', 'сезонов'], ['круг', 'круга', 'кругов'],
  ['возвращение', 'возвращения', 'возвращений'], ['переход', 'перехода', 'переходов'], ['пара', 'пары', 'пар'],
  ['упражнение', 'упражнения', 'упражнений'], ['тренировка', 'тренировки', 'тренировок'],
  ['подход', 'подхода', 'подходов'], ['повторение', 'повторения', 'повторений'],
  ['секунда', 'секунды', 'секунд'], ['шаблон', 'шаблона', 'шаблонов'],
]
const byWord = new Map(forms.flatMap((variants) => variants.map((word) => [word, variants] as const)))

export function achievementUnit(unit: string, value: number) {
  for (const word of unit.split(' ')) {
    const variants = byWord.get(word)
    if (variants) return plural(value, ...variants)
  }
  return unit
}

export function distanceToAward(value: number, threshold: number, unit: string) {
  const remaining = Math.max(0, Math.ceil(threshold - value))
  return remaining ? `До открытия · ${remaining.toLocaleString('ru-RU')} ${achievementUnit(unit, remaining)}`
    : 'Условие выполнено · открытие в конце тренировки'
}
