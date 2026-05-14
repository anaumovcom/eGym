import type { MachineHealth } from '@/entities/machine/model/types'
import type { StatusTone } from '@/shared/ui/status/status-types'

export function getMachineTone(machineState: MachineHealth['machineState']): StatusTone {
  switch (machineState) {
    case 'ready':
      return 'success'
    case 'warning':
      return 'warning'
    case 'blocked':
      return 'danger'
  }
}

export function getDriveTone(status: MachineHealth['leftDrive']): StatusTone {
  switch (status) {
    case 'connected':
      return 'success'
    case 'warning':
      return 'warning'
    case 'error':
      return 'danger'
  }
}

export function getSafetyTone(status: MachineHealth['safety']): StatusTone {
  switch (status) {
    case 'enabled':
      return 'success'
    case 'disabled':
      return 'warning'
    case 'emergency_stop':
      return 'danger'
  }
}

export function getDriveLabel(side: 'left' | 'right', status: MachineHealth['leftDrive']) {
  const sideLabel = side === 'left' ? 'Левый привод' : 'Правый привод'

  switch (status) {
    case 'connected':
      return `${sideLabel}: подключён`
    case 'warning':
      return `${sideLabel}: требует проверки`
    case 'error':
      return `${sideLabel}: ошибка`
  }
}

export function getSafetyLabel(status: MachineHealth['safety']) {
  switch (status) {
    case 'enabled':
      return 'Система безопасности: включена'
    case 'disabled':
      return 'Система безопасности: выключена'
    case 'emergency_stop':
      return 'Аварийная остановка: активна'
  }
}

export function getMachineHeadlineClass(machineState: MachineHealth['machineState']) {
  switch (machineState) {
    case 'ready':
      return 'text-[#8fe58c]'
    case 'warning':
      return 'text-[#f0d08c]'
    case 'blocked':
      return 'text-[#ff9589]'
  }
}

export function getMachineNotice(machine: MachineHealth) {
  if (
    machine.machineState === 'blocked' ||
    machine.leftDrive === 'error' ||
    machine.rightDrive === 'error' ||
    machine.safety === 'emergency_stop'
  ) {
    return {
      tone: 'blocked' as const,
      title: 'Тренажёр временно заблокирован',
      description:
        'Запуск тренировок недоступен до восстановления приводов и подтверждения статуса безопасности.',
    }
  }

  if (
    machine.machineState === 'warning' ||
    machine.leftDrive === 'warning' ||
    machine.rightDrive === 'warning' ||
    machine.safety === 'disabled'
  ) {
    return {
      tone: 'warning' as const,
      title: 'Требуется проверка системы',
      description:
        'Можно просмотреть экран, но перед стартом тренировки потребуется подтвердить готовность и безопасность.',
    }
  }

  return null
}