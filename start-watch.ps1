param(
  [switch]$Bootstrap,
  [switch]$BackendWatch
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
$exercisesRoot = Join-Path $projectRoot 'exercises'
$translationsPath = Join-Path $projectRoot 'exercise_name_translations.csv'

$frontendPidFile = Join-Path $runtimeDir 'frontend-watch.pid'
$backendPidFile = Join-Path $runtimeDir 'backend-watch.pid'
$frontendLogFile = Join-Path $runtimeDir 'frontend-watch.log'
$backendLogFile = Join-Path $runtimeDir 'backend-watch.log'
$backendErrorLogFile = "$backendLogFile.err"
$backendSupervisorLogFile = Join-Path $runtimeDir 'backend-watch-supervisor.log'

$backendUrl = 'http://127.0.0.1:8000'
$backendHealthUrl = "$backendUrl/api/health"
$frontendUrl = 'http://127.0.0.1:5173'

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

function Test-HttpReady {
  param([string]$Url)

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    return ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500)
  } catch {
    return $false
  }
}

function Test-BackendReady {
  return Test-HttpReady -Url $backendHealthUrl
}

function Test-FrontendReady {
  return Test-HttpReady -Url $frontendUrl
}

function Stop-ProcessTree {
  param([int]$ProcessId)

  if (-not (Test-ProcessRunning -ProcessId $ProcessId)) {
    return
  }

  try {
    taskkill /PID $ProcessId /T /F *> $null
    if ($LASTEXITCODE -ne 0) {
      throw "taskkill завершился с кодом $LASTEXITCODE"
    }
  } catch {
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  }
}

function Test-BackendWatchPath {
  param([string]$Path)

  if ([string]::IsNullOrWhiteSpace($Path)) {
    return $false
  }

  $fullPath = [System.IO.Path]::GetFullPath($Path)
  $extension = [System.IO.Path]::GetExtension($fullPath).ToLowerInvariant()
  if ($extension -notin @('.py', '.json', '.csv')) {
    return $false
  }

  if ($fullPath -eq [System.IO.Path]::GetFullPath($translationsPath)) {
    return $true
  }

  $backendFullPath = [System.IO.Path]::GetFullPath($backendRoot).TrimEnd('\') + '\'
  $backendOpenApiPath = [System.IO.Path]::GetFullPath((Join-Path $backendRoot 'openapi')).TrimEnd('\') + '\'
  $exercisesFullPath = [System.IO.Path]::GetFullPath($exercisesRoot).TrimEnd('\') + '\'

  if ($fullPath.StartsWith($backendOpenApiPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $false
  }

  return (
    $fullPath.StartsWith($backendFullPath, [System.StringComparison]::OrdinalIgnoreCase) -or
    $fullPath.StartsWith($exercisesFullPath, [System.StringComparison]::OrdinalIgnoreCase)
  )
}

function Start-LoggedBackendServer {
  param(
    [string]$PythonExe,
    [string[]]$ArgumentList
  )

  $process = Start-Process -FilePath $PythonExe -ArgumentList $ArgumentList -WorkingDirectory $backendRoot -RedirectStandardOutput $backendLogFile -RedirectStandardError $backendErrorLogFile -WindowStyle Hidden -PassThru

  Write-SuccessLine "Backend server запущен. PID: $($process.Id)"

  return [pscustomobject]@{
    Process = $process
  }
}

function Stop-LoggedBackendServer {
  param([object]$BackendServer)

  if (-not $BackendServer) {
    return
  }

  $process = $BackendServer.Process

  if ($process -and -not $process.HasExited) {
    Stop-ProcessTree -ProcessId $process.Id
    [void]$process.WaitForExit(5000)
  }

  $process.Dispose()
}

function Invoke-BackendWatch {
  param([string]$PythonExe)

  $serverArgs = @(
    '-m', 'uvicorn', 'app.main:app',
    '--app-dir', $backendRoot,
    '--host', '127.0.0.1',
    '--port', '8000',
    '--timeout-graceful-shutdown', '2'
  )

  $script:backendRestartRequested = $false
  $script:backendLastChangeAt = Get-Date
  $script:backendChangedPaths = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

  $watchers = @()
  $eventSubscriptions = @()
  $watcherIndex = 0
  foreach ($watchPath in @($backendRoot, $exercisesRoot, $projectRoot)) {
    if (-not (Test-Path $watchPath)) {
      continue
    }

    $watcherIndex++
    $watcher = [System.IO.FileSystemWatcher]::new()
    $watcher.Path = $watchPath
    $watcher.IncludeSubdirectories = ($watchPath -ne $projectRoot)
    $watcher.Filter = '*.*'
    $watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, DirectoryName, LastWrite, Size'
    $eventSubscriptions += Register-ObjectEvent -InputObject $watcher -EventName Changed -SourceIdentifier "BackendWatch.$watcherIndex.Changed"
    $eventSubscriptions += Register-ObjectEvent -InputObject $watcher -EventName Created -SourceIdentifier "BackendWatch.$watcherIndex.Created"
    $eventSubscriptions += Register-ObjectEvent -InputObject $watcher -EventName Deleted -SourceIdentifier "BackendWatch.$watcherIndex.Deleted"
    $eventSubscriptions += Register-ObjectEvent -InputObject $watcher -EventName Renamed -SourceIdentifier "BackendWatch.$watcherIndex.Renamed"
    $watcher.EnableRaisingEvents = $true
    $watchers += $watcher
  }

  Write-InfoLine 'Backend supervisor следит за backend, exercises и exercise_name_translations.csv.'

  Remove-Item -Path $backendLogFile -Force -ErrorAction SilentlyContinue
  Remove-Item -Path $backendErrorLogFile -Force -ErrorAction SilentlyContinue

  $backendServer = $null
  try {
    $backendServer = Start-LoggedBackendServer -PythonExe $PythonExe -ArgumentList $serverArgs

    while ($true) {
      foreach ($event in @(Get-Event | Where-Object { $_.SourceIdentifier -like 'BackendWatch.*' })) {
        $eventArgs = $event.SourceEventArgs
        $eventPath = $eventArgs.FullPath
        $oldEventPath = if ($eventArgs -is [System.IO.RenamedEventArgs]) { $eventArgs.OldFullPath } else { $null }

        if ((Test-BackendWatchPath -Path $eventPath) -or ($oldEventPath -and (Test-BackendWatchPath -Path $oldEventPath))) {
          $script:backendRestartRequested = $true
          $script:backendLastChangeAt = Get-Date
          [void]$script:backendChangedPaths.Add($eventPath)
        }

        Remove-Event -EventIdentifier $event.EventIdentifier -ErrorAction SilentlyContinue
      }

      if ($backendServer.Process.HasExited) {
        $exitCode = $backendServer.Process.ExitCode
        Stop-LoggedBackendServer -BackendServer $backendServer
        Write-WarnLine "Backend server завершился с кодом $exitCode. Запускаю заново."
        $backendServer = Start-LoggedBackendServer -PythonExe $PythonExe -ArgumentList $serverArgs
      }

      if ($script:backendRestartRequested -and ((Get-Date) - $script:backendLastChangeAt).TotalMilliseconds -ge 700) {
        $changedPaths = @($script:backendChangedPaths | Sort-Object)
        $script:backendRestartRequested = $false
        [void]$script:backendChangedPaths.Clear()

        Write-WarnLine "Обнаружены изменения backend данных: $($changedPaths -join ', ')"
        Write-InfoLine 'Принудительно перезапускаю backend server.'
        Stop-LoggedBackendServer -BackendServer $backendServer
        $backendServer = Start-LoggedBackendServer -PythonExe $PythonExe -ArgumentList $serverArgs
      }

      Start-Sleep -Milliseconds 200
    }
  } finally {
    Stop-LoggedBackendServer -BackendServer $backendServer

    foreach ($watcher in $watchers) {
      $watcher.EnableRaisingEvents = $false
      $watcher.Dispose()
    }

    foreach ($subscription in $eventSubscriptions) {
      Unregister-Event -SubscriptionId $subscription.Id -ErrorAction SilentlyContinue
    }
    Get-Event | Where-Object { $_.SourceIdentifier -like 'BackendWatch.*' } | Remove-Event -ErrorAction SilentlyContinue
  }
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
  $backendReady = $backendPid -and (Test-BackendReady)
  $frontendReady = $frontendPid -and (Test-FrontendReady)

  if ($backendPid) {
    if ($backendReady) {
      Write-SuccessLine "Backend watch запущен. PID: $backendPid"
    } else {
      Write-WarnLine "Backend watch PID есть, но API пока не отвечает. PID: $backendPid"
    }
    Write-PathLine 'Лог: ' $backendLogFile
    Write-PathLine 'Ошибки: ' $backendErrorLogFile
    Write-PathLine 'Supervisor: ' $backendSupervisorLogFile
  }

  if ($frontendPid) {
    if ($frontendReady) {
      Write-SuccessLine "Frontend watch запущен. PID: $frontendPid"
    } else {
      Write-WarnLine "Frontend watch PID есть, но сервер пока не отвечает. PID: $frontendPid"
    }
    Write-PathLine 'Лог: ' $frontendLogFile
    Write-PathLine 'Ошибки: ' "$frontendLogFile.err"
  }

  if (-not $backendReady -or -not $frontendReady) {
    Write-WarnLine 'Не удалось подтвердить готовность обоих серверов. Проверьте логи в .runtime.'
  }

  Write-Host ''
  Write-UrlLine 'Backend URL:  ' $backendUrl
  Write-UrlLine 'Frontend URL: ' $frontendUrl
}

function Start-WatchProcess {
  param(
    [string]$Name,
    [string]$PidFile,
    [string]$LogFile,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [scriptblock]$HealthCheck = $null
  )

  $existingPid = Get-PidFromFile -PidFile $PidFile
  if ($existingPid) {
    if ($null -ne $HealthCheck -and -not (& $HealthCheck)) {
      Write-WarnLine "$Name найден по PID, но не отвечает. Перезапускаю. PID: $existingPid"
      Stop-ProcessTree -ProcessId $existingPid
      Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    } else {
      Write-InfoLine "$Name уже запущен. PID: $existingPid"
      Write-PathLine 'Лог: ' $LogFile
      return
    }
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

if ($BackendWatch) {
  $pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
  if (-not (Test-Path $pythonExe)) {
    throw "Не найден Python окружения: $pythonExe"
  }

  Invoke-BackendWatch -PythonExe $pythonExe
  return
}

if (-not $Bootstrap) {
  $existingBackendPid = Get-PidFromFile -PidFile $backendPidFile
  $existingFrontendPid = Get-PidFromFile -PidFile $frontendPidFile

  if ($existingBackendPid -or $existingFrontendPid) {
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
      if ($existingBackendPid -and $existingFrontendPid -and (Test-BackendReady) -and (Test-FrontendReady)) {
        Show-StartSummary
        return
      }

      Start-Sleep -Milliseconds 100
      $existingBackendPid = Get-PidFromFile -PidFile $backendPidFile
      $existingFrontendPid = Get-PidFromFile -PidFile $frontendPidFile
    }

    Write-WarnLine 'Найдены PID-файлы, но готовность серверов не подтверждена. Запускаю восстановление.'
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
    if ($backendPid -and $frontendPid -and (Test-BackendReady) -and (Test-FrontendReady)) {
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
  "set VITE_API_BASE_URL=$backendUrl&&`"$nodeExe`" `"$viteBin`" --host 127.0.0.1 --port 5173 --strictPort"
)

$backendWatcherCommand = @(
  '-NoProfile',
  '-ExecutionPolicy', 'Bypass',
  '-File', $PSCommandPath,
  '-BackendWatch'
)

$powershellExe = Join-Path $PSHOME 'powershell.exe'

Start-WatchProcess -Name 'Backend watch' -PidFile $backendPidFile -LogFile $backendSupervisorLogFile -FilePath $powershellExe -ArgumentList $backendWatcherCommand -WorkingDirectory $projectRoot -HealthCheck { Test-BackendReady }

Start-WatchProcess -Name 'Frontend watch' -PidFile $frontendPidFile -LogFile $frontendLogFile -FilePath 'cmd.exe' -ArgumentList $frontendCommand -WorkingDirectory $frontendRoot -HealthCheck { Test-FrontendReady }