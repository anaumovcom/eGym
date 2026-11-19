import { Activity, ArrowDownUp, Dumbbell, Gauge, ListChecks, ScanLine, ShieldAlert } from 'lucide-react'
import type { CalibrationSpec } from '@/features/motor/api/motor-api'
import { setupSteps } from './first-setup'

export const scenarios = [
  { id: 'setup', title: 'Первичная настройка', icon: ScanLine, description: 'От пустого грифа на упорах до проверки ощущения Смита.', codes: setupSteps.map(s => s.code) },
  { id: 'motion', title: 'Плавный ход', icon: ArrowDownUp, description: 'Найдите тугие участки, измерьте трение и инерцию. Проверьте мягкость трогания и смены направления.', codes: ['S7', 'D2', 'D4', 'S10', 'W1', 'F3', 'F4', 'F6', 'F7', 'X4', 'G4'] },
  { id: 'load', title: 'Рабочий вес', icon: Dumbbell, description: 'Сверьте усилие с эталонным грузом и настройте, как ощущается вес при подъёме и опускании.', codes: ['S9', 'G1', 'D5', 'N1', 'L1', 'L2', 'L3', 'F1', 'F2', 'N2'] },
  { id: 'speed', title: 'Скорость и торможение', icon: Gauge, description: 'Сверьте скорость с энкодером, измерьте остановку и сравните доступный ход с расчётом для выбранной скорости.', codes: ['B1', 'B3', 'V1', 'V2', 'V3', 'M3', 'M5', 'M6', 'E1', 'F10'] },
  { id: 'smith', title: 'Проверка Смита', icon: Activity, description: 'Сначала проверьте одинаковость проходов и отпускание грифа. Затем сравните разворот и вес рукой при 6 и 16 кг.', codes: ['G4', 'F11', 'G2', 'G3'] },
  { id: 'daily', title: 'Перед тренировкой', icon: ListChecks, description: 'Проверьте ноль, баланс и трение пустого грифа по сохранённому профилю.', codes: ['Q1'] },
  { id: 'protection', title: 'Перекос и фиксация', icon: ShieldAlert, description: 'Разберите реакцию на сбой, проверьте выравнивание кареток, подвод к упражнению и жёсткость фиксации.', codes: ['X3', 'X4', 'P1', 'P2', 'M5', 'M6', 'H1', 'H3', 'E1'] },
]

export function ScenarioPicker({ specs, active, disabled, onPick }: {
  specs: Map<string, CalibrationSpec>; active: string; disabled: boolean; onPick: (id: string) => void
}) {
  return (
    <nav className="cal-scenarios" aria-label="Сценарии калибровки">
      {scenarios.map(({ id, title, icon: Icon, codes }) => {
        const available = codes.map(code => specs.get(code)).filter((spec): spec is CalibrationSpec => Boolean(spec))
        const done = available.filter(spec => spec.status === 'actual').length
        return <button key={id} type="button" aria-pressed={id === active} disabled={disabled || !available.length} onClick={() => onPick(id)}>
          <span className="cal-scenario-top"><Icon size={19} aria-hidden="true" /><small aria-label={`Актуально ${done} из ${available.length}`}>{done} / {available.length}</small></span>
          <strong>{title}</strong>
          <span className="cal-meter" aria-hidden="true"><i style={{ width: `${available.length ? 100 * done / available.length : 0}%` }} /></span>
        </button>
      })}
    </nav>
  )
}
