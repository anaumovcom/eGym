import type { AchievementTier } from '@/entities/achievement/model/types'
import { achievementUnit } from '../lib/achievement-units'

const date = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })

export function AwardFacts({ tier, unit, earnedAt = tier.earnedAt ?? tier.awardedAt }: {
  tier: AchievementTier; unit: string; earnedAt?: string | null
}) {
  return (
    <dl className="ach-award-facts">
      <div><dt>Условие</dt><dd>{tier.threshold.toLocaleString('ru-RU')} {achievementUnit(unit, tier.threshold)}</dd></div>
      {Boolean(tier.minimumEvidenceDays) && <div><dt>Минимум дней практики</dt><dd>{tier.minimumEvidenceDays}</dd></div>}
      {earnedAt && <div><dt>Получено</dt><dd><time dateTime={earnedAt}>{date.format(new Date(earnedAt))}</time></dd></div>}
    </dl>
  )
}
