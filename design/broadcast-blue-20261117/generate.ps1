$ErrorActionPreference='Stop'
$utf8=New-Object Text.UTF8Encoding($false)
$root='D:\eGym\design\broadcast-blue-20261117'
$screens=[IO.File]::ReadAllText((Join-Path $root 'screens.json'),$utf8)|ConvertFrom-Json
$variants=@($screens|ForEach-Object {@{id=$_.id;name=$_.name;style=('SCREEN: '+$_.name+'. FUNCTIONAL REQUIREMENTS: '+$_.spec)}})
$common=@'
Create ONE high-fidelity Forma touchscreen application redesign for the specified SCREEN. Attached image is the USER-APPROVED VISUAL DESIGN SYSTEM, NOT a layout template for unrelated screens. Match its premium sports broadcast aesthetic exactly: almost black charcoal canvas, blue #2878F0 active states and main buttons, warm white bold typography, subtle fine gray separators, restrained rounded dark panels. RED RESERVED FOR EMERGENCY/DESTRUCTIVE ACTIONS. Beautiful confident contemporary product design, not a dense admin dashboard or neon gaming screen. Layout tailored to each screen, excellent spacing and legible Russian text. Flat screen capture 1536x864 landscape, no device/perspective/collage, no explanatory design captions.
USABILITY: one obvious primary action, clear title and back path; human readable labels with units, group related controls; don't duplicate values as decorative badges. Large touch controls, readable secondary labels, stable action area. Distinguish data/controls, selected/disabled/error states with text as well as color. Never crowd all tab content into one screen: show selected tab only and preserve access to others. Long lists may have visible scrolling area but main actions remain visible. Avoid invented features, social sharing, points, new AI features. Keep actual functionality listed below; illustrative data marked by context not fake live telemetry. Preserve unavailable data as dash.
GLOBAL SHELL: for authenticated everyday pages, consistent slim LEFT navigation with icons AND short Russian labels Главная/Тренировки/Каталог/Календарь/Прогресс/Профиль/Настройки; achievements and fatigue reached via progress/dashboard, not overloaded main nav. Compact upper strip with AI · ВЫКЛ, Моторы — % / — кг, Нет связи and RED Аварийная остановка always visible upper right, even during dialogs. Selected profile in navigation footer where appropriate. For active exercise/setup/rest/summary prioritize content: compact navigation/back, not full sidebar if distracting. Service screens clearly marked Сервис; never suggest hardware is live or safe when disconnected. Do not display secrets/PIN/API keys. Dialogs preserve accessible emergency control.
Use existing approved visual language, not red accent, not duplicate blue weight badges. For human diagrams show anatomically plausible neutral fitness graphics; adult photo subjects in opaque fitness clothing. All content in correct Russian, short meaningful text, no lorem ipsum. A polished plausible complete screen matching functional inventory, not a coded implementation. Only output finished screen.
'@
$base=[IO.File]::ReadAllText('D:\eGym\temp\ui-concepts-preserved-20261116\generate.ps1',$utf8)
$a=$base.IndexOf('$variants = @(');$b=$base.IndexOf('$priorUsage = ')
$script=$base.Substring(0,$a)+$base.Substring($b)
$script=$script.Replace("\temp\ui-concepts-preserved-20261116'","\design\broadcast-blue-20261117'")
$script=$script.Replace("Join-Path `$root 'reference-current.png'","'D:\eGym\temp\ui-broadcast-clean-20261117\01-broadcast-clean.png'")
$script=$script.Replace("\temp\ui-concepts-20261116\ledger.json","\temp\ui-broadcast-clean-20261117\ledger.json")
$script=$script.Replace('$priorEstimate = ($priorUsage.text','$priorEstimate = [double]$old.prior_estimate_usd + ($priorUsage.text')
& ([scriptblock]::Create($script))
# Generate derived visual assets and browsable offline index after the bounded batch.
Copy-Item 'D:\eGym\temp\ui-broadcast-clean-20261117\01-broadcast-clean.png' (Join-Path $root 'approved-reference.png')
Add-Type -AssemblyName System.Drawing
$html=New-Object Text.StringBuilder
[void]$html.Append('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Forma — Broadcast Blue</title><style>body{margin:0;background:#101318;color:#f1f4f8;font:17px/1.5 system-ui}main{max-width:1700px;margin:auto;padding:32px}a{color:#80b3ff}p{color:#adb8c7}nav{display:flex;gap:18px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:26px}img{width:100%;border-radius:12px}h2{margin:48px 0 20px}h3{margin-bottom:5px}code{color:#adb8c7}@media(max-width:550px){.grid{grid-template-columns:1fr}main{padding:15px}}</style><main><h1>Forma · Broadcast Blue</h1><p>Редизайн экранов по утверждённому стилю. Статичные изображения-концепты, не реализация. Функциональная карта составлена по текущему коду; точность текста, состояний и полнота контролов требуют сверки перед разработкой. Нажмите изображение для полного размера.</p><nav><a href="approved-reference.png">Утверждённый референс</a><a href="README.md">Объём и ограничения</a>')
[void]$html.Append('<a href="REVIEW.md">Замечания проверки</a>')
foreach($group in ($screens|Group-Object section)){[void]$html.Append('<a href="#'+[uri]::EscapeDataString($group.Name)+'">'+$group.Name+'</a>')}
[void]$html.Append('</nav>')
[void]$html.Append('<p style="padding:18px;border:1px solid #c99b43;border-radius:12px">Получен 41 макет из 42. Экран «Усталость и восстановление» отклонён провайдером, повторов нет. В макете 41 параметры машины ошибочно заменены параметрами тела — не использовать для реализации. Перед разработкой обязательно прочитать замечания проверки.</p>')
foreach($group in ($screens|Group-Object section)){
 [void]$html.Append('<h2 id="'+[uri]::EscapeDataString($group.Name)+'">'+$group.Name+'</h2><div class="grid">')
 foreach($s in $group.Group){
  if(Test-Path (Join-Path $root ($s.id+'.png'))){[void]$html.Append('<article><h3>'+[Net.WebUtility]::HtmlEncode($s.name)+'</h3><p>'+[Net.WebUtility]::HtmlEncode($s.route)+'</p><a href="'+$s.id+'.png"><img loading="lazy" src="'+$s.id+'.png" alt="'+[Net.WebUtility]::HtmlEncode($s.name)+'"></a></article>')}
 }
 [void]$html.Append('</div>')
}
[void]$html.Append('</main></html>')
[IO.File]::WriteAllText((Join-Path $root 'index.html'),$html.ToString(),$utf8)
$files=@($screens|Where-Object {Test-Path (Join-Path $root ($_.id+'.png'))})
for($page=0;$page -lt [math]::Ceiling($files.Count/12);$page++){
 $batch=@($files|Select-Object -Skip ($page*12) -First 12)
 $sheet=New-Object Drawing.Bitmap(1920,([int][math]::Ceiling($batch.Count/3)*395))
 $g=[Drawing.Graphics]::FromImage($sheet);$g.Clear([Drawing.Color]::FromArgb(230,234,240));$g.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
 $font=New-Object Drawing.Font('Arial',14)
 for($i=0;$i -lt $batch.Count;$i++){
  $x=($i%3)*640;$y=[math]::Floor($i/3)*395
  $image=[Drawing.Image]::FromFile((Join-Path $root ($batch[$i].id+'.png')))
  $g.DrawImage($image,[int]$x,[int]($y+32),640,360);$image.Dispose()
  $g.DrawString($batch[$i].name,$font,[Drawing.Brushes]::Black,[single]($x+8),[single]($y+4))
 }
 $sheet.Save((Join-Path $root ('overview-'+($page+1)+'.jpg')),[Drawing.Imaging.ImageFormat]::Jpeg)
 $font.Dispose();$g.Dispose();$sheet.Dispose()
}
Write-Output ('Gallery complete: '+$files.Count+' screens')