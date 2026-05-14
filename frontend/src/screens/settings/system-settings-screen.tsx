import { CheckCircle2, Download, PlayCircle, RefreshCw, Shield, Wifi } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { SettingsTab, SystemSettingsData } from '@/entities/stage4/model/types'
import { useHardwareStore } from '@/stores/hardware-store'
import { buildSystemSettingsData, settingsTabs } from '@/mocks/stage4-data'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { MetricCardGrid, Panel, SectionTitle, Stage4DevPanel, TabStrip } from '@/shared/ui/stage4/screen-components'
import { useStage4Screen } from '@/features/stage4/lib/use-stage4-screen'
import { useStage4Store } from '@/stores/stage4-store'

function asSettingsTab(value: string | null): SettingsTab {
  if (value === 'overview' || value === 'safety' || value === 'mechanics' || value === 'diagnostics' || value === 'calibrations' || value === 'service' || value === 'journal' || value === 'common') {
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

export function SystemSettingsScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { selectedUserId, userName, emergencyStopActive, setEmergencyStopActive, dev, settingsDraft, patchDevFlags, resetDevFlags } = useStage4Screen()
  const setSettingsValue = useStage4Store((state) => state.setSettingsValue)
  const hydrateSettingsDraft = useStage4Store((state) => state.hydrateSettingsDraft)
  const saveSettingsDraft = useStage4Store((state) => state.saveSettingsDraft)
  const cancelSettingsDraft = useStage4Store((state) => state.cancelSettingsDraft)
  const resetSettingsToDefaults = useStage4Store((state) => state.resetSettingsToDefaults)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const liveSettings = useHardwareStore((state) => state.settings)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const loadSettings = useHardwareStore((state) => state.loadSettings)
  const updateSafetySettings = useHardwareStore((state) => state.updateSafetySettings)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const tab = asSettingsTab(searchParams.get('tab'))

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

  const data = liveSettings ?? fallbackData
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

  return (
    <FormaShell
      userName={userName}
      machine={snapshot?.machine ?? data.machine}
      onStop={() => {
        void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId })
        setEmergencyStopActive(true)
      }}
    >
      <SectionTitle title="Настройки, безопасность и диагностика" description="Управление тренажёром, безопасностью и обслуживанием." />

      {hardwareError ? <div className="rounded-[24px] border border-[#eb5345]/25 bg-[#1b0f10] px-5 py-4 text-sm text-[#ffb4a7]">{hardwareError}</div> : null}

      <TabStrip tabs={settingsTabs} active={tab} onChange={updateTab} />

      {tab === 'overview' ? (
        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6">
            <Panel title="Forma готова к тренировке" description="Все критические проверки пройдены. Можно выполнять упражнения.">
              <MetricCardGrid items={data.overviewCards} columns="xl:grid-cols-3" />
            </Panel>
            <div className="grid gap-6 xl:grid-cols-3">
              <Panel title="Последние события">
                <div className="space-y-3 text-sm text-white/72">
                  {data.overviewEvents.map((event) => (
                    <div key={`${event.time}-${event.title}`} className="flex items-center justify-between gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4">
                      <span>{event.time}</span>
                      <span className="flex-1">{event.title}</span>
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel title="Быстрые действия">
                <div className="space-y-3">
                  {['Запустить диагностику', 'Открыть журнал', 'Сервисный режим'].map((action) => (
                    <button key={action} type="button" className="flex w-full items-center justify-between rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-left text-sm text-white/75">{action}<span>›</span></button>
                  ))}
                </div>
              </Panel>
              <Panel title="Калибровки">
                <div className="space-y-3 text-sm text-white/72">
                  <div>Последняя: Сегодня, 08:32</div>
                  <div>Следующая: через 30 дней</div>
                  <div className="text-[#79de83]">Актуально</div>
                </div>
              </Panel>
            </div>
          </div>
          <div className="space-y-6">
            <Panel title="Безопасность">
              <InfoMetricList items={data.overviewCards.slice(0, 4)} />
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === 'safety' ? (
        <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
          <div className="space-y-6">
            <Panel title="Безопасность активна" description="Система безопасности включена и контролирует все параметры тренажёра.">
              {snapshot?.safety.state === 'emergency_stop' ? (
                <div className="mb-4 flex justify-end">
                  <Button variant="secondary" onClick={() => void handleClearEmergencyStop()}>Снять аварийную остановку</Button>
                </div>
              ) : null}
              <div className="grid gap-4 xl:grid-cols-2">
                <ToggleField label="Аварийная остановка готова" checked={data.safety.emergencyReady} editable={false} onChange={() => {}} />
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
          <Panel title="Сохранение настроек">
            <div className="space-y-3 text-sm text-white/68">
              <div>Сохраните изменения или восстановите значения по умолчанию.</div>
            </div>
            <div className="mt-5 flex flex-col gap-3">
              <Button iconLeft={<CheckCircle2 className="h-4 w-4" />} onClick={() => void handleSafetySave()}>Сохранить изменения</Button>
              <Button variant="secondary" onClick={cancelSettingsDraft}>Отменить</Button>
              <Button variant="secondary" onClick={resetSettingsToDefaults}>Сбросить по умолчанию</Button>
            </div>
          </Panel>
        </div>
      ) : null}

      {tab === 'mechanics' ? (
        <div className="space-y-6">
          <Panel title="Механика готова к работе" description="Приводы подключены, связь стабильна, запуск движения разрешён.">
            <div className="grid gap-6 xl:grid-cols-4">
              <MetricCardGrid items={data.mechanics.statusSummary} columns="xl:grid-cols-1" />
              <MetricCardGrid items={data.mechanics.leftDrive} columns="xl:grid-cols-1" />
              <MetricCardGrid items={data.mechanics.rightDrive} columns="xl:grid-cols-1" />
              <MetricCardGrid items={data.mechanics.sync} columns="xl:grid-cols-1" />
            </div>
          </Panel>
          <div className="grid gap-6 xl:grid-cols-3">
            <Panel title="Параметры движения"><InfoMetricList items={data.mechanics.motion} /></Panel>
            <Panel title="Параметры ШВП"><InfoMetricList items={data.mechanics.screw} /></Panel>
            <Panel title="Обслуживание"><InfoMetricList items={data.mechanics.service} /></Panel>
          </div>
        </div>
      ) : null}

      {tab === 'diagnostics' ? (
        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-6">
            <Panel title="Диагностика завершена успешно" description="Все системы работают в пределах нормы. Тренажёр готов к использованию.">
              <div className="grid gap-4 md:grid-cols-5">
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
          <Panel title="Последние результаты" action={<Button variant="ghost">Открыть журнал</Button>}>
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
              <Button variant="secondary">Открыть журнал</Button>
            </div>
          </Panel>
        </div>
      ) : null}

      {tab === 'calibrations' ? (
        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <Panel title="Сохранённые калибровки" description="Эти значения используются для контроля амплитуды, безопасности и прогресса.">
            <div className="overflow-hidden rounded-[24px] border border-white/8">
              <div className="grid grid-cols-[1.2fr_repeat(4,1fr)_160px] bg-white/4 px-4 py-3 text-sm text-white/45">
                <div>Упражнение</div>
                <div>Нижняя точка</div>
                <div>Верхняя точка</div>
                <div>Дата</div>
                <div>Статус</div>
                <div>Действия</div>
              </div>
              {data.calibrations.entries.map((entry) => (
                <div key={entry.id} className="grid grid-cols-[1.2fr_repeat(4,1fr)_160px] border-t border-white/8 px-4 py-4 text-sm text-white/74">
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
            <Button className="mt-5" variant="secondary">Новая калибровка</Button>
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
        <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
          <div className="space-y-6">
            <Panel title="Сервисный режим" description="Режим предназначен только для технического обслуживания и настройки тренажёра.">
              <div className="mb-6 flex flex-wrap gap-3">
                <Button onClick={() => void handleServiceModeToggle()}>{data.service.unlocked ? 'Выключить сервисный режим' : 'Включить сервисный режим'}</Button>
              </div>
              <div className="grid gap-6 xl:grid-cols-2">
                <Panel title="Текущие позиции"><InfoMetricList items={data.service.positions} /></Panel>
                <Panel title="Состояние приводов"><InfoMetricList items={data.service.driveHealth} /></Panel>
              </div>
              <div className="mt-6 grid gap-4 md:grid-cols-2">
                {data.service.actions.map((action) => (
                  <button key={action.title} type="button" onClick={() => void handleServiceAction(action.title)} className="rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-left text-sm text-white/75">
                    <div className="text-white">{action.title}</div>
                    <div className="mt-1 text-xs text-white/45">{action.description}</div>
                  </button>
                ))}
              </div>
            </Panel>
          </div>
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
                <div key={entry.id} className="grid grid-cols-[140px_140px_120px_1fr_1.2fr_120px] gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/74">
                  <span>{entry.date}</span>
                  <span>{entry.category}</span>
                  <span className={entry.level === 'critical' ? 'text-[#ff8f84]' : entry.level === 'warning' ? 'text-[#f2cf87]' : entry.level === 'success' ? 'text-[#79de83]' : 'text-white'}>{entry.level}</span>
                  <span className="text-white">{entry.title}</span>
                  <span>{entry.description}</span>
                  <Button variant="secondary" className="min-h-10 px-3 py-2">Подробнее</Button>
                </div>
              ))}
            </div>
          </Panel>
          <div className="space-y-6">
            <Panel title="Сводка за 30 дней"><MetricCardGrid items={data.journal.stats} columns="xl:grid-cols-1" /></Panel>
          </div>
        </div>
      ) : null}

      {tab === 'common' ? (
        <div className="grid gap-6 xl:grid-cols-[1fr_1fr_1fr]">
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
          <Panel title="Звук и подключения">
            <ToggleField label="Звук" checked={common.soundEnabled} editable onChange={(value) => setSettingsValue('soundEnabled', value)} />
            <ToggleField label="Голосовые подсказки" checked={common.voiceHintsEnabled} editable onChange={(value) => setSettingsValue('voiceHintsEnabled', value)} />
            <SelectField label="Громкость сигналов" value={common.signalVolume} options={['30%', '50%', '70%', '100%']} onChange={(value) => setSettingsValue('signalVolume', value)} />
            <SelectField label="Режим подключения" value={common.wifiMode} options={['Wi-Fi', 'Ethernet']} onChange={(value) => setSettingsValue('wifiMode', value)} />
            <div className="rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
              <div className="flex items-center gap-2 text-white"><Wifi className="h-4 w-4" />{data.common.ssid}</div>
              <div className="mt-2">{data.common.networkStatus} · {data.common.signalStrength}</div>
              <div className="mt-1 text-white/45">{data.common.ipAddress}</div>
            </div>
          </Panel>
          <div className="xl:col-span-3">
            <Panel title="Сохранение настроек">
              <div className="flex flex-wrap gap-3">
                <Button iconLeft={<CheckCircle2 className="h-4 w-4" />} onClick={saveSettingsDraft}>Сохранить изменения</Button>
                <Button variant="secondary" onClick={cancelSettingsDraft}>Отменить</Button>
                <Button variant="secondary" onClick={resetSettingsToDefaults}>Сбросить по умолчанию</Button>
              </div>
            </Panel>
          </div>
        </div>
      ) : null}

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
      <Stage4DevPanel value={dev} onChange={patchDevFlags} onReset={resetDevFlags} />
    </FormaShell>
  )
}

function InfoMetricList({ items }: { items: Array<{ label: string; value: string; tone?: 'neutral' | 'good' | 'warning' | 'danger' }> }) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label} className="flex items-center justify-between gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
          <span>{item.label}</span>
          <span className={item.tone === 'good' ? 'text-[#79de83]' : item.tone === 'warning' ? 'text-[#f2cf87]' : item.tone === 'danger' ? 'text-[#ff8f84]' : 'text-white'}>{item.value}</span>
        </div>
      ))}
    </div>
  )
}

function ToggleField({ label, checked, editable, onChange }: { label: string; checked: boolean; editable: boolean; onChange: (value: boolean) => void }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
      <div className="flex items-center gap-2"><Shield className="h-4 w-4 text-[#f2cf87]" />{label}</div>
      {editable ? (
        <button type="button" title={label} aria-label={label} onClick={() => onChange(!checked)} className={`inline-flex h-7 w-12 items-center rounded-full border px-1 transition ${checked ? 'justify-end border-[#d6b05f]/40 bg-[#20170b]' : 'justify-start border-white/10 bg-black/20'}`}>
          <span className={`h-5 w-5 rounded-full ${checked ? 'bg-[#f3d18b]' : 'bg-white/35'}`} />
        </button>
      ) : (
        <span className={checked ? 'text-[#79de83]' : 'text-[#ff8f84]'}>{checked ? 'Включена' : 'Выключена'}</span>
      )}
    </div>
  )
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="mb-3 grid grid-cols-[240px_1fr] items-center gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} title={label} aria-label={label} className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-white outline-none">
        {options.map((option) => (
          <option key={option} value={option} className="bg-[#0d1116]">{option}</option>
        ))}
      </select>
    </label>
  )
}

function SegmentedField({ label, value, options, onChange }: { label: string; value: string; options: Array<[string, string]>; onChange: (value: string) => void }) {
  return (
    <div className="mb-4 rounded-[20px] border border-white/8 bg-white/4 p-4">
      <div className="mb-3 text-sm text-white/45">{label}</div>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {options.map(([optionValue, optionLabel]) => (
          <button key={optionValue} type="button" onClick={() => onChange(optionValue)} className={`rounded-[16px] border px-4 py-3 text-sm transition ${value === optionValue ? 'border-[#d6b05f]/40 bg-[#20170b] text-[#f3d18b]' : 'border-white/8 bg-black/15 text-white/72'}`}>
            {optionLabel}
          </button>
        ))}
      </div>
    </div>
  )
}

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-white/8 bg-white/4 p-4">
      <div className="text-sm text-white/45">{label}</div>
      <div className="mt-2 font-display text-3xl font-bold text-white">{value}</div>
    </div>
  )
}