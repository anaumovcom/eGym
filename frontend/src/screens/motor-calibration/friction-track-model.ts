import type { FrictionSource, FrictionTrack, Side } from '@/features/motor/api/motor-api'

export const rails = ['left', 'right'] as const
export const railName = { left: 'Левая', right: 'Правая' }
export const railColor = { left: '#6fc9ff', right: '#ffc478' }
export const format = (n: number) => n.toLocaleString('ru-RU', { maximumFractionDigits: 1 })
export const signed = (n: number) => n > 0 ? '+' + format(n) : format(n)
export const binWidth = (t: FrictionTrack) => t.binMm ?? 20
export const threshold = (t: FrictionTrack, s: Side) => t.summary?.[s]?.thresholdN ?? 4
export const zoneLabel = (low: number, high: number) => format(low) + '–' + format(high) + ' мм'
export const level = (v: number | null, cut: number) =>
  v === null ? 'missing' : v > 2 * cut ? 'high' : v > cut ? 'raised' : 'usual'

export type FrictionZone = { side: Side; low: number; high: number; peakIndex: number; peakN: number }

export function tightZones(track: FrictionTrack, side: Side) {
  const zones: FrictionZone[] = []
  const half = binWidth(track) / 2
  let open: FrictionZone | undefined
  track.heightsMm.forEach((height, i) => {
    const value = track.sides[side][i]
    if (value == null || value <= threshold(track, side)) {
      open = undefined
      return
    }
    if (!open || height - half !== open.high) {
      open = { side, low: height - half, high: height + half, peakIndex: i, peakN: value }
      zones.push(open)
    } else {
      open.high = height + half
      if (value > open.peakN) {
        open.peakN = value
        open.peakIndex = i
      }
    }
  })
  return zones.sort((a, b) => b.peakN - a.peakN || a.low - b.low)
}

export function pairedEffort(t: FrictionTrack, side: Side, i: number) {
  const legs = t.directionalN?.[side]
  const up = legs?.up[i], down = legs?.down[i]
  return t.sides[side][i] != null && up != null && down != null ? (up + down) / 2 : null
}

export function comparisonIssue(now: FrictionTrack, before: FrictionTrack, source: FrictionSource): string | null {
  if (source === 'unknown') return 'У этих записей неизвестен источник.'
  if (!now.speedMmS || !before.speedMmS || !now.directionalN || !before.directionalN) {
    return 'В архивной записи отсутствуют параметры прохода. Для сравнения нужны два новых замера S10.'
  }
  if (now.speedMmS !== before.speedMmS || binWidth(now) !== binWidth(before)) return 'Различаются скорость или шаг замера.'
  for (const side of rails) {
    const a = now.reference?.[side], b = before.reference?.[side]
    if (!a || !b || a.zeroCounts == null || b.zeroCounts == null) return 'Для сравнения нужен известный ноль обеих кареток.'
    const drift = Math.abs(a.zeroCounts - b.zeroCounts) * a.mmPerPulse
    const tolerance = Math.min(now.zeroToleranceMm ?? 0, before.zeroToleranceMm ?? 0, binWidth(now) / 2)
    if ((drift > 0 && drift >= tolerance) || a.sign !== b.sign || a.mmPerPulse !== b.mmPerPulse || a.nPerRaw !== b.nPerRaw) {
      return 'Изменился ноль энкодера или шкала высоты и усилия. Повторите S10 с текущими настройками.'
    }
  }
  const previousHeights = new Map(before.heightsMm.map((h, i) => [h, i]))
  const overlap = now.heightsMm.some((height, i) => {
    const j = previousHeights.get(height)
    return j !== undefined && rails.some(s => pairedEffort(now, s, i) !== null && pairedEffort(before, s, j) !== null)
  })
  return overlap ? null : 'У записей нет общих высот с парным замером.'
}
