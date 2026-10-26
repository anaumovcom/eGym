import type { NetworkSnapshot } from '../live/coach-network-client'

/** Plain-language labels shared by the coach panel's overview and its technical details. */
export const reasons: Readonly<Record<string, string>> = {
  ready: 'Локальный тест готов', disabled: 'Выключен', audio_locked: 'Звук заблокирован браузером',
  safety: 'Блокировка безопасности', hardware_active: 'Тренажёр активен', runtime_session: 'Идёт тренировка',
  mute: 'Звук выключен', hidden: 'Вкладка скрыта', no_user: 'Пользователь не выбран',
  preferences_loading: 'Ожидание сохранённых настроек', preferences_unavailable: 'Настройки недоступны',
  no_consent: 'Нет согласия', unavailable: 'Аудиоконтекст недоступен', decode_failed: 'Ошибка декодирования',
  cancelled: 'Тест остановлен', scope_changed: 'Контекст изменён', missing_clip: 'Фраза не подготовлена',
  admitted: 'Фраза принята', idle: 'Ожидание', stale_source: 'Данные тренажёра устарели', mock_source: 'Не реальный источник',
  owner_mismatch: 'Владелец или контекст тренировки не совпадает', expired: 'Опоздало', no_source: 'Нет источника',
  requiresService: 'Сервисный режим или аварийная остановка: обычная речь заблокирована',
  pipeline_busy: 'Тренер уже говорит', provider_unavailable: 'Провайдер недоступен', stale_run: 'Настройки изменились, переподключение',
  local_mode: 'Сервер в локальном режиме', coach_disabled: 'Тренер выключен на сервере (COACH_ENABLED)', run_not_found: 'Ledger не найден', budget: 'Лимит бюджета', degraded: 'Только локальные клипы',
  no_useful_content: 'Нечего сказать', validation_failed: 'Текст отклонён проверкой', closed: 'Соединение закрыто', network: 'Сеть недоступна',
  'paused-set': 'Подход поставлен на паузу', plan_changed: 'План или настройки упражнения изменились',
  playback_failed: 'Воспроизведение отменено', watchdog: 'Поток аудио перестал поступать',
  rate_limited: 'Превышена частота сообщений', credential_unavailable: 'Доступ провайдера недоступен', voice_unavailable: 'Live-голос недоступен', voice_fallback: 'Нет ключа Fish Audio — говорит голос OpenAI',
  active_runs_full: 'Заняты все подключения тренера; повторяем попытку', run_create_failed: 'Не удалось создать сессию тренера',
}
export const reasonLabel = (reason: string) => reasons[reason] ?? reason

export const networkStates: Readonly<Record<NetworkSnapshot['state'], string>> = {
  off: 'Выключена', creating: 'Создание сессии', connecting: 'Подключение', ready: 'Подключена', retrying: 'Переподключение', refused: 'Отклонена сервером',
}

/** What the machine reported that keeps the coach silent (interpreter latch keys), in words a trainee understands. */
export const latchLabels: Readonly<Record<string, string>> = {
  emergency: 'аварийная остановка', machineEmergency: 'аварийная остановка тренажёра', blocked: 'тренажёр заблокирован',
  requiresService: 'тренажёру нужен сервис', panelStop: 'нажата кнопка «Стоп» на панели', spotter: 'сработала страховка',
  failure: 'тренажёр зафиксировал отказ в подходе', controlSafety: 'управление в защитном режиме',
  motionSafety: 'привод в защитном режиме', faultCode: 'ошибка тренажёра',
}
export const latchLabel = (key: string) => latchLabels[key] ?? key
