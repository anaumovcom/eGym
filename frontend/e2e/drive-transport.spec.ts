import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { expectPrimaryNavigation, test } from './fixtures/navigation'

test('switches CANopen and Modbus from the kiosk and keeps the saved configuration', async ({ page }, info) => {
  let config = { adapter: 'modbus', canopen: { driver: 'usbcanfd', device: 0, channel: 0, interface: 'can0',
    bitrate: 500000, cycle_ms: 20, left_id: 1, right_id: 2, velocity_unit: 'rpm' } }
  let blocked = false
  let connected = false
  await page.addInitScript(() => localStorage.setItem('egym-app-store', JSON.stringify({ state: { selectedUserId: 'alexey' }, version: 0 })))
  await page.route('**/api/hardware/drive-transport', route => {
    if (route.request().method() === 'PUT') {
      if (blocked) return route.fulfill({ status: 409, json: { detail: 'Идёт упражнение' } })
      config = route.request().postDataJSON()
    }
    const nodes = connected && config.adapter === 'canopen' ? [config.canopen.left_id, config.canopen.right_id].map(node =>
      ({ node, mode: 10, statusword: 0x27, position: 17000 * node, velocity: 0, torque: 100 })) : []
    const timing = nodes.length ? { intervals: 200, mean_hz: 198.6, p99_ms: 5.42 } : null
    return route.fulfill({ json: { config, connected, error: null, nodes, timing } })
  })
  await page.goto('/settings/drives')
  await expectPrimaryNavigation(page)
  const mode = page.getByLabel('Режим приводов')
  const save = page.getByRole('button', { name: 'Применить режим' })
  await expect(mode).toHaveValue('modbus')
  await mode.selectOption('canopen')
  await expect(page.getByLabel('Назначение подключения')).toHaveValue('diagnostics')
  await page.getByLabel('Назначение подключения').selectOption('control')
  const period = page.getByLabel('Период обмена')
  await expect(period).toHaveValue('20')
  await period.selectOption('10')
  await expect(period.locator('option:checked')).toHaveText('10 мс · 100 Гц')
  await period.selectOption('5')
  await page.getByLabel('Правый привод · Node ID').fill('1')
  await expect(save).toBeDisabled()
  await page.getByLabel('Правый привод · Node ID').fill('8')
  await page.getByLabel('Канал адаптера').selectOption('1')
  await save.click()
  await expect(page.getByText('CANopen · ожидание')).toBeVisible()
  await page.reload()
  await expect(mode).toHaveValue('canopen')
  await expect(period).toHaveValue('5')
  await expect(page.getByLabel('Правый привод · Node ID')).toHaveValue('8')
  await expect(page.getByLabel('Канал адаптера')).toHaveValue('1')
  await expect(save).toBeInViewport()
  expect(await page.evaluate(() => [innerWidth, innerHeight, devicePixelRatio])).toEqual([2560, 1440, 1.5])
  connected = true
  await expect(page.getByRole('heading', { name: 'Правый привод · ID 8' })).toBeInViewport()
  await expect(page.getByText('0x0027')).toHaveCount(2)
  await expect(page.getByText('198,6 Гц')).toBeInViewport()
  await expect(page.getByText('5,42 мс')).toBeVisible()
  await page.screenshot({ path: info.outputPath('drive-transport-4k.png'), scale: 'device' })
  await mode.selectOption('modbus')
  blocked = true
  await save.click()
  await expect(page.getByRole('alert')).toHaveText('Идёт упражнение')
  await expect(page.getByText('CANopen · на связи')).toBeVisible()
  blocked = false
  connected = false
  await save.click()
  await expect(page.getByText('Modbus RTU · ожидание')).toBeVisible()
})

test('commissions two A6 independently, inspects the dictionary and saves the current CAN report', async ({ page, navigationApi }, info) => {
  let config = { adapter: 'twin', canopen: { operation: 'control', driver: 'usbcanfd', device: 0, channel: 0, interface: 'can0',
    bitrate: 500000, cycle_ms: 20, left_id: 1, right_id: 2, velocity_unit: 'rpm' } }
  let powerLeft = false
  let adapterOpen = false
  let lastFrame = '4B 41 60 00 08 00 00 00'
  const writes: string[] = []
  await page.addInitScript(() => localStorage.setItem('egym-app-store', JSON.stringify({ state: { selectedUserId: 'alexey' }, version: 0 })))
  await page.route('**/api/hardware/drive-transport', route => {
    if (route.request().method() === 'PUT') {
      config = route.request().postDataJSON()
      writes.push(config.canopen.operation)
    }
    const axes = [1, 2].map(node => {
      const online = adapterOpen && (node === 2 || powerLeft)
      const controlling = config.canopen.operation === 'control'
      const value = (v: number) => ({ value: v, abort: null, age_ms: 35 })
      return { node, responding: adapterOpen ? online : null, last_seen_ms: online ? 35 : null, issue: adapterOpen && !online ? 'ID 1 не отвечает на 6041:00' : null,
        heartbeat_state: online ? 127 : null, heartbeat_age_ms: online ? 105 : null, bootups: online ? 1 : 0,
        emcy: node === 2 && online ? 0x2310 : null, emcy_register: 2, emcy_age_ms: online ? 100 : null,
        sent_controlword: controlling && online ? 15 : null, sent_target: controlling && online ? -90 : null, tpdo_latency_ms: controlling ? 1.3 : null,
        objects: online ? { '6041:00': value(controlling ? 0x27 : node === 2 ? 8 : 64), '6061:00': value(4),
          '6064:00': value(-321), '606C:00': value(-32), '6077:00': value(-100), '1018:02': value(0x12345678),
          '1018:04': { value: null, abort: 0x06020000, age_ms: 35 }, '1600:01': value(0x60400010) } : {} }
    })
    const diagnostics = { stage: adapterOpen ? 'Диагностика · чтение SDO' : 'Открытие адаптера', adapter_open: adapterOpen,
      adapter: adapterOpen ? { model: 'USB-CAN-FD-B', serial: 'DEMO01234', firmware: 0x120, channels: 2 } : null,
      tx: 30, rx: 22, sdo_timeouts: 2, sdo_aborts: 1, axes, frames: adapterOpen ? [
        { seq: 51, elapsed_ms: 100, direction: 'TX', identifier: 0x602, data: '40 41 60 00 00 00 00 00' },
        { seq: 52, elapsed_ms: 100.4, direction: 'RX', identifier: 0x582, data: lastFrame },
      ] : [] }
    const active = config.adapter === 'canopen' && config.canopen.operation === 'control'
    if (active) diagnostics.stage = 'Циклический обмен PDO'
    return route.fulfill({ json: { config, connected: config.adapter === 'twin' || active, error: null, nodes: [],
      timing: active ? { intervals: 200, mean_hz: 199.76, p99_ms: 5.12, p99_feedback_ms: 1.56 } : null,
      diagnostics: config.adapter === 'canopen' ? diagnostics : null } })
  })
  await page.goto('/settings/drives')
  await expectPrimaryNavigation(page)
  await page.getByLabel('Режим приводов').selectOption('canopen')
  await expect(page.getByLabel('Назначение подключения')).toHaveValue('diagnostics')
  await page.getByLabel('Скорость шины').selectOption('250000')
  await page.getByLabel('Назначение подключения').selectOption('control')
  await expect(page.getByRole('button', { name: 'Применить режим' })).toBeDisabled()
  await page.getByLabel('Назначение подключения').selectOption('diagnostics')
  await page.getByRole('button', { name: 'Применить режим' }).click()
  await expect(page.getByText('Канал закрыт', { exact: true }).first()).toBeVisible()
  adapterOpen = true
  navigationApi.snapshot.machine = { ...navigationApi.snapshot.machine, machineState: 'warning', machineLabel: 'Диагностика CANopen', leftDrive: 'warning', rightDrive: 'error' }
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Подключение приводов' })).toBeInViewport({ ratio: 1 })
  await expect(page.getByText('1 из 2')).toBeVisible()
  await expect(page.getByText('ID 1 не отвечает на 6041:00')).toBeInViewport()
  await expect(page.getByText('0x0008 · Авария')).toBeInViewport()
  await expect(page.getByText(/0x2310 \/ 0x02/)).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Применить режим' })).toBeInViewport({ ratio: 1 })
  expect(await page.evaluate(() => [innerWidth, innerHeight, devicePixelRatio, document.documentElement.scrollWidth])).toEqual([2560, 1440, 1.5, 2560])
  await page.screenshot({ path: info.outputPath('canopen-first-connection-4k.png'), scale: 'device' })
  await page.getByRole('button', { name: 'Словарь A6' }).click()
  await expect(page.getByText('0x12345678')).toBeInViewport()
  await expect(page.getByText('SDO abort 0x06020000')).toBeVisible()
  await page.getByLabel('Группа объектов').selectOption('Карты PDO')
  await expect(page.getByText('0x6040:00 · 16 бит')).toBeInViewport()
  await page.getByRole('button', { name: 'Кадры CAN' }).click()
  await expect(page.getByText(lastFrame)).toBeInViewport()
  await page.getByRole('button', { name: 'Пауза просмотра' }).click()
  lastFrame = '4B 41 60 00 40 00 00 00'
  powerLeft = true
  await expect(page.getByText('2 из 2')).toBeVisible()
  await expect(page.getByText(lastFrame)).toHaveCount(0)
  await page.getByRole('button', { name: 'Продолжить просмотр' }).click()
  await expect(page.getByText(lastFrame)).toBeVisible()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Сохранить отчёт JSON' }).click()
  const file = await downloaded
  const report = JSON.parse(await readFile((await file.path())!, 'utf8'))
  expect(report.diagnostics.axes.map((a: { responding: boolean }) => a.responding)).toEqual([true, true])
  expect(report.diagnostics.frames.at(-1).data).toBe(lastFrame)
  await page.reload()
  await expect(page.getByLabel('Назначение подключения')).toHaveValue('diagnostics')
  expect(writes).toEqual(['diagnostics'])
  await page.getByText('Режим момента и подключение A6').click()
  await page.getByLabel('Режим момента CiA 402').selectOption('profile_torque')
  await page.getByText('Режим момента и подключение A6').click()
  await page.getByLabel('Скорость шины').selectOption('500000')
  await page.getByLabel('Назначение подключения').selectOption('control')
  await page.getByLabel('Период обмена').selectOption('5')
  await page.getByRole('button', { name: 'Применить режим' }).click()
  await expect(page.getByText('199,76 Гц')).toBeVisible()
  await expect(page.getByText('1,56 мс')).toBeVisible()
  await expect(page.getByText('0x000F / -90')).toHaveCount(2)
  await expect(page.getByLabel('Режим приводов')).toHaveCount(1)
  await page.getByText('Режим момента и подключение A6').click()
  await expect(page.getByLabel('Режим момента CiA 402')).toHaveValue('profile_torque')
})
