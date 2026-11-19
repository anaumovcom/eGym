$ErrorActionPreference='Stop'
$utf8=New-Object Text.UTF8Encoding($false)
$variants=@(@{id='01-broadcast-clean';name='Без дублирования';style='Remove ONLY two upper blue weight badges and two tiny bottom-of-rail sensor chips. Preserve all other information and approved blue layout.'})
$common=@'
Perform a precise minimal edit of this approved Forma UI screenshot. Remove FOUR redundant widgets only:
1 Remove the blue outlined dumbbell badge "21 кг" ABOVE THE REPETITION COUNTER near x=875,y=135.
2 Remove the identical blue outlined dumbbell badge "21 кг" ABOVE THE SET PLAN near x=1160,y=130.
3 Remove the small chip "Ампл. —%" at the BOTTOM of the far-right vertical bar-position panel near x=1400,y=546.
4 Remove the adjacent small chip "Синхр. — мм" near x=1470,y=546.
Fill removed areas seamlessly with existing dark panel background. Do not add replacement widgets. Leave clean negative space; do not substantially reflow or resize other components. Vertical position panel may end cleanly after its ruler.
IMPORTANT keep the bottom-left weight stepper "Вес, кг" minus / 21 / plus. Keep weight prescription text inside ALL FOUR set-plan rows (10–12 × 21 кг and 8–12 × 42,5 кг). Keep main bottom amplitude metric АМПЛИТУДА 92%, ТЕМП хорошо, ПОЛОЖЕНИЕ ГРИФА 86 см. Keep entire vertical position ruler with upper 1320, current 980, lower 640. Keep video on left unchanged, large 9 counter and minus/plus in center, set plan right, all header/navigation, emergency stop red, finish action blue, skip and warmup note. Preserve exact composition, palette, athlete, all remaining labels and values. No other edits, no duplicated or new controls. Full landscape screen screenshot 1536x864, no commentary or device.
'@
$base=[IO.File]::ReadAllText('D:\eGym\temp\ui-concepts-preserved-20261116\generate.ps1',$utf8)
$a=$base.IndexOf('$variants = @(');$b=$base.IndexOf('$priorUsage = ')
$script=$base.Substring(0,$a)+$base.Substring($b)
$script=$script.Replace("\temp\ui-concepts-preserved-20261116'","\temp\ui-broadcast-clean-20261117'")
$script=$script.Replace("Join-Path `$root 'reference-current.png'","'D:\eGym\temp\ui-broadcast-blue-left-20261117\01-broadcast-blue-left.png'")
$script=$script.Replace("\temp\ui-concepts-20261116\ledger.json","\temp\ui-broadcast-blue-left-20261117\ledger.json")
$script=$script.Replace('$priorEstimate = ($priorUsage.text','$priorEstimate = [double]$old.prior_estimate_usd + ($priorUsage.text')
& ([scriptblock]::Create($script))