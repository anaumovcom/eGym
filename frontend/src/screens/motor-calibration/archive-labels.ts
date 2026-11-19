export const archiveSources = { modbus: 'Тренажёр · Modbus', canopen: 'Тренажёр · CANopen', twin: 'Цифровой двойник', unknown: 'Архив без источника' }
const statuses: Record<string, string> = { saved: 'сохранён', done: 'завершён', discarded: 'отклонён', failed: 'завершён с ошибкой', aborted: 'прерван' }
const date = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })

export function archiveLabel(r: { startedAt: string; code: string; status: string }) {
  return date.format(new Date(r.startedAt)) + ' · ' + r.code + ' · ' + (statuses[r.status] ?? r.status)
}
