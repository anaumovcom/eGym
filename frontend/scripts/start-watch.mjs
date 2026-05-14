import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'

const rootDir = path.resolve(import.meta.dirname, '..')
const runtimeDir = path.join(rootDir, '.runtime')
const pidFile = path.join(runtimeDir, 'vite-watch.pid')
const logFile = path.join(runtimeDir, 'vite-watch.log')

function ensureRuntimeDir() {
  fs.mkdirSync(runtimeDir, { recursive: true })
}

function isProcessRunning(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function readExistingPid() {
  if (!fs.existsSync(pidFile)) {
    return null
  }

  const rawValue = fs.readFileSync(pidFile, 'utf8').trim()
  const pid = Number(rawValue)

  if (!Number.isInteger(pid) || pid <= 0) {
    fs.rmSync(pidFile, { force: true })
    return null
  }

  if (!isProcessRunning(pid)) {
    fs.rmSync(pidFile, { force: true })
    return null
  }

  return pid
}

ensureRuntimeDir()

const existingPid = readExistingPid()

if (existingPid) {
  console.log(`Watch mode уже запущен. PID: ${existingPid}`)
  console.log(`Логи: ${logFile}`)
  process.exit(0)
}

const logStream = fs.openSync(logFile, 'a')
const viteBin = path.join(rootDir, 'node_modules', 'vite', 'bin', 'vite.js')
const child = spawn(process.execPath, [viteBin, '--host', '127.0.0.1', '--strictPort'], {
  cwd: rootDir,
  detached: true,
  stdio: ['ignore', logStream, logStream],
  windowsHide: true,
})

child.unref()
fs.writeFileSync(pidFile, String(child.pid))

console.log(`Watch mode запущен. PID: ${child.pid}`)
console.log('URL: http://127.0.0.1:5173')
console.log(`PID-файл: ${pidFile}`)
console.log(`Логи: ${logFile}`)