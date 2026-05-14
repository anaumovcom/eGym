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

$pidFiles = @(
  Join-Path $runtimeDir 'frontend-watch.pid'
  Join-Path $runtimeDir 'backend-watch.pid'
)

function Write-InfoLine {
  param([string]$Message)

  Write-Host $Message -ForegroundColor Cyan
}

function Write-SuccessLine {
  param([string]$Message)

  Write-Host $Message -ForegroundColor Green
}

function Write-WarnLine {
  param([string]$Message)

  Write-Host $Message -ForegroundColor Yellow
}

function Get-PidFromFile {
  param([string]$PidFile)

  if (-not (Test-Path $PidFile)) {
    return $null
  }

  $rawPid = (Get-Content -Path $PidFile -Raw).Trim()
  $parsedPid = 0
  if (-not [int]::TryParse($rawPid, [ref]$parsedPid)) {
    return $null
  }

  return $parsedPid
}

function Get-ProjectProcessIds {
  $frontendPattern = [Regex]::Escape($frontendRoot)
  $backendPattern = [Regex]::Escape($backendRoot)

  $processes = Get-CimInstance Win32_Process | Where-Object {
    $commandLine = $_.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
      return $false
    }

    $isFrontend = ($commandLine -match $frontendPattern) -and ($commandLine -match 'vite' -or $commandLine -match 'npm(\.cmd)?\s+run\s+dev')
    $isBackend = (($commandLine -match $backendPattern) -or ($commandLine -match 'uvicorn' -and $commandLine -match 'app\.main:app' -and $commandLine -match '--port\s+8000'))

    return $isFrontend -or $isBackend
  }

  return @($processes | ForEach-Object { $_.ProcessId })
}

$allPids = New-Object System.Collections.Generic.HashSet[int]

foreach ($pidFile in $pidFiles) {
  $processId = Get-PidFromFile -PidFile $pidFile
  if ($processId) {
    [void]$allPids.Add($processId)
  }
}

foreach ($processId in Get-ProjectProcessIds) {
  if ($processId) {
    [void]$allPids.Add([int]$processId)
  }
}

if ($allPids.Count -eq 0) {
  foreach ($pidFile in $pidFiles) {
    Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
  }
  Write-InfoLine 'Запущенные frontend/backend процессы этого проекта не найдены.'
  exit 0
}

foreach ($processId in ($allPids | Sort-Object)) {
  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if (-not $process) {
    continue
  }

  try {
    taskkill /PID $processId /T /F *> $null
    if ($LASTEXITCODE -ne 0) {
      throw "taskkill завершился с кодом $LASTEXITCODE"
    }
    Write-SuccessLine "Остановлен PID: $processId ($($process.ProcessName))"
  } catch {
    if (-not (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
      Write-InfoLine "PID $processId уже остановлен."
      continue
    }

    Write-WarnLine "Не удалось остановить PID ${processId}: $($_.Exception.Message)"
  }
}

foreach ($pidFile in $pidFiles) {
  Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
}