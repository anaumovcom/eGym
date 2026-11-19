import { Activity, ArrowUpRight, CheckCircle2, Download, PlayCircle, RefreshCw, Wifi, Wrench } from 'lucide-react'
import { useEffect, useMemo, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { SettingsTab, SystemSettingsData } from '@/entities/stage4/model/types'
import { useHardwareStore } from '@/stores/hardware-store'
import { buildSystemSettingsData, settingsTabs } from '@/mocks/stage4-data'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { useStage4Screen } from '@/features/stage4/lib/use-stage4-screen'
import { useStage4Store } from '@/stores/stage4-store'
import { CoachSettingsPanel } from '@/features/coach/ui/coach-settings-panel'
import './system-settings-screen.css'

const normalSettingsTabs = [
  { id: 'overview', label: 'Обзор' },
  { id: 'safety', label: 'Безопасность' },
  { id: 'common', label: 'Общие' },
  { id: 'coach', label: 'AI-тренер' },
  { id: 'service', label: 'Сервис' },
]
const serviceSettingsTabs = settingsTabs.filter(({ id }) => !['overview', 'safety', 'common', 'coach'].includes(id))

function asSettingsTab(value: string | null): SettingsTab {
  if (value === 'overview' || value === 'safety' || value === 'mechanics' || value === 'diagnostics' || value === 'calibrations' || value === 'service' || value === 'journal' || value === 'common' || value === 'coach') {
    return value
  }

  return 'overview'
}

function buildSettingsDraft(data: SystemSettingsData) {
  return {
    interfaceTheme: data.common.interfaceTheme,
    interfaceScale: data.common.interfaceScale,
    language: data.common.language,
    units: data.common.units,
    brightnessMode: data.common.brightnessMode,
    autoReturnMinutes: data.common.autoReturnMinutes,
    soundEnabled: data.common.soundEnabled,
    voiceHintsEnabled: data.common.voiceHintsEnabled,
    signalVolume: data.common.signalVolume,
    wifiMode: data.common.wifiMode,
    networkStatus: data.common.networkStatus,
    guestMode: data.safety.guestMode,
    guestWeightLimit: data.safety.guestWeightLimit,
    workoutPin: data.safety.workoutPin,
    servicePin: data.safety.servicePin,
    childLock: data.safety.childLock,
    idleLockMinutes: data.safety.idleLockMinutes,
    maxLoad: data.safety.maxLoad,
    maxSpeed: data.safety.maxSpeed,
    syncLimit: data.safety.syncLimit,
    desyncAction: data.safety.desyncAction,
  }
}

function formatMillimeters(value?: number | null) {
  if (value == null) {
    return '—'
  }

  return `${value.toFixed(1)} мм`
}

function formatTemperature(value?: number | null) {
  if (value == null) {
    return '—'
  }

  return `${value.toFixed(1)}°C`
}

function formatSpeed(value?: number | null) {
  if (value == null) {
    return '—'
  }

  return `${value.toFixed(0)} мм/с`
}

function servoLabel(value?: boolean | null) {
  return value == null ? 'неизвестно' : value ? 'включён' : 'выключен'
}

export function SystemSettingsScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { selectedUserId, userName, emergencyStopActive, setEmergencyStopActive, dev, settingsDraft } = useStage4Screen()
  const setSettingsValue = useStage4Store((state) => state.setSettingsValue)
  const hydrateSettingsDraft = useStage4Store((state) => state.hydrateSettingsDraft)
  const saveSettingsDraft = useStage4Store((state) => state.saveSettingsDraft)
  const cancelSettingsDraft = useStage4Store((state) => state.cancelSettingsDraft)
  const resetSettingsToDefaults = useStage4Store((state) => state.resetSettingsToDefaults)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const connectionStatus = useHardwareStore((state) => state.connectionStatus)
  const liveSettings = useHardwareStore((state) => state.settings)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const loadSettings = useHardwareStore((state) => state.loadSettings)
  const updateSafetySettings = useHardwareStore((state) => state.updateSafetySettings)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const tab = asSettingsTab(searchParams.get('tab'))
  const isServiceTab = serviceSettingsTabs.some(({ id }) => id === tab)
  const connectionLost = connectionStatus === 'disconnected' || connectionStatus === 'error'

  const fallbackData = useMemo(() => buildSystemSettingsData(dev), [dev])

  useEffect(() => {
    void loadSettings(selectedUserId).catch(() => {})
  }, [loadSettings, selectedUserId])

  useEffect(() => {
    if (liveSettings) {
      hydrateSettingsDraft(buildSettingsDraft(liveSettings))
    }
  }, [hydrateSettingsDraft, liveSettings])

  useEffect(() => {
    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }
  }, [setEmergencyStopActive, snapshot?.safety.state])

  const data = useMemo(() => {
    const baseData = liveSettings ?? fallbackData
    if (!snapshot) {
      return baseData
    }

    const leftDrive = snapshot.drives.find((drive) => drive.side === 'left') ?? snapshot.drives[0]
    const rightDrive = snapshot.drives.find((drive) => drive.side === 'right') ?? snapshot.drives[1] ?? leftDrive
    const delta = snapshot.motion.syncDeltaMm ?? snapshot.motion.leftPositionMm - snapshot.motion.rightPositionMm
    const syncLabel = snapshot.motion.syncAvailable === false || !Number.isFinite(delta) ? 'Нет парного замера' : `${delta.toFixed(1)} мм`

    return {
      ...baseData,
      machine: snapshot.machine,
      overviewCards: [
        { label: 'Статус', value: snapshot.machine.machineLabel, tone: snapshot.machine.machineState === 'ready' ? 'good' : 'warning' },
        { label: 'Эмулятор', value: snapshot.emulatorMode ? 'Включён' : 'Отключён', hint: 'mode' },
        { label: 'Синхронность', value: syncLabel, hint: 'левая минус правая' },
        { label: 'Калибровка', value: snapshot.machine.calibration, hint: 'диапазон' },
      ],
      mechanics: {
        ...baseData.mechanics,
        statusSummary: [
          { label: 'Механика', value: snapshot.machine.machineLabel, hint: 'общее состояние' },
          { label: 'Запуск', value: snapshot.safety.state === 'enabled' && snapshot.machine.machineState !== 'blocked' ? 'Разрешён' : 'Заблокирован', hint: 'safety gate' },
        ],
        leftDrive: leftDrive
          ? [
              { label: 'Состояние', value: leftDrive.connected ? 'Подключён' : 'Не подключён', tone: leftDrive.connected ? 'good' : 'danger' },
              { label: 'Позиция', value: formatMillimeters(leftDrive.positionMm) },
              { label: 'Скорость', value: formatSpeed(leftDrive.speedMmPerSec) },
              { label: 'Температура', value: formatTemperature(leftDrive.temperatureC) },
            ]
          : baseData.mechanics.leftDrive,
        rightDrive: rightDrive
          ? [
              { label: 'Состояние', value: rightDrive.connected ? 'Подключён' : 'Не подключён', tone: rightDrive.connected ? 'good' : 'danger' },
              { label: 'Позиция', value: formatMillimeters(rightDrive.positionMm) },
              { label: 'Скорость', value: formatSpeed(rightDrive.speedMmPerSec) },
              { label: 'Температура', value: formatTemperature(rightDrive.temperatureC) },
            ]
          : baseData.mechanics.rightDrive,
        sync: [
          { label: 'Разница сторон', value: syncLabel },
          { label: 'Допуск', value: baseData.safety.syncLimit },
          { label: 'Действие', value: baseData.safety.desyncAction },
        ],
        motion: [
          { label: 'Профиль', value: snapshot.motion.motionProfile },
          { label: 'Направление', value: snapshot.motion.moving ? snapshot.motion.direction : 'остановлено' },
          { label: 'Амплитуда', value: `${snapshot.motion.amplitudePercent}%` },
          { label: 'Темп', value: snapshot.motion.tempoLabel },
        ],
        screw: [
          { label: 'Ход', value: '2100 мм' },
          { label: 'Текущая позиция', value: formatMillimeters(snapshot.motion.barPositionMm) },
          { label: 'Нижняя граница', value: snapshot.motion.lowerBoundMm != null ? formatMillimeters(snapshot.motion.lowerBoundMm) : '—' },
          { label: 'Верхняя граница', value: snapshot.motion.upperBoundMm != null ? formatMillimeters(snapshot.motion.upperBoundMm) : '—' },
        ],
        service: [
          { label: 'Сервисный режим', value: snapshot.serviceMode ? 'Включён' : 'Отключён' },
          { label: 'Последняя диагностика', value: snapshot.lastDiagnosticsAt ?? 'нет данных' },
          { label: 'Команд в очереди', value: String(snapshot.commandQueueDepth) },
        ],
      },
      service: {
        ...baseData.service,
        unlocked: snapshot.serviceMode,
        positions: [
          { label: 'Гриф', value: formatMillimeters(snapshot.motion.barPositionMm) },
          { label: 'Левый привод', value: formatMillimeters(snapshot.motion.leftPositionMm) },
          { label: 'Правый привод', value: formatMillimeters(snapshot.motion.rightPositionMm) },
          { label: 'Рассинхрон', value: syncLabel },
        ],
        driveHealth: [
          { label: 'Левый привод', value: leftDrive?.status ?? '—', tone: leftDrive?.status === 'connected' ? 'good' : leftDrive?.status === 'warning' ? 'warning' : 'danger' },
          { label: 'Правый привод', value: rightDrive?.status ?? '—', tone: rightDrive?.status === 'connected' ? 'good' : rightDrive?.status === 'warning' ? 'warning' : 'danger' },
          { label: 'Безопасность', value: snapshot.safety.label, tone: snapshot.safety.state === 'enabled' ? 'good' : 'warning' },
          { label: 'Последняя команда', value: snapshot.lastCommand?.action ?? 'нет' },
        ],
      },
    }
  }, [fallbackData, liveSettings, snapshot])

  const common = {
    ...data.common,
    interfaceTheme: settingsDraft.interfaceTheme === 'light' ? 'light' : 'dark',
    interfaceScale: settingsDraft.interfaceScale === '125%' || settingsDraft.interfaceScale === '150%' ? settingsDraft.interfaceScale : '100%',
    language: settingsDraft.language === 'English' ? 'English' : 'Русский',
    units: settingsDraft.units === 'lb / in' ? 'lb / in' : 'kg / cm',
    brightnessMode: settingsDraft.brightnessMode === 'Вручную' ? 'Вручную' : 'Авто',
    autoReturnMinutes: String(settingsDraft.autoReturnMinutes),
    soundEnabled: Boolean(settingsDraft.soundEnabled),
    voiceHintsEnabled: Boolean(settingsDraft.voiceHintsEnabled),
    signalVolume: String(settingsDraft.signalVolume),
    wifiMode: String(settingsDraft.wifiMode),
    networkStatus: String(settingsDraft.networkStatus ?? data.common.networkStatus),
  }

  const safetyDraft = {
    childLock: Boolean(settingsDraft.childLock),
    workoutPin: Boolean(settingsDraft.workoutPin),
    servicePin: Boolean(settingsDraft.servicePin),
    idleLockMinutes: String(settingsDraft.idleLockMinutes),
    guestMode: Boolean(settingsDraft.guestMode),
    guestWeightLimit: String(settingsDraft.guestWeightLimit),
    maxLoad: String(settingsDraft.maxLoad),
    maxSpeed: String(settingsDraft.maxSpeed),
    syncLimit: String(settingsDraft.syncLimit),
    desyncAction: String(settingsDraft.desyncAction),
  }

  function updateTab(nextTab: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('tab', nextTab)
      return next
    })
  }

  async function refreshSettings() {
    await loadSettings(selectedUserId)
  }

  async function handleSafetySave() {
    if (liveSettings) {
      await updateSafetySettings(safetyDraft, selectedUserId)
      await refreshSettings()
    }

    saveSettingsDraft()
  }

  async function handleRunDiagnostics() {
    await runCommand({ action: 'run_diagnostics', userId: selectedUserId })
    await refreshSettings()
  }

  async function handleClearEmergencyStop() {
    await runCommand({ action: 'clear_emergency_stop', userId: selectedUserId })
    setEmergencyStopActive(false)
    await refreshSettings()
  }

  async function handleServiceModeToggle() {
    await runCommand({ action: 'toggle_service_mode', userId: selectedUserId, serviceMode: !data.service.unlocked })
    await refreshSettings()
  }

  async function handleServo(on: boolean) {
    const warning = on
      ? 'Включить оба привода (SRV-ON)? Приводы сразу дадут момент поддержки вверх.'
      : 'Выключить оба привода? Поднятый гриф упадёт: тормоза нет. Убедитесь, что гриф лежит на упорах.'
    if (!window.confirm(warning)) return
    try {
      await runCommand({ action: on ? 'servo_on' : 'servo_off', userId: selectedUserId, serviceMode: true })
    } catch {
      // the store keeps the error message for display
    }
    await refreshSettings()
  }

  async function handleServiceAction(title: string) {
    if (title === 'Homing') {
      await runCommand({ action: 'home', userId: selectedUserId, serviceMode: data.service.unlocked })
    } else if (title === 'Сброс нуля') {
      await runCommand({ action: 'reset_zero_position', userId: selectedUserId, serviceMode: data.service.unlocked })
    } else if (title === 'Запуск диагностики') {
      await handleRunDiagnostics()
      return
    }

    await refreshSettings()
  }

  const hasMachineData = Boolean(snapshot || liveSettings)
  const machineSummary = connectionLost || !hasMachineData ? 'Нет связи' : data.machine.machineLabel

  return (
    <FormaShell
      userName={userName}
      machine={snapshot?.machine ?? data.machine}
      onStop={() => {
        void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId })
        setEmergencyStopActive(true)
      }}
    >
      <div className="settings-console">
      <header className="settings-hero">
        <p className="settings-kicker">{isServiceTab ? 'Техническое обслуживание' : 'Тренажёр Forma'}</p>
        <h1>Настройки</h1>
        <p>{isServiceTab ? 'Диагностика и обслуживание тренажёра. Раздел для оператора.' : 'Проверьте состояние тренажёра или настройте его для тренировки.'}</p>
      </header>

      {hardwareError ? (
        <div className="rt-alert" data-tone="danger" role="alert">
          <div />
          <div>
            <strong>Ошибка тренажёра</strong>
            <p>{hardwareError}</p>
          </div>
          <span />
        </div>
      ) : null}

      <nav aria-label="Настройки" className="settings-nav">
        <TabStrip tabs={normalSettingsTabs.slice(0, -1)} active={tab} onChange={updateTab} />
        <div className="settings-operator-nav">
          <span className="settings-kicker">Для оператора</span>
          <TabStrip tabs={normalSettingsTabs.slice(-1)} active={isServiceTab ? 'service' : tab} onChange={updateTab} />
        </div>
      </nav>

      {tab === 'overview' ? (
        <div className="settings-stack">
          <Panel title="Состояние тренажёра">
            <div className="settings-readiness" data-tone={connectionLost || !hasMachineData ? 'warning' : data.machine.machineState === 'blocked' ? 'danger' : data.machine.machineState === 'ready' ? 'good' : 'warning'}>
              <Activity aria-hidden="true" size={24} />
              <div>
                <strong>{machineSummary}</strong>
                <p>{connectionLost ? 'Последние полученные данные могут быть неактуальны.' : !hasMachineData ? 'Данные о готовности ещё не получены.' : snapshot?.safety.message || (snapshot ? 'По последнему снимку состояния' : 'По данным последней загрузки настроек')}</p>
              </div>
            </div>
            {hasMachineData ? <MetricCardGrid items={data.overviewCards.filter(({ label }) => label !== 'Статус' && label !== 'Статус системы')} /> : null}
          </Panel>
          <div className="settings-grid settings-overview-grid">
            <Panel title="Последние события">
              {liveSettings?.overviewEvents.length ? (
                <ul className="settings-event-list">
                  {liveSettings.overviewEvents.map((event, index) => (
                    <li key={`${event.time}-${index}`} data-tone={event.tone}>
                      <span className="settings-event-time">{event.time}</span><span>{event.title}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="settings-muted">Нет данных о последних событиях.</p>}
            </Panel>
            <Panel title="Калибровки">
              <InfoMetricList items={[
                { label: 'Последнее обновление', value: liveSettings?.calibrations.lastUpdate ?? '—' },
                { label: 'Сохранено', value: liveSettings?.calibrations.total ?? '—' },
                { label: 'Устаревшие', value: liveSettings?.calibrations.staleCount ?? '—' },
              ]} />
            </Panel>
            <Panel title="Быстрые переходы">
              <div className="settings-stack settings-shortcuts">
                <Link to="/settings?tab=safety">Безопасность <ArrowUpRight size={16} aria-hidden="true" /></Link>
                <Link to="/settings?tab=common">Общие настройки <ArrowUpRight size={16} aria-hidden="true" /></Link>
                <Link to="/settings?tab=service">Открыть сервисный раздел <ArrowUpRight size={16} aria-hidden="true" /></Link>
              </div>
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === 'safety' ? (
        <div className="settings-stack">
          <div className="settings-grid">
            <Panel title="Защита и доступ" description="Запуск тренировки, сервисный доступ и ограничения для гостей.">
              <div className="settings-fields">
                <ToggleField label="Детская защита" checked={safetyDraft.childLock} editable onChange={(value) => setSettingsValue('childLock', value)} />
                <ToggleField label="PIN для запуска тренировки" checked={safetyDraft.workoutPin} editable onChange={(value) => setSettingsValue('workoutPin', value)} />
                <ToggleField label="PIN для сервисного режима" checked={safetyDraft.servicePin} editable onChange={(value) => setSettingsValue('servicePin', value)} />
                <ToggleField label="Гостевой режим" checked={safetyDraft.guestMode} editable onChange={(value) => setSettingsValue('guestMode', value)} />
                <SelectField label="Автоблокировка" value={safetyDraft.idleLockMinutes} options={['2 минуты', '5 минут', '10 минут']} onChange={(value) => setSettingsValue('idleLockMinutes', value)} />
              </div>
            </Panel>
            <Panel title="Лимиты безопасности">
              <SelectField label="Максимальная нагрузка" value={safetyDraft.maxLoad} options={['60 кг', '80 кг', '100 кг']} onChange={(value) => setSettingsValue('maxLoad', value)} />
              <SelectField label="Максимальная скорость движения" value={safetyDraft.maxSpeed} options={['Низкая', 'Средняя', 'Высокая']} onChange={(value) => setSettingsValue('maxSpeed', value)} />
              <SelectField label="Максимальная разница сторон" value={safetyDraft.syncLimit} options={['3 мм', '5 мм', '8 мм']} onChange={(value) => setSettingsValue('syncLimit', value)} />
              <SelectField label="Действие при рассинхроне" value={safetyDraft.desyncAction} options={['Остановить движение', 'Предупреждение', 'Снизить скорость']} onChange={(value) => setSettingsValue('desyncAction', value)} />
              <SelectField label="Макс. нагрузка в гостевом режиме" value={safetyDraft.guestWeightLimit} options={['20 кг', '30 кг', '40 кг']} onChange={(value) => setSettingsValue('guestWeightLimit', value)} />
            </Panel>
          </div>
          <SettingsActions onSave={() => void handleSafetySave()} onCancel={cancelSettingsDraft} onReset={resetSettingsToDefaults} />
          <Panel title="Аварийная остановка" description={snapshot?.safety.message || 'Программная остановка не заменяет физическую аварийную остановку.'}>
            {liveSettings ? <ToggleField label="Аварийная остановка готова" checked={data.safety.emergencyReady} editable={false} onChange={() => {}} /> : null}
            {snapshot?.safety.state === 'emergency_stop' ? (
              <Button variant="secondary" onClick={() => void handleClearEmergencyStop()}>Снять аварийную остановку</Button>
            ) : null}
          </Panel>
        </div>
      ) : null}

      {isServiceTab ? (
          <section aria-label="Сервисный раздел" className="settings-stack">
            <div className="settings-service-nav">
              <div className="settings-service-label"><Wrench size={17} aria-hidden="true" /><h2>Рабочая зона оператора</h2></div>
              <nav aria-label="Сервисные настройки">
                <TabStrip tabs={serviceSettingsTabs} active={tab} onChange={updateTab} />
              </nav>
              <div className="settings-shortcuts settings-tools">
                <Link to="/settings/drives">Подключение приводов <ArrowUpRight size={16} aria-hidden="true" /></Link>
                <Link to="/motor-calibration">Калибровки привода <ArrowUpRight size={16} aria-hidden="true" /></Link>
                <Link to="/modbus">Modbus Debug <ArrowUpRight size={16} aria-hidden="true" /></Link>
              </div>
            </div>

      {tab === 'mechanics' ? (
        <div className="space-y-6">
          <div className="settings-grid settings-overview-grid">
            <Panel title="Состояние механики"><InfoMetricList items={data.mechanics.statusSummary} /></Panel>
            <Panel title="Левый привод"><InfoMetricList items={data.mechanics.leftDrive} /></Panel>
            <Panel title="Правый привод"><InfoMetricList items={data.mechanics.rightDrive} /></Panel>
            <Panel title="Синхронизация"><InfoMetricList items={data.mechanics.sync} /></Panel>
            <Panel title="Параметры движения"><InfoMetricList items={data.mechanics.motion} /></Panel>
            <Panel title="Параметры ШВП"><InfoMetricList items={data.mechanics.screw} /></Panel>
            <Panel title="Обслуживание"><InfoMetricList items={data.mechanics.service} /></Panel>
          </div>
        </div>
      ) : null}

      {tab === 'diagnostics' ? (
        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-6">
            <Panel title="Сводка диагностики" description="Состояние и результаты последней проверки.">
              <div className="settings-metrics">
                <StatBox label="Последний запуск" value={data.diagnostics.lastRun} />
                <StatBox label="Проверено" value={data.diagnostics.checked} />
                <StatBox label="Успешно" value={data.diagnostics.success} />
                <StatBox label="Ошибки" value={data.diagnostics.errors} />
                <StatBox label="Статус" value={data.diagnostics.systemStatus} />
              </div>
            </Panel>
            <div className="grid gap-6 xl:grid-cols-2">
              <Panel title="Проверенные элементы">
                <div className="space-y-3">
                  {data.diagnostics.checklist.map((item) => (
                    <div key={item.label} className="flex items-center justify-between gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75"><span>{item.label}</span><span className="text-[#79de83]">{item.result}</span></div>
                  ))}
                </div>
              </Panel>
              <Panel title="Быстрые тесты">
                <div className="space-y-3">
                  {data.diagnostics.quickTests.map((item) => (
                    <button key={item.title} type="button" className="flex w-full items-center justify-between rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-left text-sm text-white/75">
                      <span>
                        <div className="text-white">{item.title}</div>
                        <div className="mt-1 text-xs text-white/45">{item.description}</div>
                      </span>
                      <span>›</span>
                    </button>
                  ))}
                </div>
              </Panel>
            </div>
          </div>
          <Panel title="Последние результаты">
            <div className="space-y-3">
              {data.diagnostics.history.map((item) => (
                <div key={item.label} className="rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
                  <div className="flex items-center justify-between gap-3"><span>{item.label}</span><span>{item.result}</span></div>
                  <div className="mt-1 text-xs text-white/45">{item.hint}</div>
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-col gap-3">
              <Button iconLeft={<PlayCircle className="h-4 w-4" />} onClick={() => void handleRunDiagnostics()}>Запустить полную диагностику</Button>
              <Button variant="secondary" iconLeft={<RefreshCw className="h-4 w-4" />} onClick={() => void handleRunDiagnostics()}>Повторить</Button>
              <Button variant="secondary" onClick={() => updateTab('journal')}>Открыть журнал</Button>
            </div>
          </Panel>
        </div>
      ) : null}

      {tab === 'calibrations' ? (
        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <Panel title="Сохранённые калибровки" description="Эти значения используются для контроля амплитуды, безопасности и прогресса.">
            <div className="settings-table-scroll" role="region" aria-label="Таблица сохранённых калибровок" tabIndex={0}>
              <div className="settings-calibration-row settings-table-head">
                <div>Упражнение</div>
                <div>Нижняя точка</div>
                <div>Верхняя точка</div>
                <div>Дата</div>
                <div>Статус</div>
                <div>Действия</div>
              </div>
              {data.calibrations.entries.map((entry) => (
                <div key={entry.id} className="settings-calibration-row">
                  <div>
                    <div className="font-medium text-white">{entry.exercise}</div>
                    <div className="mt-1 text-xs text-white/45">{entry.muscle}</div>
                  </div>
                  <div>{entry.lowerPoint}</div>
                  <div>{entry.upperPoint}</div>
                  <div>{entry.updatedAt}</div>
                  <div className={entry.status === 'actual' ? 'text-[#79de83]' : 'text-[#ff8f84]'}>{entry.status === 'actual' ? 'Актуальна' : 'Устарела'}</div>
                  <div className="flex gap-2"><Button variant="secondary" className="min-h-10 px-3 py-2">Открыть</Button></div>
                </div>
              ))}
            </div>
            <Button asChild className="mt-5" variant="secondary"><Link to="/motor-calibration">Настроить механику тренажёра</Link></Button>
          </Panel>
          <div className="space-y-6">
            <Panel title="Итоги по калибровкам">
              <StatBox label="Всего калибровок" value={data.calibrations.total} />
              <StatBox label="Последнее обновление" value={data.calibrations.lastUpdate} />
              <StatBox label="Устаревшие" value={data.calibrations.staleCount} />
              <StatBox label="Без калибровки" value={data.calibrations.missingCount} />
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === 'service' ? (
        <div className="settings-stack">
          <div className="settings-grid">
            <Panel title="Текущие позиции"><InfoMetricList items={data.service.positions} /></Panel>
            <Panel title="Состояние приводов">
              <InfoMetricList items={data.service.driveHealth} />
              <p className="settings-muted mt-3">Серво: левый — {servoLabel(snapshot?.control?.servo?.left)}, правый — {servoLabel(snapshot?.control?.servo?.right)}</p>
            </Panel>
          </div>
          <div className="settings-grid">
            <Panel title="Команды обслуживания" description="Программная остановка не заменяет физическую аварийную остановку.">
              <div className="mb-3 flex flex-wrap gap-3">
                <Button variant="secondary" onClick={() => void handleServiceModeToggle()}>{data.service.unlocked ? 'Выключить сервисный режим' : 'Включить сервисный режим'}</Button>
                {data.service.unlocked ? (
                  <>
                    <Button variant="secondary" onClick={() => void handleServo(true)}>Включить приводы</Button>
                    <Button variant="secondary" onClick={() => void handleServo(false)}>Выключить приводы</Button>
                  </>
                ) : null}
              </div>
              <div className="settings-stack settings-shortcuts">
                {data.service.actions.map((action) => (
                  <button key={action.title} type="button" onClick={() => void handleServiceAction(action.title)} className="rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-left text-sm text-white/75">
                    <div className="text-white">{action.title}</div>
                    <div className="mt-1 text-xs text-white/45">{action.description}</div>
                  </button>
                ))}
              </div>
            </Panel>
          <Panel title="Журнал сервисных действий">
            <div className="space-y-3">
              {data.service.journal.map((item) => (
                <div key={`${item.time}-${item.action}`} className="flex items-center justify-between gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
                  <div>
                    <div className="text-white">{item.action}</div>
                    <div className="mt-1 text-xs text-white/45">{item.time}</div>
                  </div>
                  <span>{item.result}</span>
                </div>
              ))}
            </div>
          </Panel>
          </div>
        </div>
      ) : null}

      {tab === 'journal' ? (
        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <Panel title="Журнал событий" description="История ошибок, предупреждений, калибровок, тренировок и сервисных действий.">
            <div className="mb-4 flex flex-wrap gap-3">
              <Button variant="secondary" iconLeft={<Download className="h-4 w-4" />}>Экспортировать</Button>
              <Button variant="secondary">Очистить фильтр</Button>
            </div>
            <div className="space-y-3">
              {data.journal.entries.map((entry) => (
                <div key={entry.id} className="settings-journal-row">
                  <div><strong>{entry.title}</strong><p>{entry.description}</p></div>
                  <div className="settings-journal-meta"><span>{entry.date}</span><span>{entry.category}</span><span data-tone={entry.level === 'critical' ? 'danger' : entry.level === 'success' ? 'good' : entry.level}>{entry.level}</span></div>
                  <Button variant="secondary" className="min-h-10 px-3 py-2">Подробнее</Button>
                </div>
              ))}
            </div>
          </Panel>
          <div className="space-y-6">
            <Panel title="Сводка за 30 дней"><MetricCardGrid items={data.journal.stats} /></Panel>
          </div>
        </div>
      ) : null}

          </section>
      ) : null}

      {tab === 'common' ? (
        <div className="settings-stack">
          <div className="settings-grid settings-overview-grid">
          <Panel title="Интерфейс">
            <SegmentedField label="Тема оформления" value={common.interfaceTheme} options={[['dark', 'Тёмная'], ['light', 'Светлая']]} onChange={(value) => setSettingsValue('interfaceTheme', value)} />
            <SegmentedField label="Масштаб интерфейса" value={common.interfaceScale} options={[['100%', 'Нормальный'], ['125%', 'Крупный'], ['150%', 'Очень крупный']]} onChange={(value) => setSettingsValue('interfaceScale', value)} />
            <SegmentedField label="Язык интерфейса" value={common.language} options={[['Русский', 'Русский'], ['English', 'English']]} onChange={(value) => setSettingsValue('language', value)} />
            <SegmentedField label="Система единиц" value={common.units} options={[['kg / cm', 'Метрическая'], ['lb / in', 'Имперская']]} onChange={(value) => setSettingsValue('units', value)} />
          </Panel>
          <Panel title="Экран и система">
            <SegmentedField label="Яркость" value={common.brightnessMode} options={[['Авто', 'Авто'], ['Вручную', 'Вручную']]} onChange={(value) => setSettingsValue('brightnessMode', value)} />
            <SelectField label="Автовозврат к пользователю" value={common.autoReturnMinutes} options={['2 минуты', '5 минут', '10 минут']} onChange={(value) => setSettingsValue('autoReturnMinutes', value)} />
            <div className="grid gap-3 xl:grid-cols-2">
              <StatBox label="Версия ПО" value={data.common.version} />
              <StatBox label="Серийный номер" value={data.common.serialNumber} />
            </div>
          </Panel>
          <Panel title="Звук и голос">
            <ToggleField label="Звук" checked={common.soundEnabled} editable onChange={(value) => setSettingsValue('soundEnabled', value)} />
            <ToggleField label="Голосовые подсказки" checked={common.voiceHintsEnabled} editable onChange={(value) => setSettingsValue('voiceHintsEnabled', value)} />
            <SelectField label="Громкость сигналов" value={common.signalVolume} options={['30%', '50%', '70%', '100%']} onChange={(value) => setSettingsValue('signalVolume', value)} />
          </Panel>
          <Panel title="Подключение">
            <SelectField label="Режим подключения" value={common.wifiMode} options={['Wi-Fi', 'Ethernet']} onChange={(value) => setSettingsValue('wifiMode', value)} />
            <div className="rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
              <div className="flex items-center gap-2 text-white"><Wifi className="h-4 w-4" />{data.common.ssid}</div>
              <div className="mt-2">{data.common.networkStatus} · {data.common.signalStrength}</div>
              <div className="mt-1 text-white/45">{data.common.ipAddress}</div>
            </div>
          </Panel>
          </div>
          <SettingsActions onSave={saveSettingsDraft} onCancel={cancelSettingsDraft} onReset={resetSettingsToDefaults} />
        </div>
      ) : null}

      {tab === 'coach' ? <CoachSettingsPanel /> : null}
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

type SettingsMetric = { label: string; value: string; hint?: string; tone?: string }

function Panel({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="settings-panel">
      <header><h2>{title}</h2>{description ? <p>{description}</p> : null}</header>
      {children}
    </section>
  )
}

function TabStrip({ tabs, active, onChange }: { tabs: { id: string; label: string }[]; active: string; onChange: (tab: string) => void }) {
  return (
    <div className="settings-tabs">
      {tabs.map(({ id, label }) => <button key={id} type="button" aria-current={active === id ? 'page' : undefined} onClick={() => onChange(id)}>{label}</button>)}
    </div>
  )
}

function MetricCardGrid({ items }: { items: SettingsMetric[] }) {
  return <div className="settings-metrics">{items.map((item) => <StatBox key={item.label} {...item} />)}</div>
}

function SettingsActions({ onSave, onCancel, onReset }: { onSave: () => void; onCancel: () => void; onReset: () => void }) {
  return (
    <footer className="settings-actions">
      <h2>Изменения настроек</h2>
      <div className="flex flex-wrap gap-2">
        <Button variant="ghost" onClick={onReset}>Сбросить по умолчанию</Button>
        <Button variant="secondary" onClick={onCancel}>Отменить</Button>
        <Button iconLeft={<CheckCircle2 className="h-4 w-4" />} onClick={onSave}>Сохранить изменения</Button>
      </div>
    </footer>
  )
}

function InfoMetricList({ items }: { items: SettingsMetric[] }) {
  return (
    <dl className="settings-readouts">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}{item.hint ? <small>{item.hint}</small> : null}</dt>
          <dd data-tone={item.tone}>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function ToggleField({ label, checked, editable, onChange }: { label: string; checked: boolean; editable: boolean; onChange: (value: boolean) => void }) {
  return (
    <div className="settings-field settings-toggle-field">
      <span>{label}</span>
      {editable ? (
        <button type="button" role="switch" aria-checked={checked} title={label} aria-label={label} onClick={() => onChange(!checked)} className="settings-switch">
          <span aria-hidden="true" />
        </button>
      ) : (
        <span data-tone={checked ? 'good' : 'danger'}>{checked ? 'Да' : 'Нет'}</span>
      )}
    </div>
  )
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="settings-field settings-select-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} title={label} aria-label={label}>
        {options.map((option) => (
          <option key={option} value={option} className="bg-[#0d1116]">{option}</option>
        ))}
      </select>
    </label>
  )
}

function SegmentedField({ label, value, options, onChange }: { label: string; value: string; options: Array<[string, string]>; onChange: (value: string) => void }) {
  return (
    <div className="settings-field settings-segment-field">
      <span>{label}</span>
      <div className="settings-tabs" role="group" aria-label={label}>
        {options.map(([optionValue, optionLabel]) => (
          <button key={optionValue} type="button" aria-pressed={value === optionValue} onClick={() => onChange(optionValue)}>
            {optionLabel}
          </button>
        ))}
      </div>
    </div>
  )
}

function StatBox({ label, value, hint, tone }: SettingsMetric) {
  return (
    <div className="settings-stat">
      <div>{label}</div>
      <strong data-tone={tone}>{value}</strong>
      {hint ? <small>{hint}</small> : null}
    </div>
  )
}
