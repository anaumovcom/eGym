$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Net.Http
$root = 'D:\eGym\temp\ui-concepts-preserved-20261116'
$utf8 = New-Object Text.UTF8Encoding($false)
$reference = Join-Path $root 'reference-current.png'
if (-not (Test-Path $reference)) { throw 'Reference missing' }
$ledgerPath = Join-Path $root 'ledger.json'
if (Test-Path $ledgerPath) { throw 'Ledger exists. Inspect before resuming.' }
$envText = [IO.File]::ReadAllText('D:\eGym\backend\.env.local', $utf8)
$m = [regex]::Match($envText, '(?m)^OPENAI_API_KEY\s*=\s*(.+?)\s*$')
if (-not $m.Success) { throw 'Key not found' }
$key = $m.Groups[1].Value.Trim().Trim('"').Trim("'")
$envText = $null
$variants = @(
  @{id='01-graphite';name='Graphite';style='Premium matte graphite and warm ivory with muted champagne accent. Quiet professional industrial luxury. Flat broad surfaces, subtle separators, refined slightly rounded rectangles. Elegant large numerals. Absolutely no glowing borders.'},
  @{id='02-studio';name='Studio';style='LIGHT warm off-white studio theme. Charcoal text, sage green controls, warm gray separators. Pale surfaces, airy spacing, rounded but mature controls. Maintain high contrast even in secondary text. Warm home fitness product.'},
  @{id='03-performance';name='Performance';style='High contrast sports performance equipment. Near black and pure white, electric lime accent only for selected/primary states. Crisp geometric slightly squared panels, confident condensed athletic numerals, strict precise grid. No neon glow.'},
  @{id='04-midnight';name='Midnight';style='Midnight navy professional coaching equipment. Layered blue-gray surfaces, icy cyan accents, precise white typography. Calm polished contemporary interface, subtle depth, generous consistent gutters, no decorative gradients.'},
  @{id='05-porcelain';name='Porcelain';style='LIGHT cool porcelain and white theme with cobalt blue primary controls. Very sharp Swiss editorial typography, hairline slate dividers, almost square panels, scientific precision. Strong dark text and very clear active set.'},
  @{id='06-evergreen';name='Evergreen';style='Deep forest green and graphite surfaces, pale mint primary accent and soft ivory text. Sophisticated quiet premium wellness technology. Medium rounded panels, subtle tonal elevation, clean typography. Never color emergency stop green.'},
  @{id='07-titanium';name='Titanium';style='Neutral titanium gray professional equipment. Medium charcoal gray background, light gray raised surfaces, white numbers, restrained orange accents. Machined functional precision without metal textures, screws, skeuomorphism or glow. Distinct sturdy flat buttons.'},
  @{id='08-sand';name='Sand';style='LIGHT warm sand and cream with dark brown ink and muted rust primary controls. Architectural elegant home equipment, restrained editorial typography, soft rectangular panels, ample breathing room. No beige text on beige, use strong readable contrast.'},
  @{id='09-indigo';name='Indigo';style='Deep dark indigo with soft periwinkle primary accent and neutral white text. Modern approachable personal training UI, rounded organized panels and pill set-plan chips, very clean professional restraint. No gradients, excessive purple or glow.'},
  @{id='10-monochrome';name='Monochrome';style='Ultra clear monochrome functional minimalism. Near-black background, white typography and white primary finish control with black text. Gray secondary controls and separators. Red reserved for emergency stop, small green only for good movement status. Remove visual chrome, not content; exceptionally clear type hierarchy.'}
)
$common = @'
Edit the ATTACHED REAL APPLICATION SCREENSHOT into a polished visual redesign of the SAME screen. This is a conservative functional-preserving reskin, NOT a new simplified concept. Landscape flat screen capture, no device, no perspective, no collage. Keep the same three-column topology: large exercise video on left; main set/repetition/weight/metrics panel center-right; tall vertical bar-position rail at far right; system strip above and full-width action dock below. Improve use of space, alignment, typography, readable hierarchy and coherent touch control styling. Preserve every existing interface element and visible Russian label, including secondary controls. Do not replace controls with decorative illustrations. Do not invent new controls or hide controls behind menus.
MANDATORY VISIBLE INVENTORY FROM REFERENCE:
1 Top system strip: "AI · ВЫКЛ", "МОТОРЫ", "— %", "— кг", disconnected warning indicator, prominent red "Аварийная остановка" at upper right. Preserve disconnected status, never falsely show ready.
2 Upper exercise metadata: "Упражнение 1 из 5", "Базовый режим", "Упражнения" with five workout dots and "0/5", title "Жим с пола со штангой", "Подход 1 из 4", "Разминка", weight badge "21 кг".
3 Left video frame: retain the actual floor-press exercise demonstration and its role/footprint, not a generic athlete standing. No new playback toolbar. This is existing video content, not artwork to replace.
4 Set-plan track with ALL FOUR entries: "Р · СЕЙЧАС · 10–12 × 21 кг" selected; "1 · РАБОЧИЙ · 8–12 × 42,5 кг"; "2 · РАБОЧИЙ · 8–12 × 42,5 кг"; "3 · РАБОЧИЙ · 8–12 × 42,5 кг". All four stay readable.
5 Large repetition counter "9" with distinct minus button on left AND plus button on right, label "повторы · цель 10–12 повторов", horizontal progress bar.
6 Separate adjustable weight control label "Вес, кг", minus, value "21", plus. Do not omit these small minus/plus buttons or merge them into repetition control.
7 THREE movement metric tiles: "АМПЛИТУДА 92%", "ТЕМП хорошо", "ПОЛОЖЕНИЕ ГРИФА 86 см". Preserve even though rail also displays position.
8 Far-right vertical position instrument: "ПОЛОЖЕНИЕ · ММ", upper endpoint "ВЕРХ 1320", current marker "ГРИФ 980", lower endpoint "НИЗ 640". Keep marker between endpoints and visible range. Below rail BOTH compact status values "Ампл. —%" and "Синхр. — мм". Do not convert millimeters to arbitrary values or erase missing-data dashes.
9 Bottom action dock: left "Пропустить упражнение" button, center "Лёгкий разминочный подход.", right prominent "Завершить подход" button. Preserve entire dock, no cropping.
Do not add a pause button: not visible in this captured state. Do not invent calibration controls, profile avatar or other controls not present in this exact captured state. This redesign preserves the existing state and interaction inventory; conditional states remain a separate implementation concern. Fit all content within canvas, without clipping or scrollbars. All small labels should be readable, native Russian, professional typographic quality. Do not print the design variant name on screen. Final output only redesigned screen.
'@
$priorUsage = [ordered]@{text=0;image=0;output=0}
$oldLedger = 'D:\eGym\temp\ui-concepts-20261116\ledger.json'
if (Test-Path $oldLedger) {
  $old = [IO.File]::ReadAllText($oldLedger,$utf8) | ConvertFrom-Json
  foreach ($r in $old.requests) {
    if ($r.status -ne 'completed' -or -not $r.usage) { throw 'Prior billing cannot be reconciled' }
    $priorUsage.text += $r.usage.input_tokens_details.text_tokens
    $priorUsage.image += $r.usage.input_tokens_details.image_tokens
    $priorUsage.output += $r.usage.output_tokens
  }
}
# Conservative accounting rates, USD / 1M tokens; estimates, not provider invoice.
$priorEstimate = ($priorUsage.text * 5 + $priorUsage.image * 8 + $priorUsage.output * 30) / 1000000
$ledger = [ordered]@{model='gpt-image-2.5-flare';budget_usd=10;prior_estimate_usd=$priorEstimate;estimate_usd=$priorEstimate;reservation_per_request_usd=0.75;reference='reference-current.png';requests=@()}
function Save-Ledger { [IO.File]::WriteAllText($ledgerPath,($ledger | ConvertTo-Json -Depth 15),$utf8) }
Save-Ledger
$client = New-Object Net.Http.HttpClient
$client.Timeout = [TimeSpan]::FromMinutes(10)
$client.DefaultRequestHeaders.Authorization = New-Object Net.Http.Headers.AuthenticationHeaderValue('Bearer',$key)
try {
  foreach ($v in $variants) {
    if ($ledger.estimate_usd + $ledger.reservation_per_request_usd -gt $ledger.budget_usd) { throw 'Budget gate reached' }
    $prompt = $common + "`nVISUAL DIRECTION: " + $v.style
    [IO.File]::WriteAllText((Join-Path $root ($v.id + '-prompt.txt')),$prompt,$utf8)
    $record = [ordered]@{id=$v.id;name=$v.name;status='reserved';reserved_usd=0.75;estimate_usd=$null;usage=$null;started_at=[DateTime]::UtcNow.ToString('o')}
    $ledger.requests += $record
    Save-Ledger
    $form = New-Object Net.Http.MultipartFormDataContent
    $response = $null
    try {
      foreach ($entry in @{model=$ledger.model;prompt=$prompt;n='1';size='1536x864';quality='medium';output_format='png'}.GetEnumerator()) {
        $content = New-Object Net.Http.StringContent([string]$entry.Value,$utf8)
        $form.Add($content,[string]$entry.Key)
      }
      $image = New-Object Net.Http.ByteArrayContent -ArgumentList (,[IO.File]::ReadAllBytes($reference))
      $image.Headers.ContentType = New-Object Net.Http.Headers.MediaTypeHeaderValue('image/png')
      $form.Add($image,'image','reference-current.png')
      Write-Output ('Generating ' + $v.id)
      $response = $client.PostAsync('https://api.openai.com/v1/images/edits',$form).GetAwaiter().GetResult()
      $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
      if (-not $response.IsSuccessStatusCode) {
        $record.status = 'failed_or_unknown'
        $safeText = $text.Replace($key,'[REDACTED]')
        [IO.File]::WriteAllText((Join-Path $root 'api-error.json'),$safeText,$utf8)
        Write-Output ('Stopped HTTP ' + [int]$response.StatusCode + '. No retries.')
        Save-Ledger
        break
      }
      $result = $text | ConvertFrom-Json
      if (-not $result.data[0].b64_json) { throw 'No image returned' }
      [IO.File]::WriteAllBytes((Join-Path $root ($v.id + '.png')),[Convert]::FromBase64String($result.data[0].b64_json))
      $record.usage = $result.usage
      $record.status = 'completed'
      if (-not $result.usage) { $record.status='completed_usage_unknown'; Save-Ledger; break }
      $cost = ($result.usage.input_tokens_details.text_tokens * 5 + $result.usage.input_tokens_details.image_tokens * 8 + $result.usage.output_tokens * 30) / 1000000
      $record.estimate_usd = $cost
      $ledger.estimate_usd += $cost
      Save-Ledger
      Write-Output ('Saved ' + $v.id + '.png; estimated task total USD ' + $ledger.estimate_usd)
    } catch {
      $record.status='failed_or_unknown'
      Save-Ledger
      Write-Output 'Stopped on request error. No retries. Inspect local ledger.'
      break
    } finally {
      if ($response) { $response.Dispose() }
      $form.Dispose()
    }
  }
} finally { $client.Dispose(); $key=$null }
Write-Output 'Done.'