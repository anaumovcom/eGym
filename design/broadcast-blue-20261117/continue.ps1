$ErrorActionPreference='Stop'
$utf8=New-Object Text.UTF8Encoding($false)
$path='D:\eGym\design\broadcast-blue-20261117\generate.ps1'
$code=[IO.File]::ReadAllText($path,$utf8)
$code=$code.Replace('$variants=@($screens|ForEach-Object', '$variants=@($screens|Where-Object {[int]$_.id.Substring(0,2) -ge 29}|ForEach-Object')
$needle='& ([scriptblock]::Create($script))'
$replacement=@'
$prior=[IO.File]::ReadAllText((Join-Path $root 'ledger.json'),$utf8)|ConvertFrom-Json
$start=$script.IndexOf('$priorUsage = ')
$finish=$script.IndexOf('$ledger = [ordered]@{')
$prefix='$priorEstimate = '+([double]$prior.estimate_usd+0.75).ToString([Globalization.CultureInfo]::InvariantCulture)+"`n"
$script=$script.Substring(0,$start)+$prefix+$script.Substring($finish)
$script=$script.Replace("Join-Path `$root 'ledger.json'","Join-Path `$root 'continuation-ledger.json'")
& ([scriptblock]::Create($script))
'@
$code=$code.Replace($needle,$replacement)
& ([scriptblock]::Create($code))