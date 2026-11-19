# Bake the Russian award lines once so the kiosk can play them offline.
[CmdletBinding()]
param([string]$Voice = 'Microsoft Irina Desktop')

$ErrorActionPreference = 'Stop'
$backend = Split-Path $PSScriptRoot
$content = Join-Path $backend 'app/services/achievements/content/workout-titles.ru.json'
$root = Join-Path $backend 'media/achievements/collection'
$audioDir = Join-Path $root 'voice'
$null = [IO.Directory]::CreateDirectory($audioDir)
$entries = Get-Content -Raw -Encoding UTF8 $content | ConvertFrom-Json
$archive = @{}
$legacy = Join-Path (Split-Path $content) 'v2/catalog.json'
foreach ($series in (Get-Content -Raw -Encoding UTF8 $legacy | ConvertFrom-Json).lines) {
    $archive[$series.id] = $series.tiers
}
$encoder = (Get-Command ffmpeg -ErrorAction Stop).Source
Add-Type -AssemblyName System.Speech
$reader = New-Object System.Speech.Synthesis.SpeechSynthesizer
$work = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString() + '.wav')
$clips = [ordered]@{}
$digest = [Security.Cryptography.SHA256]::Create()
try {
    $reader.SelectVoice($Voice)
    $reader.Rate = 0
    foreach ($series in $entries.PSObject.Properties) {
        $entry = $series.Value
        $phrases = if ($entry.phrases) { $entry.phrases } else { $archive[$series.Name].phrase }
        if ($phrases.Count -ne $entry.tiers.Count) { throw "Missing voice lines for $($series.Name)" }
        for ($i = 0; $i -lt $entry.tiers.Count; $i++) {
            $id = '{0}:t{1}' -f $series.Name, ($i + 1)
            $title = $entry.tiers[$i]
            if ($title -notmatch '[.!?\u2026]$') { $title += '.' }
            $line = "$title $($phrases[$i])"
            $hash = $digest.ComputeHash([Text.Encoding]::UTF8.GetBytes("$Voice|ru-awards-v1|$line"))
            $rev = ([BitConverter]::ToString($hash) -replace '-', '').Substring(0, 12).ToLowerInvariant()
            $name = ($id -replace '[.:]', '-') + ".$rev.mp3"
            $target = Join-Path $audioDir $name
            if (-not [IO.File]::Exists($target)) {
                $reader.SetOutputToWaveFile($work)
                $reader.Speak($line)
                $reader.SetOutputToNull()
                $stage = "$target.$([guid]::NewGuid()).mp3"
                try {
                    & $encoder -v error -nostdin -y -i $work -af 'highpass=f=55,loudnorm=I=-17:TP=-2:LRA=7' -ar 24000 -ac 1 -c:a libmp3lame -b:a 56k $stage
                    if ($LASTEXITCODE -ne 0 -or (Get-Item $stage).Length -lt 2500) { throw "Encoding failed for $id" }
                    [IO.File]::Move($stage, $target)
                } finally {
                    if ([IO.File]::Exists($stage)) { [IO.File]::Delete($stage) }
                }
            }
            $clips[$id] = $name
        }
    }
    if (-not $clips.Count) { throw 'No recordings found' }
    $manifest = [ordered]@{ voice = $Voice; clips = $clips } | ConvertTo-Json -Depth 3
    $stageManifest = Join-Path $root ("voice." + [guid]::NewGuid() + ".tmp")
    [IO.File]::WriteAllText($stageManifest, $manifest + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $stageManifest -Destination (Join-Path $root 'voice.json') -Force
    Write-Output "$($clips.Count) Russian recordings ready"
} finally {
    $reader.Dispose()
    $digest.Dispose()
    if ([IO.File]::Exists($work)) { [IO.File]::Delete($work) }
}
