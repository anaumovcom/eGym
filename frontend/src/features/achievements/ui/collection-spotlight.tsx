import { ArrowUpRight, Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { AchievementLine } from '@/entities/achievement/model/types'
import { distanceToAward } from '../lib/achievement-units'
import type { CollectionItem } from '../lib/collection-filters'
import { AchievementImage, RarityBadge } from './achievement-media'
import { CollectionSymbol } from './collection-symbol'

export function CollectionSpotlight({ latest, next }: { latest?: CollectionItem; next?: AchievementLine }) {
  const tier = latest?.tier
  const target = next?.tiers.find(item => item.id === next.nextTierId)
  if (!tier && !target) return null
  return (
    <section className="ach-spotlight" aria-label="Личная витрина">
      {tier && latest && <Link className="ach-showpiece" data-rarity={tier.rarity}
        to={`/achievements/${encodeURIComponent(latest.line.id)}?tier=${tier.tier}`} aria-label={`Последняя находка · ${tier.title}`}>
        <AchievementImage tier={tier} decorative eager />
        <div className="ach-showpiece-copy"><span className="ach-kicker">Последняя находка</span>
          <strong>{tier.title}</strong><p>{tier.phrase}</p><RarityBadge rarity={tier.rarity} /></div>
        <ArrowUpRight className="ach-open-arrow" aria-hidden="true" />
      </Link>}
      {next && target && <Link className="ach-clue" to={`/achievements/${encodeURIComponent(next.id)}`}>
        <span className="ach-clue-icon"><CollectionSymbol group={next.group} /></span>
        <div className="ach-showpiece-copy"><span className="ach-kicker"><Compass aria-hidden="true" />{tier ? 'На подходе' : 'Первая находка'}</span>
          <strong>{next.name}</strong><p>{next.description}</p>
          <span className="ach-clue-distance">{distanceToAward(next.currentValue, target.threshold, next.unit)}</span></div>
        <ArrowUpRight className="ach-open-arrow" aria-hidden="true" />
      </Link>}
    </section>
  )
}
