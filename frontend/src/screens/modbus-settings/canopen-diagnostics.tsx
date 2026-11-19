import { useState } from 'react'
import type { DriveStatus } from './drive-transport-screen'

type Reading = { value: number | null; abort: number | null; issue?: string | null; age_ms: number }
type Axis = {
  node: number; responding: boolean | null; last_seen_ms: number | null; issue: string | null
  heartbeat_state: number | null; heartbeat_age_ms: number | null; bootups: number
  emcy: number | null; emcy_register: number | null; emcy_age_ms: number | null
  objects: Record<string, Reading>; sent_controlword: number | null; sent_target: number | null
  tpdo_latency_ms?: number | null
}
type Frame = { seq: number; elapsed_ms: number; direction: 'TX' | 'RX'; identifier: number; data: string }
export type Diagnostics = {
  stage: string; adapter_open: boolean; adapter: {
    model: string | null; serial: string | null; hardware: number | null; firmware: number | null
    driver: number | null; channels: number | null; interface_bitrate: number | null; link_state: string | null
  } | null
  tx: number; rx: number; sdo_timeouts: number; sdo_aborts: number; axes: Axis[]; frames: Frame[]
}
const fmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })
const hex = (v: number, width: number) => '0x' + v.toString(16).toUpperCase().padStart(width, '0')
const elapsed = (ms: number | null) => ms == null ? '—' : ms < 1000 ? ms + ' мс' : fmt.format(ms / 1000) + ' с'
const hbStates: Record<number, string> = { 0: 'Boot-up', 4: 'Stopped', 5: 'Operational', 127: 'Pre-operational' }
const modes: Record<number, string> = { 0: 'Режим не задан', 1: 'Profile Position', 3: 'Profile Velocity', 4: 'Profile Torque', 6: 'Homing', 8: 'CSP', 9: 'CSV', 10: 'CST' }
const tabs = ['Связь и оси', 'Словарь A6', 'Кадры CAN'] as const
type Tab = typeof tabs[number]

function pds(word: number) {
  const basic: Record<number, string> = { 0: 'Инициализация', 0x40: 'Включение запрещено', 0x08: 'Авария', 0x0F: 'Реакция на аварию' }
  const powered: Record<number, string> = { 0x21: 'Готов к включению', 0x23: 'Включён', 0x27: 'Управление разрешено', 0x07: 'Quick Stop' }
  return basic[word & 0x4F] ?? powered[word & 0x6F] ?? 'Неизвестное состояние'
}

function reading(axis: Axis, key: string, format: (n: number) => string = String) {
  const r = axis.objects[key]
  if (!r) return '—'
  if (r.abort != null) return 'SDO abort ' + hex(r.abort, 8)
  if (r.issue) return r.issue
  return r.value == null ? 'Тайм-аут' : format(r.value)
}

const objectGroups: Record<string, Record<string, string>> = {
  'Паспорт и режим': {
    '1018:01': 'Производитель', '1018:02': 'Код изделия', '1018:03': 'Ревизия', '1018:04': 'Серийный номер',
    '6502:00': 'Маска режимов', '6060:00': 'Заданный режим', '6061:00': 'Фактический режим',
  },
  'Состояние и пределы': {
    '6040:00': 'Слово управления', '6041:00': 'Слово состояния', '603F:00': 'Код аварии', '1001:00': 'Регистр ошибок',
    '6071:00': 'Заданный момент, ‰', '6077:00': 'Фактический момент, ‰', '6064:00': 'Позиция, отсчёты',
    '606C:00': 'Скорость', '6072:00': 'Предел момента, ‰', '6080:00': 'Предел скорости', '6087:00': 'Наклон рампы момента',
  },
  'SYNC и heartbeat': {
    '1005:00': 'COB-ID SYNC', '1006:00': 'Период SYNC, мкс', '1019:00': 'Переполнение счётчика SYNC',
    '1017:00': 'Период heartbeat, мс', '1016:00': 'Число потребителей heartbeat',
  },
  'Карты PDO': {},
}
const groups = Object.keys(objectGroups)
function objectKeys(group: string, axes: Axis[]) {
  const known = Object.keys(objectGroups[group])
  const keys = [...new Set(axes.flatMap(a => Object.keys(a.objects)))].sort()
  if (group === 'SYNC и heartbeat') return [...known, ...keys.filter(k => k.startsWith('1016:') && !k.endsWith(':00'))]
  if (group !== 'Карты PDO') return known
  return [...new Set(['1400:01', '1400:02', '1600:00', '1800:01', '1800:02', '1A00:00', '1801:01', '1801:02', '1A01:00', ...keys.filter(k => /^(1400|1600|180[01]|1A0[01]):/.test(k))])].sort()
}
function objectLabel(group: string, key: string) {
  if (objectGroups[group][key]) return objectGroups[group][key]
  if (key.startsWith('1016:')) return 'Потребитель heartbeat'
  const names: Record<string, string> = { '1400': 'RPDO1', '1600': 'RPDO1', '1800': 'TPDO1', '1A00': 'TPDO1', '1801': 'TPDO2', '1A01': 'TPDO2' }
  const [idx, sub] = key.split(':')
  if (['1600', '1A00', '1A01'].includes(idx)) return names[idx] + (sub === '00' ? ' · число полей' : ' · поле ' + parseInt(sub, 16))
  return names[idx] + (sub === '01' ? ' · COB-ID' : ' · тип передачи')
}

function objectValue(key: string, value: number) {
  if (key.startsWith('6060') || key.startsWith('6061')) return (modes[value] ?? 'Режим') + ' (' + value + ')'
  if (key === '6502:00') return [hex(value, 8), ...(value & 0x200 ? ['CST'] : []), ...(value & 8 ? ['Profile Torque'] : [])].join(' · ')
  if (key === '6041:00') return hex(value, 4) + ' · ' + pds(value)
  if (key === '1001:00') return hex(value, 2)
  if (key === '603F:00' || key === '6040:00') return hex(value, 4)
  if (key.startsWith('1016:') && !key.endsWith(':00')) return hex(value, 8) + ' · ID ' + ((value >>> 16) & 255) + ' / ' + (value & 65535) + ' мс'
  if (/^(1600|1A0[01]):(?!00)/.test(key)) return hex(value >>> 16, 4) + ':' + hex((value >>> 8) & 255, 2).slice(2) + ' · ' + (value & 255) + ' бит'
  if (/^(1400|180[01]):01$/.test(key)) return hex(value, 8) + ((value >>> 31) ? ' · выключен' : ' · включён')
  return key.startsWith('1018:') || key === '1005:00' ? hex(value, 8) : String(value)
}
function Dictionary({ axes }: { axes: Axis[] }) {
  const [group, setGroup] = useState<string>(groups[0])
  return <section><label className="can-select">Группа объектов<select value={group} onChange={e => setGroup(e.target.value)}>
    {groups.map(g => <option key={g}>{g}</option>)}</select></label>
    <div className="can-table-scroll"><table><thead><tr><th>Объект</th>{axes.map(a => <th key={a.node}>ID {a.node}</th>)}</tr></thead>
      <tbody>{objectKeys(group, axes).map(k => <tr key={k}><th><code>{k}</code> {objectLabel(group, k)}</th>{axes.map(a => <td key={a.node}>
        {reading(a, k, v => objectValue(k, v))}{a.objects[k] && <small>{elapsed(a.objects[k].age_ms)} назад</small>}
      </td>)}</tr>)}</tbody></table></div>
    <p className="can-note">Прочерк означает, что объект ещё не прочитан. SDO abort показывает ответ прошивки на запрос этого объекта.</p>
  </section>
}

function frameName(frame: Frame, axes: Axis[]) {
  const id = frame.identifier
  if (id === 0) return 'NMT'
  if (id === 0x80) return 'SYNC'
  const bytes = frame.data ? frame.data.split(' ') : []
  for (const axis of axes) {
    if (id === 0x80 + axis.node) return 'EMCY · ID ' + axis.node
    if (id === 0x580 + axis.node || id === 0x600 + axis.node) {
      const address = bytes.length === 8 ? bytes[2] + bytes[1] + ':' + bytes[3] : ''
      return (bytes[0] === '80' ? 'SDO abort' : 'SDO') + ' ' + address + ' · ID ' + axis.node
    }
    for (const [address, name] of [['1400:01', 'RPDO1'], ['1800:01', 'TPDO1'], ['1801:01', 'TPDO2']]) {
      const cob = axis.objects[address]?.value
      if (cob != null && (cob & 0xBFFFFFFF) === id) return name + ' · ID ' + axis.node
    }
  }
  if (id > 0x700 && id <= 0x77F) return (bytes[0] === '00' ? 'Boot-up' : 'Heartbeat') + ' · ID ' + (id - 0x700)
  return 'CAN'
}

function FrameLog({ diagnostics }: { diagnostics: Diagnostics }) {
  const [held, setHeld] = useState<Diagnostics | null>(null)
  const data = held ?? diagnostics
  return <section><div className="can-section-head"><h2>Последние 64 кадра</h2>
    <button type="button" aria-pressed={!!held} onClick={() => setHeld(held ? null : diagnostics)}>{held ? 'Продолжить просмотр' : 'Пауза просмотра'}</button></div>
    <p className="can-note">Время приёма и отправки на компьютере, в миллисекундах от запуска этого подключения.</p>
    {data.frames.length ? <div className="can-table-scroll"><table><thead><tr><th>мс</th><th>TX/RX</th><th>CAN-ID</th><th>Протокол</th><th>DLC</th><th>Данные, hex</th></tr></thead>
      <tbody>{[...data.frames].reverse().map(f => <tr key={f.seq}><td>{fmt.format(f.elapsed_ms)}</td><td>{f.direction}</td><td><code>{hex(f.identifier, 3)}</code></td>
        <td>{frameName(f, data.axes)}</td><td>{f.data ? f.data.split(' ').length : 0}</td><td><code>{f.data || '—'}</code></td></tr>)}</tbody></table></div> :
      <p>Кадров пока нет.</p>}</section>
}

function AxisCard({ axis, title, unit, opened }: { axis: Axis; title: string; unit: string; opened: boolean }) {
  const hasReadings = Object.keys(axis.objects).length > 0
  const hb = axis.heartbeat_state == null ? '—' : (hbStates[axis.heartbeat_state] ?? hex(axis.heartbeat_state, 2)) + ' · ' + elapsed(axis.heartbeat_age_ms) + ' назад'
  const rows = [
    ['Связь', !opened ? 'Канал закрыт' : axis.responding == null ? 'Ожидание опроса' : axis.responding ? 'Есть ответ' : 'Нет ответа'],
    ['Последний ответ SDO / PDO', elapsed(axis.last_seen_ms)],
    ...(hasReadings ? [['Состояние 6041', reading(axis, '6041:00', v => objectValue('6041:00', v))],
      ['Авария 603F / регистр 1001', reading(axis, '603F:00', v => hex(v, 4)) + ' / ' + reading(axis, '1001:00', v => hex(v, 2))]] : []),
    ...(axis.emcy == null ? [] : [['Последний EMCY / регистр', hex(axis.emcy, 4) + ' / ' + hex(axis.emcy_register!, 2) + ' · ' + elapsed(axis.emcy_age_ms) + ' назад']]),
    ['Heartbeat', hb + (axis.bootups ? ' · boot-up ×' + axis.bootups : '')],
    ...(hasReadings ? [['Режим 6061', reading(axis, '6061:00', v => objectValue('6061:00', v))],
      ['Позиция, отсчёты', reading(axis, '6064:00')], ['Скорость, ' + unit, reading(axis, '606C:00')],
      ['Фактический момент 6077, ‰', reading(axis, '6077:00')]] : []),
    ...(axis.sent_controlword != null ? [['Передано RPDO · 6040 / 6071', hex(axis.sent_controlword, 4) + ' / ' + axis.sent_target]] :
      hasReadings ? [['Заданный момент 6071, ‰', reading(axis, '6071:00')]] : []),
    ...(axis.tpdo_latency_ms == null ? [] : [['SYNC → оба TPDO оси', fmt.format(axis.tpdo_latency_ms) + ' мс']]),
  ]
  return <section><h2>{title} · ID {axis.node}</h2>{axis.issue && <p className="can-issue">{axis.issue}</p>}
    {hasReadings && (!opened || axis.responding === false) && <p className="can-note">Последние полученные значения</p>}
    <dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section>
}

function downloadReport(status: DriveStatus, updatedAt: number) {
  const sampled = new Date(updatedAt).toISOString()
  const url = URL.createObjectURL(new Blob([JSON.stringify({ snapshot_received_at: sampled, ...status }, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'forma-canopen-' + sampled.replace(/[:.]/g, '-') + '.json'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function CanopenDiagnostics({ status, diagnostics: d, updatedAt }: { status: DriveStatus; diagnostics: Diagnostics; updatedAt: number }) {
  const [tab, setTab] = useState<Tab>(tabs[0])
  const info = d.adapter
  const can = status.config.canopen
  const count = d.axes.filter(a => a.responding).length
  return <aside className="drive-transport-feedback can-diag" aria-label="Диагностика CANopen">
    <div className="can-section-head"><h2>Диагностика CANopen</h2><button type="button" onClick={() => downloadReport(status, updatedAt)}>Сохранить отчёт JSON</button></div>
    <div className="can-summary"><div><small>Адаптер</small><strong>{d.adapter_open ? 'Канал открыт' : 'Канал закрыт'}</strong></div>
      <div><small>Ответили оси</small><strong>{d.adapter_open ? count + ' из ' + d.axes.length : '—'}</strong></div><div><small>Этап обмена</small><strong>{d.stage}</strong></div></div>
    {status.error && <p role="status" className="can-issue">{status.error}</p>}
    <div role="group" aria-label="Раздел диагностики" className="can-tabs">{tabs.map(t =>
      <button type="button" key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>{t}</button>)}</div>
    {tab === 'Связь и оси' && <><section className="can-link-detail"><h2>{can.driver === 'usbcanfd' ? 'USB-CAN-FD-B · CAN' + (can.channel + 1) + ' · SDK ' + can.channel : 'SocketCAN · ' + can.interface}</h2>
      {info && <p>{[info.model, info.serial && 'S/N ' + info.serial, info.hardware != null && 'HW ' + hex(info.hardware, 4),
        info.firmware != null && 'FW ' + hex(info.firmware, 4), info.driver != null && 'SDK ' + hex(info.driver, 4),
        info.channels != null && 'Каналов ' + info.channels, info.interface_bitrate && info.interface_bitrate / 1000 + ' кбит/с', info.link_state].filter(Boolean).join(' · ')}</p>}
      <p>TX {d.tx} · RX {d.rx} · Тайм-ауты SDO {d.sdo_timeouts} · Отказы SDO {d.sdo_aborts}</p>
      {status.timing && <p>Обмен двух приводов · <b>{fmt.format(status.timing.mean_hz)} Гц</b> · период p99 <b>{fmt.format(status.timing.p99_ms)} мс</b>
        {status.timing.p99_feedback_ms != null && <> · SYNC → 4 TPDO p99 <b>{fmt.format(status.timing.p99_feedback_ms)} мс</b></>} · {status.timing.intervals} интервалов</p>}
    </section><div className="can-axes">{d.axes.map(a => <AxisCard key={a.node} axis={a} opened={d.adapter_open}
      title={a.node === can.left_id ? 'Левый привод' : 'Правый привод'} unit={can.velocity_unit === 'rpm' ? 'об/мин' : 'отсчёты/с'} />)}</div>
      {(!d.adapter_open || count < d.axes.length) && <p className="can-note">{d.adapter_open ? 'Если узел не отвечает, сверьте питание A6, PA_000, PA_00C, выбранный разъём и оконечные сопротивления.' :
        'Проверьте подключение адаптера, номер устройства и доступ процесса Forma к нему. Данные закрытого канала относятся к последнему обмену.'}</p>}
    </>}
    {tab === 'Словарь A6' && <Dictionary axes={d.axes} />}
    {tab === 'Кадры CAN' && <FrameLog diagnostics={d} />}
  </aside>
}
