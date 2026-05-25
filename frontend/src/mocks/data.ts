import type { DashboardData } from '@/entities/dashboard/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'
import type { UserSummary } from '@/entities/user/model/types'

export type KnownUserId = UserSummary['id'] | 'guest'
export type MachineScenarioName = 'ready' | 'warning' | 'blocked'
export type DashboardScenarioName = 'default' | 'no-workout' | 'high-fatigue' | 'machine-warning' | 'drive-error'

export const mockUsers: UserSummary[] = [
  {
    id: 'alexey',
    name: 'Алексей',
    readinessPercent: 78,
    lastWorkout: 'Вчера — грудь и трицепс',
    todayFocus: 'спина или лёгкая тренировка',
    weekProgress: '+4% к объёму',
    accent: 'gold',
  },
  {
    id: 'elena',
    name: 'Елена',
    readinessPercent: 84,
    lastWorkout: '12 мая — ноги',
    todayFocus: 'верх тела',
    weekProgress: '+3% к стабильности',
    accent: 'green',
  },
]

export const machineScenarios: Record<MachineScenarioName, MachineHealth> = {
  ready: {
    machineState: 'ready',
    machineLabel: 'Тренажёр готов',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: 'Калибровка: перед упражнением',
  },
  warning: {
    machineState: 'warning',
    machineLabel: 'Требуется внимание',
    leftDrive: 'connected',
    rightDrive: 'warning',
    safety: 'enabled',
    calibration: 'Калибровка: рекомендуется перед стартом',
  },
  blocked: {
    machineState: 'blocked',
    machineLabel: 'Тренажёр заблокирован',
    leftDrive: 'connected',
    rightDrive: 'error',
    safety: 'emergency_stop',
    calibration: 'Калибровка недоступна до сервисной проверки',
  },
}

export const mockMachineHealth = machineScenarios.ready

export const userSelectionScenarios = {
  ready: { users: mockUsers, machine: machineScenarios.ready },
  warning: { users: mockUsers, machine: machineScenarios.warning },
  blocked: { users: mockUsers, machine: machineScenarios.blocked },
} satisfies Record<MachineScenarioName, { users: UserSummary[]; machine: MachineHealth }>

const baseMuscles: MuscleCard[] = [
  { name: 'Грудь', status: 'high', score: 72 },
  { name: 'Трицепс', status: 'medium', score: 41 },
  { name: 'Плечи', status: 'medium', score: 36 },
  { name: 'Спина', status: 'ready', score: 9 },
  { name: 'Бицепс', status: 'light', score: 18 },
  { name: 'Предплечья', status: 'ready', score: 6 },
  { name: 'Пресс', status: 'light', score: 14 },
  { name: 'Ягодицы', status: 'ready', score: 7 },
  { name: 'Ноги', status: 'ready', score: 12 },
]

export const mockMuscles = baseMuscles

const baseWorkout = {
  title: 'Спина + бицепс',
  exercises: 5,
  sets: 18,
  duration: '45 минут',
  list: [
    {
      slug: 'machine-pulldown',
      name: 'Тяга сверху',
      previewVideoUrl: '/media/exercises/machine-pulldown/male-machine-pulldown-side.mp4',
      previous: {
        label: 'Прошлый раз',
        primary: '50 кг',
        secondary: '20 повторов',
        meta: '2 подхода • 3 дня назад',
      },
      planned: {
        label: 'План',
        primary: '55 кг',
        secondary: '20 повторов',
        meta: '4 подхода • +5 кг к прошлому',
      },
    },
    {
      slug: 'machine-seated-cable-row',
      name: 'Тяга к поясу',
      previewVideoUrl: '/media/exercises/machine-seated-cable-row/male-machine-seated-cable-row-side.mp4',
      previous: {
        label: 'Прошлый раз',
        primary: '42 кг',
        secondary: '24 повтора',
        meta: '3 подхода • 5 дней назад',
      },
      planned: {
        label: 'План',
        primary: '45 кг',
        secondary: '24 повтора',
        meta: '4 подхода • +3 кг к прошлому',
      },
    },
    {
      slug: 'barbell-curl',
      name: 'Сгибание рук',
      previewVideoUrl: '/media/exercises/barbell-curl/male-barbell-curl-side.mp4',
      previous: {
        label: 'Прошлый раз',
        primary: '20 кг',
        secondary: '36 повторов',
        meta: '3 подхода • 5 дней назад',
      },
      planned: {
        label: 'План',
        primary: '20 кг',
        secondary: '36 повторов',
        meta: '3 подхода • повторяем рабочую схему',
      },
    },
    {
      slug: 'underhand-pulldown',
      name: 'Тяга прямыми руками',
      previewVideoUrl: '/media/exercises/underhand-pulldown/male-underhand-pulldown-side.mp4',
      previous: {
        label: 'Прошлый раз',
        primary: '30 кг',
        secondary: '36 повторов',
        meta: '3 подхода • 7 дней назад',
      },
      planned: {
        label: 'План',
        primary: '35 кг',
        secondary: '48 повторов',
        meta: '4 подхода • +5 кг к прошлому',
      },
    },
    {
      slug: 'forearm-plank',
      name: 'Планка',
      previewVideoUrl: '/media/exercises/forearm-plank/male-forearm-plank-side.mp4',
      previous: {
        label: 'Прошлый раз',
        primary: '40 сек',
        secondary: 'вес тела',
        meta: '3 подхода • 4 дня назад',
      },
      planned: {
        label: 'План',
        primary: '45 сек',
        secondary: 'вес тела',
        meta: '3 подхода • +5 сек к прошлому',
      },
    },
  ],
}

const baseRecommendedExercises = [
  { name: 'Тяга сверху', muscles: 'Спина, бицепс', status: 'Рекомендуется' },
  { name: 'Тяга к поясу', muscles: 'Спина', status: 'Рекомендуется' },
  { name: 'Сгибание рук', muscles: 'Бицепс', status: 'Можно выполнить' },
]

const baseQuickStart = [
  { name: 'Жим лёжа', stats: '40 кг × 10 × 3', last: '2 дн. назад' },
  { name: 'Присед', stats: '60 кг × 10 × 3', last: '3 дн. назад' },
  { name: 'Тяга сверху', stats: '45 кг × 10 × 3', last: '5 дн. назад' },
]

const baseProgress = [
  { label: 'тренировок за месяц', value: '8' },
  { label: 'недели подряд', value: '3' },
  { label: 'к объёму за неделю', value: '+4%' },
  { label: 'кг за месяц', value: '-1.2' },
]

const dashboardProfiles: Record<KnownUserId, Pick<DashboardData, 'greeting' | 'recommendationTitle' | 'recommendationText' | 'readinessPercent'>> = {
  alexey: {
    greeting: 'Добрый день, Алексей',
    recommendationTitle: 'Сегодня лучше: Спина + бицепс',
    recommendationText:
      'Грудь и трицепс ещё восстанавливаются после прошлой тренировки. Ноги готовы к умеренной нагрузке.',
    readinessPercent: 78,
  },
  elena: {
    greeting: 'Добрый день, Елена',
    recommendationTitle: 'Сегодня лучше: Верх тела',
    recommendationText:
      'Ноги ещё утомлены после прошлой сессии. Верх тела готов к плановой нагрузке и контролю техники.',
    readinessPercent: 84,
  },
  guest: {
    greeting: 'Добро пожаловать',
    recommendationTitle: 'Сегодня лучше: Быстрый старт',
    recommendationText:
      'Гостевой режим не использует персональную историю. Можно выбрать упражнение из каталога и начать тренировку на моках.',
    readinessPercent: 68,
  },
}

function getProfile(userId: KnownUserId) {
  return dashboardProfiles[userId] ?? dashboardProfiles.alexey
}

export function buildDashboardScenario(
  userId: KnownUserId = 'alexey',
  scenario: DashboardScenarioName = 'default',
): DashboardData {
  const profile = getProfile(userId)

  const base: DashboardData = {
    ...profile,
    todayWorkout: baseWorkout,
    machine: machineScenarios.ready,
    alerts: [],
    recommendedExercises: baseRecommendedExercises,
    quickStart: baseQuickStart,
    progress: baseProgress,
    muscles: baseMuscles,
  }

  switch (scenario) {
    case 'no-workout':
      return {
        ...base,
        recommendationTitle: 'Сегодня лучше: Выбрать новый старт',
        recommendationText:
          'На сегодня не найдено сохранённой тренировки. Можно перейти в быстрый старт или открыть каталог упражнений.',
        todayWorkout: null,
        alerts: [
          {
            tone: 'warning',
            title: 'План на сегодня не найден',
            description: 'Сценарий моков показывает состояние без назначенной тренировки, но с доступным быстрым стартом.',
          },
        ],
      }
    case 'high-fatigue':
      return {
        ...base,
        readinessPercent: 34,
        recommendationTitle: 'Сегодня лучше: Восстановление',
        recommendationText:
          'Уровень усталости слишком высок для полноценной силовой тренировки. Рекомендуется облегчённая сессия или отдых.',
        alerts: [
          {
            tone: 'blocked',
            title: 'Высокая усталость мышц',
            description: 'Мок отображает сценарий, в котором старт силовой тренировки должен быть пересмотрен.',
          },
        ],
        muscles: [
          { name: 'Грудь', status: 'critical', score: 128 },
          { name: 'Трицепс', status: 'high', score: 94 },
          { name: 'Плечи', status: 'high', score: 88 },
          { name: 'Спина', status: 'medium', score: 41 },
          { name: 'Бицепс', status: 'medium', score: 39 },
          { name: 'Предплечья', status: 'light', score: 20 },
          { name: 'Пресс', status: 'light', score: 18 },
          { name: 'Ягодицы', status: 'medium', score: 36 },
          { name: 'Ноги', status: 'high', score: 91 },
        ],
      }
    case 'machine-warning':
      return {
        ...base,
        machine: machineScenarios.warning,
        alerts: [
          {
            tone: 'warning',
            title: 'Требуется внимание к приводу',
            description: 'Сценарий моков показывает предупреждение по правому приводу перед началом упражнения.',
          },
        ],
      }
    case 'drive-error':
      return {
        ...base,
        machine: machineScenarios.blocked,
        alerts: [
          {
            tone: 'blocked',
            title: 'Ошибка правого привода',
            description: 'Старт тренировки блокируется, пока не будет завершена сервисная проверка оборудования.',
          },
        ],
      }
    case 'default':
    default:
      return base
  }
}

export const dashboardStoryScenarios = {
  default: buildDashboardScenario('alexey', 'default'),
  'no-workout': buildDashboardScenario('alexey', 'no-workout'),
  'high-fatigue': buildDashboardScenario('alexey', 'high-fatigue'),
  'machine-warning': buildDashboardScenario('alexey', 'machine-warning'),
  'drive-error': buildDashboardScenario('alexey', 'drive-error'),
} satisfies Record<DashboardScenarioName, DashboardData>