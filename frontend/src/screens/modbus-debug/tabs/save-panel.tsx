import { Save } from 'lucide-react'
import { useState } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

export function SavePanel() {
  const {
    paramStates,
    connectionStatus,
    profiles,
    lastCompare,
    runCommand,
    saveProfile,
    loadProfiles,
    compareProfile,
  } = useModbusStore()

  const [profileName, setProfileName] = useState('')
  const [profileComment, setProfileComment] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<string | null>(null)
  const [selectedProfileId, setSelectedProfileId] = useState<string>('')
  const [confirmSaveToDriver, setConfirmSaveToDriver] = useState(false)

  const isConnected = connectionStatus?.connected ?? false

  const unsaved = [...paramStates.values()].filter((s) => s.writtenButUnsaved)
  const needsReboot = unsaved.filter((s) => {
    const p = s.address
    // Parameters that require reboot: PA_000, PA_002, PA_00D
    return [0x000, 0x002, 0x00D].includes(p)
  })

  const handleSaveToEeprom = async () => {
    setConfirmSaveToDriver(false)
    setBusy('save')
    try {
      const r = await runCommand('save_parameters', true)
      setLastResult(r.success ? 'Параметры сохранены в EEPROM (PA_1A7 = 0x0801)' : `Ошибка: ${r.error}`)
    } finally {
      setBusy(null)
    }
  }

  const handleSaveProfile = async () => {
    if (!profileName.trim()) return
    setBusy('profile')
    try {
      await saveProfile(profileName, profileComment)
      setLastResult(`Профиль «${profileName}» сохранён`)
      setProfileName('')
      setProfileComment('')
    } finally {
      setBusy(null)
    }
  }

  const handleLoadProfiles = async () => {
    setBusy('load')
    try {
      await loadProfiles()
    } finally {
      setBusy(null)
    }
  }

  const handleCompare = async () => {
    if (!selectedProfileId) return
    setBusy('compare')
    try {
      await compareProfile(selectedProfileId)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      {/* EEPROM save */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <h3 className="font-semibold text-[#f4dfb4]">Сохранение в память драйвера</h3>

        {unsaved.length > 0 ? (
          <div className="rounded-xl bg-[#2d2500] border border-[#f2cf87]/30 p-3 space-y-2">
            <p className="text-sm text-[#f2cf87]">{unsaved.length} параметров записано, но не сохранено в EEPROM.</p>
            {needsReboot.length > 0 && (
              <p className="text-xs text-[#ff8f84]">⚠ {needsReboot.length} параметров требуют перезапуска питания.</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-white/40">Нет несохранённых изменений в параметрах.</p>
        )}

        <div className="flex flex-col gap-2">
          <Button
            variant="primary"
            iconLeft={<Save size={15} />}
            onClick={() => setConfirmSaveToDriver(true)}
            disabled={!isConnected || busy !== null}
          >
            Сохранить все параметры в драйвер
          </Button>
          <p className="text-xs text-white/30">Выполняет PA_1A7 = 0x0801. Данные записываются в EEPROM.</p>
        </div>

        {lastResult && (
          <p className="text-xs text-white/50 mt-2">{lastResult}</p>
        )}
      </div>

      {/* Save profile */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <h3 className="font-semibold text-[#f4dfb4]">Профили настроек</h3>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="space-y-1">
            <span className="text-xs text-white/50">Название профиля</span>
            <input
              type="text"
              className="input-field w-full"
              placeholder="Например: A6 Position 38400"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs text-white/50">Комментарий</span>
            <input
              type="text"
              className="input-field w-full"
              placeholder="Необязательно"
              value={profileComment}
              onChange={(e) => setProfileComment(e.target.value)}
            />
          </label>
        </div>

        <Button
          variant="secondary"
          onClick={handleSaveProfile}
          disabled={!profileName.trim() || busy === 'profile'}
          className="text-sm"
        >
          {busy === 'profile' ? 'Сохраняю...' : 'Сохранить профиль'}
        </Button>
      </div>

      {/* Profile list & compare */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-[#f4dfb4]">Сохранённые профили</h3>
          <Button variant="ghost" className="text-xs" onClick={handleLoadProfiles} disabled={busy === 'load'}>
            Обновить список
          </Button>
        </div>

        {profiles.length === 0 ? (
          <p className="text-sm text-white/40">Нет сохранённых профилей.</p>
        ) : (
          <div className="space-y-2">
            {profiles.map((p) => (
              <div
                key={p.id}
                className={cn(
                  'flex items-center justify-between rounded-xl px-4 py-3 cursor-pointer transition',
                  selectedProfileId === p.id ? 'bg-[#b5852f]/20 border border-[#b5852f]/40' : 'bg-white/4 hover:bg-white/6',
                )}
                onClick={() => setSelectedProfileId(p.id ?? '')}
              >
                <div>
                  <p className="text-sm font-semibold text-white">{p.name}</p>
                  <p className="text-xs text-white/40">{p.parameters.length} параметров · {p.comment}</p>
                  {p.createdAt && <p className="text-[11px] text-white/25">{new Date(p.createdAt).toLocaleString()}</p>}
                </div>
                <span className="text-xs text-white/30">{p.driverModel}</span>
              </div>
            ))}
          </div>
        )}

        {selectedProfileId && (
          <Button
            variant="secondary"
            className="text-sm"
            onClick={handleCompare}
            disabled={busy === 'compare'}
          >
            {busy === 'compare' ? 'Сравниваю...' : 'Сравнить с драйвером'}
          </Button>
        )}

        {lastCompare && (
          <div className="rounded-xl bg-white/4 p-4 space-y-2">
            <p className="text-sm">
              <span className="text-[#79de83]">{lastCompare.matching} совпадают</span>
              {lastCompare.differing > 0 && <span className="text-[#f2cf87] ml-3">{lastCompare.differing} отличаются</span>}
            </p>
            {lastCompare.differences.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-white/30 uppercase">
                      <th className="py-1 text-left">Адрес</th>
                      <th className="py-1 text-right">В драйвере</th>
                      <th className="py-1 text-right">В профиле</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lastCompare.differences.map((d) => (
                      <tr key={d.address} className="border-t border-white/6">
                        <td className="py-1 font-mono text-[#f2cf87]">{d.addressHex}</td>
                        <td className="py-1 text-right font-mono text-white">{d.driverValue}</td>
                        <td className="py-1 text-right font-mono text-white/50">{d.profileValue}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Confirm EEPROM save */}
      {confirmSaveToDriver && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-panel rounded-2xl p-6 max-w-md w-full mx-4 space-y-4">
            <h3 className="font-bold text-white">Сохранить параметры в EEPROM?</h3>
            <p className="text-sm text-white/60">Все текущие параметры будут записаны в энергонезависимую память драйвера (PA_1A7 = 0x0801). Убедитесь, что значения параметров верны.</p>
            <div className="flex gap-3 justify-end">
              <Button variant="ghost" onClick={() => setConfirmSaveToDriver(false)}>Отмена</Button>
              <Button variant="primary" iconLeft={<Save size={14} />} onClick={handleSaveToEeprom}>Сохранить</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
