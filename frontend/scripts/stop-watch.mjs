import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

const rootDir = path.resolve(import.meta.dirname, '..')
const runtimeDir = path.join(rootDir, '.runtime')
const pidFile = path.join(runtimeDir, 'vite-watch.pid')

function isProcessRunning(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

if (!fs.existsSync(pidFile)) {
  console.log('Watch mode не запущен: PID-файл не найден.')
  process.exit(0)
}

const rawValue = fs.readFileSync(pidFile, 'utf8').trim()
const pid = Number(rawValue)

if (!Number.isInteger(pid) || pid <= 0) {
  fs.rmSync(pidFile, { force: true })
  console.log('PID-файл был некорректным и удалён.')
  process.exit(0)
}

if (!isProcessRunning(pid)) {
  fs.rmSync(pidFile, { force: true })
  console.log(`Процесс ${pid} уже остановлен.`)
  process.exit(0)
}

if (process.platform === 'win32') {
  execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' })
} else {
  process.kill(-pid, 'SIGTERM')
}

fs.rmSync(pidFile, { force: true })
console.log(`Watch mode остановлен. PID: ${pid}`)