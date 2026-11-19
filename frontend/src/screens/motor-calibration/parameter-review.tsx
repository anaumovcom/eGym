import { comparisonValue, formatValue, PROVENANCE_LABEL, type ParameterPreview } from '@/features/motor/api/motor-api'
import { SPEC_STATUS } from './calibration-status'

export function ParameterReview({ review }: { review: ParameterPreview }) {
  return <section className="cal-review-panel" aria-label="Предварительная проверка правок">
    <h3>Что изменится в профиле v{review.baseVersion}</h3>
    <table><thead><tr><th>Параметр</th><th>Сторона</th><th>Сейчас</th><th>После сохранения</th><th>Действие настройки</th></tr></thead>
      <tbody>{review.changes.map(row => <tr key={`${row.scope}/${row.key}/${row.side}`}>
        <th>{row.label}</th><td>{row.side === 'left' ? 'Левая' : row.side === 'right' ? 'Правая' : 'Общее'}</td>
        <td>{comparisonValue(row.before.value, row.after.value, row.kind, row.unit)}<small>{PROVENANCE_LABEL[row.before.provenance]}</small></td>
        <td>{comparisonValue(row.after.value, row.before.value, row.kind, row.unit)}<small>{PROVENANCE_LABEL[row.after.provenance]}</small></td>
        <td>{row.effective ? `Контроллер использует ${formatValue(row.effective.value, row.kind, row.unit)} · ${row.effective.label}${row.effective.procedure ? ' (' + row.effective.procedure + ')' : ''}. Правка меняет базовое значение.`
          : row.restart ? 'При следующем подключении к приводу.' : 'При применении профиля'}</td>
      </tr>)}</tbody></table>
    {review.statusChanges.length ? <div><h4>Изменится статус калибровок</h4><ul>{review.statusChanges.map(s =>
      <li key={s.code}><strong>{s.code} · {s.title}</strong> · {SPEC_STATUS[s.before].label} → {SPEC_STATUS[s.after].label}</li>)}</ul></div>
      : <p>Статусы калибровок сохранятся.</p>}
  </section>
}
