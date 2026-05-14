param(
  [switch]$Bootstrap
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$utf8Encoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8Encoding
[Console]::OutputEncoding = $utf8Encoding
$OutputEncoding = $utf8Encoding

$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
$frontendRoot = Join-Path $projectRoot 'frontend'
$backendRoot = Join-Path $projectRoot 'backend'

$frontendPidFile = Join-Path $runtimeDir 'frontend-watch.pid'
$backendPidFile = Join-Path $runtimeDir 'backend-watch.pid'
$frontendLogFile = Join-Path $runtimeDir 'frontend-watch.log'
$backendLogFile = Join-Path $runtimeDir 'backend-watch.log'

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

function Write-InfoLine {
  param([string]$Message)

  Write-Host $Message -ForegroundColor Cyan
}

function Write-SuccessLine {
  param([string]$Message)

  Write-Host $Message -ForegroundColor Green
}

function Write-PathLine {
  param(
    [string]$Label,
    [string]$Value
  )

  Write-Host $Label -NoNewline -ForegroundColor DarkGray
  Write-Host $Value -ForegroundColor White
}

function Write-WarnLine {
  param([string]$Message)

  Write-Host $Message -ForegroundColor Yellow
}

function Write-UrlLine {
  param(
    [string]$Label,
    [string]$Value
  )

  Write-Host $Label -NoNewline -ForegroundColor DarkGray
  Write-Host $Value -ForegroundColor Magenta
}

function Test-ProcessRunning {
  param([int]$ProcessId)

  return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-PidFromFile {
  param([string]$PidFile)

  if (-not (Test-Path $PidFile)) {
    return $null
  }

  $rawPid = (Get-Content -Path $PidFile -Raw).Trim()
  $parsedPid = 0
  if (-not [int]::TryParse($rawPid, [ref]$parsedPid)) {
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    return $null
  }

  if (-not (Test-ProcessRunning -ProcessId $parsedPid)) {
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    return $null
  }

  return $parsedPid
}

function Show-StartSummary {
  $backendPid = Get-PidFromFile -PidFile $backendPidFile
  $frontendPid = Get-PidFromFile -PidFile $frontendPidFile

  if ($backendPid) {
    Write-SuccessLine "Backend watch запущен. PID: $backendPid"
    Write-PathLine 'Лог: ' $backendLogFile
    Write-PathLine 'Ошибки: ' "$backendLogFile.err"
  }

  if ($frontendPid) {
    Write-SuccessLine "Frontend watch запущен. PID: $frontendPid"
    Write-PathLine 'Лог: ' $frontendLogFile
    Write-PathLine 'Ошибки: ' "$frontendLogFile.err"
  }

  if (-not $backendPid -or -not $frontendPid) {
    Write-WarnLine 'Не удалось подтвердить запуск обоих процессов по PID-файлам. Проверьте логи в .runtime.'
  }

  Write-Host ''
  Write-UrlLine 'Backend URL:  ' 'http://127.0.0.1:8000'
  Write-UrlLine 'Frontend URL: ' 'http://127.0.0.1:5173'
}

function Start-WatchProcess {
  param(
    [string]$Name,
    [string]$PidFile,
    [string]$LogFile,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory
  )

  $existingPid = Get-PidFromFile -PidFile $PidFile
  if ($existingPid) {
    Write-InfoLine "$Name уже запущен. PID: $existingPid"
    Write-PathLine 'Лог: ' $LogFile
    return
  }

  if (Test-Path $LogFile) {
    Remove-Item -Path $LogFile -Force -ErrorAction SilentlyContinue
  }

  $errorLogFile = "$LogFile.err"
  if (Test-Path $errorLogFile) {
    Remove-Item -Path $errorLogFile -Force -ErrorAction SilentlyContinue
  }

  $startProcessArgs = @{
    FilePath = $FilePath
    ArgumentList = $ArgumentList
    WorkingDirectory = $WorkingDirectory
    RedirectStandardOutput = $LogFile
    RedirectStandardError = $errorLogFile
    WindowStyle = 'Hidden'
    PassThru = $true
  }

  $process = Start-Process @startProcessArgs

  Set-Content -Path $PidFile -Value $process.Id

  Write-SuccessLine "$Name запущен. PID: $($process.Id)"
  Write-PathLine 'Лог: ' $LogFile
  Write-PathLine 'Ошибки: ' $errorLogFile
}

if (-not $Bootstrap) {
  $existingBackendPid = Get-PidFromFile -PidFile $backendPidFile
  $existingFrontendPid = Get-PidFromFile -PidFile $frontendPidFile

  if ($existingBackendPid -or $existingFrontendPid) {
    Show-StartSummary
    return
  }

  $powershellExe = Join-Path $PSHOME 'powershell.exe'
  $bootstrapArgs = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $PSCommandPath,
    '-Bootstrap'
  )

  Start-Process -FilePath $powershellExe -ArgumentList $bootstrapArgs -WindowStyle Hidden | Out-Null

  for ($attempt = 0; $attempt -lt 50; $attempt++) {
    $backendPid = Get-PidFromFile -PidFile $backendPidFile
    $frontendPid = Get-PidFromFile -PidFile $frontendPidFile
    if ($backendPid -and $frontendPid) {
      break
    }

    Start-Sleep -Milliseconds 100
  }

  Show-StartSummary
  return
}

$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
  throw "Не найден Python окружения: $pythonExe"
}

$nodeCommand = Get-Command node -ErrorAction Stop
$nodeExe = $nodeCommand.Source
$viteBin = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
if (-not (Test-Path $viteBin)) {
  throw "Не найден Vite: $viteBin"
}

$frontendCommand = @(
  '/d',
  '/c',
  "set VITE_API_BASE_URL=http://127.0.0.1:8000&&`"$nodeExe`" `"$viteBin`" --host 127.0.0.1 --port 5173 --strictPort"
)

Start-WatchProcess -Name 'Backend watch' -PidFile $backendPidFile -LogFile $backendLogFile -FilePath $pythonExe -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $backendRoot

Start-WatchProcess -Name 'Frontend watch' -PidFile $frontendPidFile -LogFile $frontendLogFile -FilePath 'cmd.exe' -ArgumentList $frontendCommand -WorkingDirectory $frontendRoot