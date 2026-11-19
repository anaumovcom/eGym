import type { CSSProperties } from 'react'
import type { MuscleStatus } from '@/entities/muscle/model/types'

export const fatigueColors: Record<MuscleStatus, string> = {
  ready: '#798897',
  light: '#52a8ec',
  medium: '#ad83e9',
  high: '#ffb649',
  critical: '#ff766d',
  no_data: '#8495a7',
}

const heatOpacity: Record<MuscleStatus, number> = {
  ready: 0, no_data: 0, light: .43, medium: .58, high: .73, critical: .85,
}

export function muscleHeatOpacity(status: MuscleStatus, score = 0) {
  const opacity = heatOpacity[status]
  return opacity && opacity + .12 * Math.min(100, Math.max(0, score)) / 100
}

export const fatigueLabels: Record<MuscleStatus, string> = {
  ready: 'Готова к нагрузке',
  light: 'Лёгкая усталость',
  medium: 'Умеренная усталость',
  high: 'Высокая усталость',
  critical: 'Перегрузка',
  no_data: 'Нет данных',
}

export const fatigueLegend = [
  { status: 'ready', label: 'Готова / нет данных' },
  { status: 'light', label: 'Низкая' },
  { status: 'medium', label: 'Средняя' },
  { status: 'high', label: 'Высокая' },
  { status: 'critical', label: 'Перегрузка' },
] as const

export const fatiguePaletteStyle = {
  '--fatigue-scale': `linear-gradient(90deg, ${fatigueColors.ready}, ${fatigueColors.light}, ${fatigueColors.medium}, ${fatigueColors.high}, ${fatigueColors.critical})`,
} as CSSProperties
