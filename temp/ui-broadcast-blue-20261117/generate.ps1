$ErrorActionPreference='Stop'
$utf8=New-Object Text.UTF8Encoding($false)
$variants=@(@{id='01-broadcast-blue';name='Спортивная трансляция — синий';style='Use rich premium electric royal blue #2878F0 as main accent with lighter blue #60A5FA for small highlights. Keep all normal controls including finish-set blue; emergency stop only remains red.'})
$common=@'
Precisely edit the ATTACHED approved Forma UI image. User likes THIS EXACT sports broadcast design and requests ONLY changing main accent color from red/orange/vermilion to BLUE. Preserve identical composition, panel positions, video, athlete, barbell, all typography, Russian labels, numbers, spacing, sizes, dark black background and warm-white text. No redesign, no added controls, no removed content, no new layout.
Replace all decorative red/orange accents, current-set outline, current set tag, repetition progress line, weight stepper accent, tiny active dots, bar-position current-marker accent and bottom-right "Завершить подход" primary action with elegant saturated royal BLUE #2878F0. Keep contrast on blue buttons with white text. Retain muted white/gray secondary controls. Do not tint athlete or video blue.
EXCEPTION: upper-right emergency control "Аварийная остановка" must stay RED, visibly distinct from blue routine actions. Other warning-status semantics remain unchanged. Preserve every existing text and number exactly; do not create new labels. Output only full-screen flat UI screenshot, same landscape aspect ratio, no frame, no commentary, no crop. This is a faithful color edit of approved image, not a new concept.
'@
$base=[IO.File]::ReadAllText('D:\eGym\temp\ui-concepts-preserved-20261116\generate.ps1',$utf8)
$a=$base.IndexOf('$variants = @(');$b=$base.IndexOf('$priorUsage = ')
$script=$base.Substring(0,$a)+$base.Substring($b)
$script=$script.Replace("\temp\ui-concepts-preserved-20261116'","\temp\ui-broadcast-blue-20261117'")
$script=$script.Replace("Join-Path `$root 'reference-current.png'","'D:\eGym\temp\ui-next-20261116\01-broadcast.png'")
$script=$script.Replace("\temp\ui-concepts-20261116\ledger.json","\temp\ui-next-20261116\ledger.json")
$script=$script.Replace('$priorEstimate = ($priorUsage.text','$priorEstimate = [double]$old.prior_estimate_usd + ($priorUsage.text')
& ([scriptblock]::Create($script))