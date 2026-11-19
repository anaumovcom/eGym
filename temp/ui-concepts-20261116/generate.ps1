$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = 'D:\eGym\temp\ui-concepts-20261116'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$envText = [IO.File]::ReadAllText('D:\eGym\backend\.env.local', $utf8)
$match = [regex]::Match($envText, '(?m)^OPENAI_API_KEY\s*=\s*(.+?)\s*$')
if (-not $match.Success) { throw 'OPENAI_API_KEY not found' }
$key = $match.Groups[1].Value.Trim().Trim('"').Trim("'")
$envText = $null
$common = @'
Create a polished high fidelity UI design screenshot for Forma, a home strength training machine touchscreen app. Landscape 16:9, flat straight-on screen capture, no physical device, no perspective, no browser chrome, no collage. A complete usable exercise execution screen, beautiful professional product design, exquisite typography, coherent spacing, clear hierarchy, readable exact Russian text. Same scenario in every design: "Жим с пола", "Подход 2 из 3", "40 кг", huge "7" with smaller "из 10". Athlete demonstration if present: adult wearing normal sportswear lying supine on the floor, knees bent, doing barbell floor press, not bench press. Show persistent red "СТОП" emergency control at top right and bottom controls "Пауза" and "Завершить подход". Emergency stop visually distinct from routine controls. No charts unrelated to exercise, no invented branding, no tiny illegible paragraphs. Touch friendly large controls. Do not show design variant name in UI. Deliver only the finished app screen.
'@
$variants = @(
    @{ id='01-focus'; title='Forma Focus'; direction='Quiet premium minimalism. Matte graphite #17191b, ivory typography, restrained amber #d5ae69. Generous negative space, almost no cards, no glows, no decorative borders. Left 42 percent a modest clean athlete demonstration on subtle dark studio background; right huge elegant repetition number 7. Below number single coaching cue "Плавно опускайте". Thin vertical range-of-motion rail beside demonstration. Bottom three set-progress segments, weight and clean controls. Sophisticated editorial typography, calm luxurious industrial product.' },
    @{ id='02-studio'; title='Forma Studio'; direction='Warm LIGHT home fitness studio aesthetic. Warm off-white #f5f3ed background, charcoal text, sage #8ca48c and restrained terracotta. Airy asymmetrical layout, large athlete demonstration left on pale seamless background, reps right, soft flat surfaces and delicate separators. Ten discrete small repetition segments with seven filled sage. Visible concise rows "40 кг", "Подход 2 / 3", "Амплитуда в норме". Rounded touch controls, no gradients or glows. Inviting mature premium wellness product, not medical dashboard.' },
    @{ id='03-performance'; title='Forma Performance'; direction='Precision sports instrument, black #0c1010, bright white and sparing electric lime #c4fa53. Bold condensed athletic numerals, strict grid, angular clean geometry, no gold, no glow. Three purposeful columns: left huge reps 7/10 and load; center dominant tall vertical barbell motion instrument, actual position marker, upper and lower range endpoints labeled "Верх" and "Низ", clear current motion phase "Подъём"; right technique readouts "Темп 2–1–2", "Амплитуда 92%", "Баланс 50 / 50". Small exercise demonstration thumbnail only. Instrument is central, not a huge video. Crisp serious athletic equipment interface.' },
    @{ id='04-coach'; title='Forma Coach'; direction='Guided personal coach interface. Deep blue gray #182735, soft blue #9bc9ee, white. Main focal point is huge readable coaching instruction "Опускайте медленнее", with calm secondary line "Держите движение под контролем". Huge reps 7 / 10 on opposite side. Compact athlete demonstration near cue. A beautiful horizontal three-phase rhythm indicator with labels "Подъём", "Удержание", "Опускание", highlight lowering phase in blue. Hide technical clutter; only one correction. Large simple flat planes, humane reassuring intelligent guidance, polished purposeful layout rather than dense dashboard.' },
    @{ id='05-stage'; title='Forma Stage'; direction='Immersive cinematic training stage. Full-bleed large side-view athlete demonstration across 70 percent of canvas, dark neutral real training studio, floor press visible full body and bar. Dedicated opaque dark right sidebar about 25 percent width with giant white 7 / 10, weight and set. Minimal top overlay title on dark scrim with guaranteed contrast, no text over busy subject. Wide slim amplitude progress band above persistent bottom dark control dock, cue "Плавно опускайте". Muted teal accent only. Readable from distance, restrained cinematic atmosphere, no particles or distracting neon, not a video player with playback icons.' }
)
$ledgerPath = Join-Path $root 'ledger.json'
if (Test-Path $ledgerPath) { throw 'Ledger exists. Inspect before resuming to avoid duplicate charges.' }
$ledger = [ordered]@{ model='gpt-image-2.5-flare'; budget_usd=10; reservation_per_request_usd=2; requests=@() }
function Save-Ledger { [IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Depth 12), $utf8) }
Save-Ledger
foreach ($variant in $variants) {
    $prompt = $common + "`nART DIRECTION: " + $variant.direction
    [IO.File]::WriteAllText((Join-Path $root ($variant.id + '-prompt.txt')), $prompt, $utf8)
    $record = [ordered]@{ id=$variant.id; status='reserved'; reserved_usd=2; started_at=[DateTime]::UtcNow.ToString('o'); usage=$null }
    $ledger.requests += $record
    Save-Ledger
    Write-Output ('Generating ' + $variant.id)
    try {
        $body = @{ model=$ledger.model; prompt=$prompt; n=1; size='1536x864'; quality='medium'; output_format='png' } | ConvertTo-Json -Depth 5
        $response = Invoke-RestMethod -Uri 'https://api.openai.com/v1/images/generations' -Method Post -Headers @{ Authorization=('Bearer ' + $key) } -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 600
        if (-not $response.data[0].b64_json) { throw 'No image returned; unknown billing state' }
        [IO.File]::WriteAllBytes((Join-Path $root ($variant.id + '.png')), [Convert]::FromBase64String($response.data[0].b64_json))
        $record.status = 'completed'
        $record.usage = $response.usage
        Save-Ledger
        Write-Output ('Saved ' + $variant.id + '.png')
    } catch {
        $record.status = 'failed_or_unknown'
        Save-Ledger
        $statusCode = 'unknown'
        if ($_.Exception.Response) { $statusCode = [int]$_.Exception.Response.StatusCode }
        Write-Output ('Request stopped. HTTP ' + $statusCode + '. No automatic retries.')
        if ($_.ErrorDetails.Message) {
            try {
                $apiError = $_.ErrorDetails.Message | ConvertFrom-Json
                $safeError = [ordered]@{ status=$statusCode; code=$apiError.error.code; type=$apiError.error.type; message=([string]$apiError.error.message).Replace($key, '[REDACTED]') }
                [IO.File]::WriteAllText((Join-Path $root 'api-error.json'), ($safeError | ConvertTo-Json), $utf8)
                Write-Output ('API error code: ' + $apiError.error.code)
            } catch { Write-Output 'Error details omitted for credential safety.' }
        }
        break
    }
}
$key = $null
Write-Output 'Generation finished. See ledger.json.'