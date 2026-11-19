import type { CalibrationSpec } from '@/features/motor/api/motor-api'
import { PriorityMark } from './calibration-priority'

export const setupSteps = [
  { code: 'WIZARD', title: 'Подготовить приводы', task: 'Положите пустой гриф на нижние упоры. В панели состояния включите сервисный режим и оба привода. Мастер проверит связь, направление, поддержку и торможение.' },
  { code: 'B8', title: 'Измерить полный ход', task: 'Освободите весь ход пустого грифа. Проследите, что обе каретки дошли до верхних упоров, а затем вернулись вниз.' },
  { code: 'B6', title: 'Сверить высоту рулеткой', task: 'Отметьте положение каретки на нижних упорах. Когда гриф остановится в поднятом положении, измерьте подъём от отметки и введите миллиметры.' },
  { code: 'AUTO_GUIDES', title: 'Измерить направляющие', task: 'Оставьте гриф пустым. Тренажёр сравнит каретки, измерит баланс по высоте и покажет, где ход тяжелее.' },
  { code: 'AUTO_MOTION', title: 'Настроить движение', task: 'Наблюдайте за пустым грифом. Тренажёр измерит трение и инерцию в середине хода, затем подберёт разгон, торможение и посадку.' },
  { code: 'AUTO_SIGNAL', title: 'Настроить отклик и поддержку', task: 'Оставьте гриф свободным. Тренажёр проверит передачу усилия, движение после паузы и удержание.' },
  { code: 'AUTO_WEIGHT', title: 'Сверить килограммы', task: 'На нижних упорах закрепите известный груз поровну с двух сторон. Введите его общую массу без грифа. Оставьте груз на оба автоматических замера и снимите после завершения серии.' },
  { code: 'AUTO_FEEL', title: 'Настроить ощущение Смита', task: 'Снимите весь эталонный груз. Тренажёр воспроизведёт повторения и подберёт отклик при трогании, развороте и прохождении тугих участков.' },
  { code: 'F11', title: 'Настроить захват при отпускании', task: 'Оставьте гриф свободным. Тренажёр сравнит удержание и отпускание на двух виртуальных нагрузках. На графике видны движение и усилие обеих кареток.' },
  { code: 'G4', title: 'Сравнить одинаковые проходы', task: 'Оставьте гриф пустым. Тренажёр трижды пройдёт среднюю зону в каждом направлении и сравнит усилие обеих сторон.' },
  { code: 'G2', title: 'Проверить отклик под нагрузкой', task: 'Освободите ход пустого грифа. Тренажёр воспроизведёт повторения с разными виртуальными весами и оценит плавность разворота.' },
  { code: 'G3', title: 'Оценить гриф рукой', task: 'Дождитесь приглашения взять гриф. Выполните по три полных повторения с виртуальными 6 и 16 кг. После каждого подхода оцените ощущения.' },
]

export function participation(spec: CalibrationSpec) {
  switch (spec.participation) {
    case 'tape': return 'Нужна рулетка'
    case 'weight': return 'Нужен взвешенный груз'
    case 'hands': return 'С вашим участием'
    default: return 'Автоматически'
  }
}

export function SetupRoute({ specs, selected, disabled, onSelect }: {
  specs: Map<string, CalibrationSpec>; selected: string; disabled: boolean; onSelect: (code: string) => void
}) {
  const steps = setupSteps.filter(s => specs.has(s.code))
  const done = steps.filter(s => specs.get(s.code)?.status === 'actual').length
  const remainingSeconds = steps.reduce((sum, step) => {
    const spec = specs.get(step.code)!
    return sum + (spec.status === 'actual' ? 0 : spec.durationS ?? 0)
  }, 0)
  const equipment = [
    specs.has('B6') && specs.get('B6')?.status !== 'actual' && 'рулетку',
    specs.has('AUTO_WEIGHT') && specs.get('AUTO_WEIGHT')?.status !== 'actual' && 'два взвешенных груза, например по 10 кг',
  ].filter(Boolean).join(' и ')
  return <section aria-label="Маршрут первого запуска">
    <p className="cal-route-count">{done === steps.length ? 'Маршрут пройден' : 'Первая настройка'} · {done} из {steps.length} этапов</p>
    <progress value={done} max={steps.length || 1} aria-label="Этапы первого запуска" />
    {done < steps.length && <p className="cal-route-help">{equipment && `Подготовьте ${equipment}.`}
      {remainingSeconds > 0 && ` Оставшиеся замеры займут ориентировочно ${Math.ceil(remainingSeconds / 60)} мин.`} После сохранения серии можно сделать перерыв.</p>}
    <ol className="cal-route-list">{steps.map(({ code, title }, i) => {
      const spec = specs.get(code)!
      return <li key={code}><button type="button" disabled={disabled} aria-current={code === selected ? 'step' : undefined} onClick={() => onSelect(code)}>
        <span className="cal-route-index" data-done={spec.status === 'actual'}>{spec.status === 'actual' ? '✓' : i + 1}</span>
        <span><strong>{title}</strong><span className="cal-procedure-meta"><PriorityMark code={code} />
          <small>{participation(spec)}{spec.status === 'stale' ? ' · обновить' : spec.status === 'failed' ? ' · повторить проверку' : ''}</small></span></span>
      </button></li>
    })}</ol>
  </section>
}
