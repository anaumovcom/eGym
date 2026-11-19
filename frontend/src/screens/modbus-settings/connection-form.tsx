import { Link2, RefreshCw, Unlink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import type { ModbusConnectionStatus } from '@/features/modbus/model/types'
import { Button } from '@/shared/ui/button'
import type { useModbusRead } from '@/features/modbus/lib/use-modbus-read'

const rates = [9600, 19200, 38400, 57600, 115200]
const manualOption = '__manual__'
const inRange = (text: string, min: number, max: number) => /^\d+$/.test(text) && Number(text) >= min && Number(text) <= max
type Fields = Record<'port' | 'baudRate' | 'timeoutMs' | 'left' | 'right', string>

export function ConnectionForm({ status, portsRead, checking, clearCheck, refreshStatus }: {
  status: ModbusConnectionStatus | null
  portsRead: ReturnType<typeof useModbusRead>
  checking: boolean
  clearCheck?: () => void
  refreshStatus: () => void
}) {
  const { ports, connectionParams: params, connectionPending, connect, disconnect } = useModbusStore()
  const [edits, setEdits] = useState<Partial<Fields>>({})
  const [manual, setManual] = useState(false)
  const [actionError, setActionError] = useState('')
  const connected = status?.connected === true
  useEffect(() => { setActionError('') }, [connected])
  const busy = !!connectionPending || checking
  const available = portsRead.failed ? [] : ports
  const fields: Fields = {
    port: status?.port ?? (available.some((p) => p.device === params.port) ? params.port : ''),
    baudRate: String(params.baudRate), timeoutMs: String(params.timeoutMs),
    left: String(params.slaveId), right: String(params.rightSlaveId),
    ...(!connected && edits),
  }
  const manualEntry = manual && !connected
  const leftValid = inRange(fields.left, 1, 247)
  const rightValid = inRange(fields.right, 1, 247)
  const duplicate = leftValid && rightValid && Number(fields.left) === Number(fields.right)
  const addressError = !leftValid || !rightValid ? 'Введите целые адреса от 1 до 247.' : duplicate ? 'У левого и правого приводов должны быть разные адреса.' : ''
  const timeoutValid = inRange(fields.timeoutMs, 50, 5000)
  const valid = Boolean(fields.port.trim()) && timeoutValid && !addressError

  function edit(key: keyof Fields, value: string) {
    setEdits((prev) => ({ ...prev, [key]: value }))
    setActionError('')
  }

  async function changeConnection() {
    if (!status || busy || (!connected && !valid)) return
    if (connected && !status.simulationMode && !window.confirm('Отключить связь с приводами? Убедитесь, что гриф на упорах и тренажёр не используется.')) return
    clearCheck?.()
    setActionError('')
    try {
      if (connected) {
        await disconnect()
      } else {
        const result = await connect({ ...params, port: fields.port.trim(), baudRate: Number(fields.baudRate),
          timeoutMs: Number(fields.timeoutMs), slaveId: Number(fields.left), rightSlaveId: Number(fields.right) })
        if (!result.connected) {
          setActionError(result.errorMessage || 'Не удалось открыть порт. Проверьте адаптер и параметры связи.')
          return
        }
      }
      setEdits({})
      setManual(false)
    } catch (error) {
      setActionError(`Не удалось подтвердить ${connected ? 'отключение' : 'подключение'}.${error instanceof Error ? ` ${error.message}` : ''}`)
      refreshStatus() // The request may have reached the server. Reconcile, never retry the command.
    }
  }

  return <section className="mb-card mb-form" aria-labelledby="mb-form-title">
    <h2 id="mb-form-title">Параметры подключения</h2>
    <p className="mb-hint">{connected ? 'Чтобы изменить параметры, сначала отключите порт.' : 'Параметры применяются при нажатии «Подключиться».'}</p>
    <fieldset disabled={!status || connected || busy}>
      <legend><span aria-hidden="true">01</span> Порт и скорость</legend>
      <div className="mb-port-row">
        <label>Последовательный порт
          <select value={manualEntry ? manualOption : fields.port} onChange={(e) => {
            const custom = e.target.value === manualOption
            setManual(custom)
            edit('port', custom ? '' : e.target.value)
          }}>
            <option value="" disabled>Выберите порт адаптера</option>
            {available.map((p) => <option key={p.device} value={p.device}>{p.device}{p.description ? ` — ${p.description}` : ''}</option>)}
            {!manualEntry && fields.port && !available.some((p) => p.device === fields.port) && <option value={fields.port}>{fields.port} — текущий выбор</option>}
            <option value={manualOption}>Ввести порт вручную…</option>
          </select>
        </label>
        <Button type="button" variant="secondary" onClick={portsRead.refresh} disabled={portsRead.loading} iconLeft={<RefreshCw size={16} aria-hidden="true" />}>
          {portsRead.loading ? 'Поиск портов…' : 'Обновить порты'}
        </Button>
      </div>
      {manualEntry && <label>Имя порта<input type="text" autoComplete="off" spellCheck={false} placeholder="Например, COM3 или /dev/ttyUSB0" value={fields.port} onChange={(e) => edit('port', e.target.value)} /></label>}
      {!connected && !portsRead.loading && (portsRead.failed || !available.length) && <p className="mb-hint" role="status">
        {portsRead.failed ? 'Не удалось получить список портов.' : 'Порты не найдены.'} Подключите адаптер и обновите список или введите порт вручную.
      </p>}
      <div className="mb-field-pair">
        <label>Скорость, бод<select value={fields.baudRate} onChange={(e) => edit('baudRate', e.target.value)}>
          {!rates.includes(Number(fields.baudRate)) && <option>{fields.baudRate}</option>}
          {rates.map((rate) => <option key={rate}>{rate}</option>)}
        </select></label>
        <label>Таймаут ответа, мс<input type="number" inputMode="numeric" min={50} max={5000} step={1} value={fields.timeoutMs}
          aria-invalid={!timeoutValid} aria-describedby={!timeoutValid ? 'mb-timeout-error' : undefined} onChange={(e) => edit('timeoutMs', e.target.value)} /></label>
      </div>
      {!timeoutValid && <p id="mb-timeout-error" className="mb-error">Введите целое число от 50 до 5000 мс.</p>}
      <p className="mb-hint"><b>Формат 8E1:</b> 8 бит данных, проверка на чётность, 1 стоп-бит.</p>
    </fieldset>
    <fieldset disabled={!status || connected || busy}>
      <legend><span aria-hidden="true">02</span> Адреса приводов</legend>
      <p id="mb-address-hint" className="mb-hint">Укажите адрес (Slave ID), заданный на каждом приводе. Это не меняет адреса в самих приводах.</p>
      <div className="mb-field-pair">
        {(['left', 'right'] as const).map((side) => <label key={side}>{side === 'left' ? 'Левый привод' : 'Правый привод'} · ID
          <input type="number" inputMode="numeric" min={1} max={247} step={1} value={fields[side]}
            aria-invalid={duplicate || !(side === 'left' ? leftValid : rightValid)} aria-describedby={addressError ? 'mb-address-error' : 'mb-address-hint'}
            onChange={(e) => edit(side, e.target.value)} />
        </label>)}
      </div>
      {addressError && <p id="mb-address-error" className="mb-error">{addressError}</p>}
    </fieldset>
    {(actionError || status?.errorMessage) && <p className="mb-error" role="alert">{actionError || status?.errorMessage}</p>}
    <div className="mb-apply">
      <Button type="button" variant={connected ? 'secondary' : 'primary'} onClick={changeConnection} disabled={!status || busy || (!connected && !valid)}
        iconLeft={connected ? <Unlink size={17} aria-hidden="true" /> : <Link2 size={17} aria-hidden="true" />}>
        {connectionPending === 'connect' ? 'Подключаем…' : connectionPending === 'disconnect' ? 'Отключаем…' : connected ? 'Отключиться' : 'Подключиться'}
      </Button>
      <p className="mb-hint">Меняйте подключение, когда гриф на упорах и тренажёр не используется.</p>
    </div>
  </section>
}
