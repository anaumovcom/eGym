import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/shared/ui/button'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { useAppStore } from '@/stores/app-store'
import { capturePositionCalibration, changePositionLimit, enterPositionWeightless, fetchPositionCalibration, fetchPositionStatus, holdPosition, startPositionExercise, stopRaisePosition, zeroModbusPositions } from '@/features/modbus/api/modbus-api'
import type { PositionCalibration, PositionExercise, PositionMotionStatus } from '@/features/modbus/model/types'

const DEFAULT_EXERCISE: PositionExercise = {
  targetType: 'lower_boundary', lowerBoundaryMm: 400, fixedPositionMm: 1200,
  torqueLimit: 300, speedRpm: 30, minMm: 0, maxMm: 2000,
}
const STORAGE_PREFIX = 'egym-position-exercise:'

export function PositionExercisePanel() {
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const connected = useModbusStore((s) => s.connectionStatus?.connected ?? false)
  const simulated = useModbusStore((s) => s.connectionStatus?.simulationMode ?? false)
  const [slug, setSlug] = useState(searchParams.get('exercise') || 'default')
  const exerciseKey = `${selectedUserId ?? 'guest'}:${slug.trim()}`
  const [settings, setSettings] = useState<PositionExercise>(DEFAULT_EXERCISE)
  const [status, setStatus] = useState<PositionMotionStatus | null>(null)
  const [calibration, setCalibration] = useState<PositionCalibration | null>(null)
  const [weightlessTorque, setWeightlessTorque] = useState(1)
  const [noMotionThreshold, setNoMotionThreshold] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + exerciseKey)
      setSettings(saved ? { ...DEFAULT_EXERCISE, ...JSON.parse(saved) as PositionExercise } : DEFAULT_EXERCISE)
    } catch { setSettings(DEFAULT_EXERCISE) }
  }, [exerciseKey])

  useEffect(() => {
    if (!connected) { setStatus(null); return }
    let active = true
    let reading = false
    const refresh = async () => {
      if (reading) return
      reading = true
      try { const value = await fetchPositionStatus(); if (active) setStatus(value) }
      catch (err) { if (active) setError(err instanceof Error ? err.message : 'Нет связи Modbus') }
      finally { reading = false }
    }
    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 500)
    return () => { active = false; window.clearInterval(timer) }
  }, [connected])

  useEffect(() => {
    if (!connected || !slug.trim()) { setCalibration(null); return }
    let active = true
    setCalibration(null)
    void fetchPositionCalibration(exerciseKey).then((value) => { if (active) setCalibration(value) })
      .catch(() => { if (active) setCalibration(null) })
    return () => { active = false }
  }, [connected, exerciseKey, status?.positions.zeroGeneration])

  const update = (patch: Partial<PositionExercise>) => setSettings((previous) => ({ ...previous, ...patch }))
  const operation = async (action: () => Promise<PositionMotionStatus>) => {
    setBusy(true); setError(null)
    try { setStatus(await action()) }
    catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setBusy(false) }
  }
  const run = () => {
    const point = settings.targetType === 'lower_boundary' ? calibration?.lowerMm : calibration?.fixedMm
    if (!slug.trim() || !Number.isFinite(settings.minMm) || !Number.isFinite(settings.maxMm) ||
        settings.minMm >= settings.maxMm || !calibration || calibration.zeroGeneration !== status?.positions.zeroGeneration || point == null ||
        (settings.targetType === 'lower_boundary' && (calibration.upperMm == null || calibration.upperMm <= point))) {
      setError('Укажите упражнение и зафиксируйте нужные точки при текущем программном нуле'); return
    }
    localStorage.setItem(STORAGE_PREFIX + exerciseKey, JSON.stringify(settings))
    void operation(() => startPositionExercise({ ...settings, exerciseKey,
      lowerBoundaryMm: settings.targetType === 'lower_boundary' ? point : null,
      fixedPositionMm: settings.targetType === 'fixed_position' ? point : null }))
  }
  const capture = (point: 'lower' | 'upper' | 'fixed') => {
    setBusy(true); setError(null)
    void capturePositionCalibration(exerciseKey, point).then(setCalibration)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err))).finally(() => setBusy(false))
  }
  const numeric = (label: string, value: number | null, set: (value: number | null) => void, min?: number, max?: number) => (
    <label className="space-y-1 text-xs text-white/60">{label}
      <input type="number" className="input-field w-full" value={value ?? ''} min={min} max={max}
        onChange={(event) => set(event.target.value === '' ? null : Number(event.target.value))} />
    </label>
  )
  const positions = status?.positions
  const sides = ['left', 'right'] as const
  return <div className="space-y-4">
    <div role="alert" className="rounded-xl border border-[#ffd166]/40 bg-[#3d2f10]/40 p-4 text-sm text-[#ffd166]">
      STOP выполняет управляемый подъём грифа вверх. Это не заменяет аппаратный E-STOP.
      <p className="mt-2">В этом проекте контур реальных приводов заблокирован (E-CTRL-UNAVAILABLE): DI0, POS_LOAD, тормоз и аппаратная защита не проверены. Управление ниже работает только в симуляции. Не отключайте Servo-ON под нагрузкой.</p>
    </div>
    <section className="glass-panel space-y-4 rounded-2xl p-5">
      <h2 className="text-lg font-semibold text-[#f4dfb4]">Position mode · настройки упражнения</h2>
      <label className="block space-y-1 text-xs text-white/60">Ключ упражнения (параметры в этом браузере; точки на сервере до перезапуска/обнуления)
        <input className="input-field w-full" value={slug} onChange={(event) => setSlug(event.target.value)} />
      </label>
      <label className="block space-y-1 text-xs text-white/60">Тип цели
        <select className="input-field w-full" value={settings.targetType} onChange={(e) => update({ targetType: e.target.value as PositionExercise['targetType'] })}>
          <option value="lower_boundary">Стремление к нижней границе</option>
          <option value="fixed_position">Стремление к фиксированной позиции</option>
        </select>
      </label>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <p className="text-sm text-white/70">Цель из калибровки: {settings.targetType === 'lower_boundary' ? calibration?.lowerMm ?? '—' : calibration?.fixedMm ?? '—'} мм</p>
        {numeric('Лимит усилия, 0.1% (100 ≈ 10%)', settings.torqueLimit, (v) => update({ torqueLimit: v ?? 0 }), 1, 3000)}
        {numeric('Скорость, об/мин', settings.speedRpm, (v) => update({ speedRpm: v ?? 0 }), 1, 3000)}
        {numeric('Программный min, мм', settings.minMm, (v) => update({ minMm: v ?? 0 }))}
        {numeric('Программный max, мм', settings.maxMm, (v) => update({ maxMm: v ?? 0 }))}
      </div>
      <div className="space-y-2 rounded-xl border border-white/10 p-3 text-sm text-white/70">
        <p>Калибровка по двум энкодерам · программный ноль #{status?.positions.zeroGeneration ?? '—'}. Перекос не более 3 мм. Не используйте координаты другого контроллера для Position mode.</p>
        <p>Нижняя: {calibration?.lowerMm ?? '—'} мм · верхняя: {calibration?.upperMm ?? '—'} мм · фиксированная: {calibration?.fixedMm ?? '—'} мм</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={!simulated || busy || !slug.trim() || status?.state === 'exercise' || status?.state === 'raising'} onClick={() => capture('lower')}>Зафиксировать нижнюю</Button>
          <Button variant="secondary" disabled={!simulated || busy || !slug.trim() || status?.state === 'exercise' || status?.state === 'raising'} onClick={() => capture('upper')}>Зафиксировать верхнюю</Button>
          <Button variant="secondary" disabled={!simulated || busy || !slug.trim() || status?.state === 'exercise' || status?.state === 'raising'} onClick={() => capture('fixed')}>Зафиксировать фиксированную</Button>
        </div>
      </div>
      <div className="space-y-2 rounded-xl border border-[#ffd166]/30 p-3 text-sm text-white/70">
        <h3 className="font-semibold text-[#f4dfb4]">Невесомый гриф · цель 2000 мм</h3>
        <p>Задайте измеренный на механике порог момента, при котором гриф начинает двигаться без помощи человека. Лимит режима должен быть строго меньше порога. Значение 100 не является заведомо безопасным; программное ограничение не гарантирует ни невесомость, ни удержание груза. Только симуляция.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {numeric('Лимит невесомого грифа, 0.1%', weightlessTorque, (v) => setWeightlessTorque(v ?? 0), 1, 3000)}
          {numeric('Измеренный порог движения, 0.1%', noMotionThreshold, setNoMotionThreshold, 2, 3000)}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={!simulated || busy || noMotionThreshold == null || !Number.isInteger(weightlessTorque) || !Number.isInteger(noMotionThreshold) || weightlessTorque < 1 || weightlessTorque >= noMotionThreshold || status?.state === 'exercise' || status?.state === 'raising'} onClick={() => void operation(() => enterPositionWeightless(weightlessTorque, noMotionThreshold!, settings.speedRpm))}>Невесомый гриф (симуляция)</Button>
          <Button variant="secondary" disabled={!simulated || busy || !status || !['weightless', 'holding'].includes(status.state)} onClick={() => void operation(holdPosition)}>Удержать текущую позицию</Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!simulated || busy || !calibration || calibration.zeroGeneration !== status?.positions.zeroGeneration ||
          (settings.targetType === 'lower_boundary' ? calibration.lowerMm == null || calibration.upperMm == null : calibration.fixedMm == null)} onClick={run}>Запустить упражнение (симуляция)</Button>
        <Button variant="secondary" disabled={!simulated || busy || status?.state !== 'exercise'} onClick={() => void operation(() => changePositionLimit(settings.torqueLimit))}>Обновить только лимит</Button>
        <Button variant="danger" disabled={!simulated || busy} onClick={() => void operation(stopRaisePosition)}>STOP · подъём к 2000 мм</Button>
        <Button variant="secondary" disabled={!connected || busy || status?.state !== 'idle' && status?.state !== 'fault'} onClick={() => {
          setBusy(true); setError(null)
          void zeroModbusPositions().then(() => fetchPositionStatus()).then(setStatus).catch((err: unknown) => setError(err instanceof Error ? err.message : String(err))).finally(() => setBusy(false))
        }}>Обнулить позицию</Button>
      </div>
      {error && <p role="alert" className="text-sm text-[#ff8f84]">{error}</p>}
    </section>
    <section className="glass-panel space-y-3 rounded-2xl p-5" aria-label="Мониторинг позиции">
      <h2 className="font-semibold text-[#f4dfb4]">Мониторинг {status?.state ?? '—'}</h2>
      <p className="text-sm text-white/70">Цель: {status?.targetMm ?? '—'} мм · {status?.targetType === 'stop_raise' ? 'STOP · подъём' : status?.targetType === 'weightless' ? 'невесомый гриф' : status?.targetType === 'hold' ? 'удержание' : status?.targetType === 'lower_boundary' ? 'нижняя граница' : status?.targetType === 'fixed_position' ? 'фиксированная позиция' : '—'} · лимит: {status?.torqueLimit ?? '—'} · скорость: {status?.speedRpm ?? '—'} об/мин</p>
      <p className="text-sm text-white/70">Перекос: {positions?.skewMm?.toFixed(2) ?? '—'} мм · Modbus: {positions?.readiness.communicationReady ? 'связь есть' : 'нет связи'} · POS_LOAD: импульс при запуске, не удерживается</p>
      {status?.warning && <p role="status" className="text-[#ffd166]">{status.warning}</p>}
      {status?.error && <p role="alert" className="text-[#ff8f84]">{status.error}. При работе с реальным грифом используйте аппаратную защиту.</p>}
      <div className="grid gap-3 sm:grid-cols-2">{sides.map((side) => {
        const drive = status?.drives[side]
        return <div key={side} className="rounded-xl border border-white/10 p-3 text-sm text-white/70">
          <h3 className="font-semibold text-white">{side === 'left' ? 'Левый' : 'Правый'} привод</h3>
          <p>Позиция: {positions?.[side].positionMm?.toFixed(2) ?? '—'} мм · Servo-ON: {status?.servoOn[side] ? 'да' : 'нет/неизвестно'}</p>
          <p>Позиционная ошибка: {drive?.position_error_mm ?? '—'} мм · движение: {drive?.speed_actual == null ? 'неизвестно' : drive.speed_actual === 0 ? 'скорость 0' : 'есть'}</p>
          <p>Скорость фактическая / командная: {drive?.speed_actual ?? '—'} / {drive?.speed_command ?? '—'} об/мин</p>
          <p>Момент фактический / командный / отклонение: {drive?.torque_actual ?? '—'} / {drive?.torque_command ?? '—'} / {drive?.torque_error ?? '—'}</p>
          <p>Статус: {drive?.system_status ?? '—'} · ошибка: {drive?.error_code ?? '—'} · авария: {drive?.alarm ?? '—'}</p>
          <p>Причина отсутствия движения: не подтверждена документацией драйвера; диагностика по скорости/моменту доступна в симуляции.</p>
          <p>POS_LOAD: {status?.posLoad[side] ? 'активен' : 'не активен/неизвестно'}</p>
        </div>
      })}</div>
    </section>
  </div>
}
