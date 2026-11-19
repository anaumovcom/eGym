$ErrorActionPreference='Stop'
$utf8=New-Object Text.UTF8Encoding($false)
$variants=@(@{id='01-broadcast-blue-left';name='Синий — видео слева';style='Move exercise video to LEFT of main content, repetition counter to CENTER, keep set plan RIGHT. Preserve royal blue accent and red emergency stop.'})
$common=@'
Edit this attached APPROVED blue Forma sports broadcast UI. User requests one specific layout change: MOVE THE EXERCISE VIDEO TO THE LEFT PART OF THE SCREEN. Swap main video and repetition-counter regions: large landscape video frame in LEFT half of main content; large repetition counter 9 in CENTER column immediately to the right of video; four-set plan stays in RIGHT column. Video must clearly be leftmost main content region, not centered. Keep full athlete doing floor barbell press visible without cropping. Keep rep target and both minus/plus buttons with the relocated counter. Rebalance widths gracefully: video approx 48%, counter 25%, plan 27% of content width. Maintain same polished sports broadcast style.
Everything else remains faithful to approved image: dark charcoal background, royal BLUE #2878F0 accents, white typography, title Жим с пола со штангой, metadata, system header, all FOUR set entries, lower weight stepper with minus/plus, three movement metrics, horizontal position instrument with lower 640/current 980/upper 1320 labels, bottom skip and blue finish action. Keep upper-right emergency stop RED. Preserve all Russian text, values, controls and semantic states from reference; no new controls or missing elements, no duplicated counters. Header and lower console unchanged unless small spacing adjustment needed. Do not change color palette or overall visual identity. Flat full-screen UI screenshot, landscape 1536x864, no device, no explanation, no collage.
'@
$base=[IO.File]::ReadAllText('D:\eGym\temp\ui-concepts-preserved-20261116\generate.ps1',$utf8)
$a=$base.IndexOf('$variants = @(');$b=$base.IndexOf('$priorUsage = ')
$script=$base.Substring(0,$a)+$base.Substring($b)
$script=$script.Replace("\temp\ui-concepts-preserved-20261116'","\temp\ui-broadcast-blue-left-20261117'")
$script=$script.Replace("Join-Path `$root 'reference-current.png'","'D:\eGym\temp\ui-broadcast-blue-20261117\01-broadcast-blue.png'")
$script=$script.Replace("\temp\ui-concepts-20261116\ledger.json","\temp\ui-broadcast-blue-20261117\ledger.json")
$script=$script.Replace('$priorEstimate = ($priorUsage.text','$priorEstimate = [double]$old.prior_estimate_usd + ($priorUsage.text')
& ([scriptblock]::Create($script))