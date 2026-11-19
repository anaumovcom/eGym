import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ModbusShell } from '@/screens/modbus-debug/modbus-shell'
import { apiGet, apiPut } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { CanopenDiagnostics, type Diagnostics } from './canopen-diagnostics'
import './drive-transport.css'

type Adapter = 'modbus' | 'canopen' | 'twin'
type CanSettings = {
  operation: 'diagnostics' | 'control'
  torque_mode: 'auto' | 'cst' | 'profile_torque'
  driver: 'usbcanfd' | 'socketcan'; device: number; channel: number; interface: string; bitrate: number
  left_id: number; right_id: number; cycle_ms: number; velocity_unit: 'rpm' | 'counts/s'
}
type Config = { adapter: Adapter; canopen: CanSettings }
type NodeStatus = { node: number; mode: number; statusword: number; position: number; velocity: number; torque: number }
type Timing = { intervals: number; mean_hz: number; p99_ms: number; p99_feedback_ms?: number | null }
export type DriveStatus = { config: Config; connected: boolean; error: string | null; nodes: NodeStatus[]; timing: Timing | null; diagnostics?: Diagnostics | null }
const endpoint = '/api/hardware/drive-transport'
const queryKey = ['hardware', 'drive-transport']
const names = { modbus: 'Modbus RTU', canopen: 'CANopen', twin: 'Цифровой двойник' }
const timingNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })

const rates = [[20000, 0], [50000, 1], [125000, 2], [250000, 3], [500000, 4], [750000, 5], [1000000, 6]]

function TransportForm({ status }: { status: DriveStatus }) {
  const [draft, setDraft] = useState(status.config)
  const client = useQueryClient()
  const save = useMutation({
    mutationFn: () => apiPut<DriveStatus>(endpoint, draft),
    onSuccess: (next) => client.setQueryData(queryKey, next),
  })
  const can = draft.canopen
  function edit<K extends keyof CanSettings>(key: K, value: CanSettings[K]) {
    setDraft(prev => ({ ...prev, canopen: { ...prev.canopen, [key]: value } }))
  }
  const duplicate = draft.adapter === 'canopen' && can.left_id === can.right_id
  const readOnly = can.operation === 'diagnostics'
  const allowedRate = (rate: number) => (can.driver === 'socketcan' || rate >= 100000) && (readOnly || rate === 500000 || rate === 1000000)
  const wrongRate = draft.adapter === 'canopen' && !allowedRate(can.bitrate)
  return <form className="drive-transport-form" onSubmit={e => {
    e.preventDefault()
    if (!duplicate && !wrongRate && !save.isPending) save.mutate()
  }}>
    <fieldset disabled={save.isPending}>
      <legend>Канал управления</legend>
      <div className={draft.adapter === 'canopen' ? 'mb-field-pair mb-mode-pair' : undefined}>
      <label>Режим приводов<select value={draft.adapter} onChange={e => {
        const adapter = e.target.value as Adapter
        setDraft({ ...draft, adapter, canopen: adapter === 'canopen' ? { ...can, operation: 'diagnostics' } : can })
      }}>
        {Object.entries(names).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
      </select></label>
      {draft.adapter === 'canopen' && <label>Назначение подключения<select value={can.operation ?? 'control'} onChange={e => edit('operation', e.target.value as CanSettings['operation'])}>
        <option value="diagnostics">Диагностика · только чтение</option><option value="control">Управление приводами</option>
      </select></label>}
      </div>
      {draft.adapter === 'canopen' && <p className="mb-hint">{readOnly ? 'Только запросы SDO. Питание осей можно подавать по очереди.' :
        'После проверки пары Forma запускает PDO и может автоматически включить Servo ON.'}</p>}
    </fieldset>
    {draft.adapter === 'canopen' && <fieldset disabled={save.isPending}>
      <legend>Подключение CANopen</legend>
      <div className="mb-field-pair">
        <label>Адаптер<select value={can.driver} onChange={e => edit('driver', e.target.value as CanSettings['driver'])}>
          <option value="usbcanfd">USB-CAN-FD-B</option><option value="socketcan">SocketCAN</option>
        </select></label>
        <label>Скорость шины<select value={can.bitrate} onChange={e => edit('bitrate', Number(e.target.value))}>
          {rates.filter(([rate]) => allowedRate(rate) || can.bitrate === rate).map(([rate, pa]) =>
            <option key={rate} value={rate} disabled={!allowedRate(rate)}>{rate === 1000000 ? '1 Мбит/с' : (rate / 1000) + ' кбит/с'} · PA_00C = {pa}</option>)}
        </select></label>
      </div>
      {wrongRate && <p className="mb-error" role="alert">Выберите скорость, доступную для этого адаптера и режима.</p>}
      {can.driver === 'usbcanfd' ? <div className="mb-field-pair">
        <label>Номер USB-устройства<input type="number" min={0} max={7} required value={can.device} onChange={e => edit('device', Number(e.target.value))} /></label>
        <label>Канал адаптера<select value={can.channel} onChange={e => edit('channel', Number(e.target.value))}>
          <option value={0}>CAN1 на корпусе · SDK 0</option><option value={1}>CAN2 на корпусе · SDK 1</option>
        </select></label>
      </div> : <label>Сетевой интерфейс Linux<input required pattern="[a-zA-Z0-9_.\-]{1,15}" value={can.interface} onChange={e => edit('interface', e.target.value)} />
        <span className="mb-hint">Поднимите интерфейс в Linux с выбранной скоростью.</span></label>}
      <div className="mb-field-pair">
        {(['left_id', 'right_id'] as const).map(key => <label key={key}>{key === 'left_id' ? 'Левый привод' : 'Правый привод'} · Node ID
          <input type="number" min={1} max={32} required value={can[key] || ''} onChange={e => edit(key, Number(e.target.value))} />
        </label>)}
      </div>
      {duplicate && <p className="mb-error" role="alert">Укажите разные Node ID для двух приводов.</p>}
      <div className="mb-field-pair">
        <label>Период обмена<select value={can.cycle_ms} onChange={e => edit('cycle_ms', Number(e.target.value))}>
          <option value={20}>20 мс · 50 Гц</option><option value={10}>10 мс · 100 Гц</option><option value={5}>5 мс · 200 Гц</option>
        </select></label>
        <label>Единицы скорости 606C<select value={can.velocity_unit} onChange={e => edit('velocity_unit', e.target.value as CanSettings['velocity_unit'])}>
          <option value="rpm">Обороты в минуту</option><option value="counts/s">Отсчёты энкодера в секунду</option>
        </select></label>
      </div>
      <details className="can-wiring"><summary>Режим момента и подключение A6</summary>
        <label>Режим момента CiA 402<select value={can.torque_mode ?? 'auto'} onChange={e => edit('torque_mode', e.target.value as CanSettings['torque_mode'])}>
          <option value="auto">Авто · CST, затем Profile Torque</option><option value="cst">Только CST (10)</option>
          <option value="profile_torque">Только Profile Torque (4)</option>
        </select></label>
        <p className="mb-hint">На обоих A6 задайте PA_002 = 10. PA_000 задаёт Node ID каждой оси. Сохраните параметры панели и перезапустите питание управления. Период обмена применяется в режиме управления.</p>
        {can.driver === 'usbcanfd' && <p className="mb-hint">Обе оси подключаются к одному каналу. На конце линии включите один переключатель 120 Ом этого канала и оконечный резистор на последнем A6.</p>}
        <p className="mb-hint">У A6 по руководству 2020‑05 на CN1/CN2 контакт 1 — CAN_H, 2 — CAN_L, 3 — GND. Для исполнения CN6A/CN6B сверьте распиновку своей ревизии.</p>
      </details>
    </fieldset>}
    {draft.adapter === 'modbus' && <p className="mb-hint">Для Modbus установите на обоих A6 режим момента PA_002 = 2. <Link to="/modbus/settings">Настройки последовательного порта</Link></p>}
    <div className="mb-apply">
      <Button type="submit" disabled={save.isPending || duplicate || wrongRate || JSON.stringify(draft) === JSON.stringify(status.config)}>
        {save.isPending ? 'Применяем…' : 'Применить режим'}
      </Button>
      <p className="mb-hint">Переключайте канал с грифом на упорах и выключенными приводами.</p>
    </div>
    {save.isError && <p className="mb-error" role="alert">{save.error.message}</p>}
  </form>
}

export function DriveTransportScreen() {
  const query = useQuery({ queryKey, queryFn: () => apiGet<DriveStatus>(endpoint), refetchInterval: 2000 })
  const status = query.data
  const observing = status?.config.adapter === 'canopen' && status.config.canopen.operation === 'diagnostics'
  const label = query.isError ? 'нет связи с программой' : observing && status.diagnostics ?
    (status.diagnostics.adapter_open ? 'чтение узлов' : 'ожидание адаптера') : status?.connected ? 'на связи' : 'ожидание'
  return <ModbusShell>
    <header className="modbus-hero drive-transport-heading"><div><Link to="/settings?tab=service">Сервисные настройки</Link><h1>Подключение приводов</h1></div>
      {status && <div className="modbus-link-status" role="status" data-state={!query.isError && (status.connected || (observing && status.diagnostics?.adapter_open)) ? 'online' : 'offline'}>
        <div><small>Активный режим</small><strong>{names[status.config.adapter]} · {label}</strong></div>
      </div>}
    </header>
    {query.isError && <p role="alert">Нет связи с программой управления.{status && ' На экране последний полученный снимок.'} <button type="button" onClick={() => void query.refetch()}>Повторить</button></p>}
    {status ? <div className="drive-transport-layout">
      <TransportForm key={'form-' + JSON.stringify(status.config)} status={status} />
      {status.diagnostics ? <CanopenDiagnostics key={'diagnostics-' + JSON.stringify(status.config)} status={status} diagnostics={status.diagnostics} updatedAt={query.dataUpdatedAt} /> :
        (status.error || status.nodes.length > 0) && <aside className="drive-transport-feedback" aria-label="Состояние приводов">
        {status.error && <p role="status">{status.error}</p>}
        {status.timing && <section>
          <h2>Обмен двух приводов</h2>
          <dl>
            <div><dt>Средняя частота</dt><dd>{timingNumber.format(status.timing.mean_hz)} Гц</dd></div>
            <div><dt>Период p99</dt><dd>{timingNumber.format(status.timing.p99_ms)} мс</dd></div>
            <div><dt>Измерено интервалов</dt><dd>{status.timing.intervals}</dd></div>
          </dl>
        </section>}
        {status.nodes.map(n => <section key={n.node}>
          <h2>{n.node === status.config.canopen.left_id ? 'Левый привод' : 'Правый привод'} · ID {n.node}</h2>
          <dl>{[
            ['Режим', n.mode === 10 ? 'CST' : 'Profile Torque'],
            ['Состояние 6041', '0x' + n.statusword.toString(16).padStart(4, '0').toUpperCase()],
            ['Позиция, отсчёты', n.position], [status.config.canopen.velocity_unit === 'rpm' ? 'Скорость, об/мин' : 'Скорость, отсчёты/с', n.velocity],
            ['Момент, ‰ номинала', n.torque],
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        </section>)}
      </aside>}
    </div> : !query.isError && <p role="status">Читаем настройки приводов…</p>}
  </ModbusShell>
}
