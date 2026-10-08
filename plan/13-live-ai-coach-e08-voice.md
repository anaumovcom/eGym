# E08 — streaming voice и выбор моделей/голосов

**Дата:** 07.10.2026, pilot 08.10.2026. **Статус:** E08.1–E08.6 готовы (проверено на реальном аккаунте);
E08.7 и E08.G ждут прослушивания и выбора голосов пользователем.

## Что сделано

| Пункт | Реализация | Проверка |
|---|---|---|
| E08.1 (код) | [voice.py](../backend/app/services/coach/voice.py): единый `VoiceCapability`; `TtsVoiceAdapter` (streaming PCM, verbatim input) и `RealtimeVoiceAdapter` (out-of-band `response.create`, `conversation:"none"`, только audio, usage из `response.done`); prompts §7 дословно (`coach-voice-0.5`, твёрдая подача и низкое начало фразы D-E08.8/D-E08.9); repr без ключа, URL whitelist; `voice_pricing` — официальные ставки 08.10.2026, `verified` = переключатель оператора; usage: Realtime из `response.done`, TTS из SSE `speech.audio.done` | MockTransport/FakeSocket, verbatim prompts, реальный аккаунт |
| E08.2 | Wire `ECA1 \| u32 header \| JSON CoachAudio \| PCM s16le`: Python `encode_frame/decode_frame/PcmFramer`, TS [coach-frames.ts](../frontend/src/features/coach/audio/coach-frames.ts) (`CoachFrameReader` не зависит от сетевого chunking); bounds 4 KiB header / 96 000 B frame / 60 s stream; `VoiceStreamer`: reserve→dispatch→settle, first-audio timeout 5 s, watchdog 60 s без продления пакетами, cancel/aclose → unsettled | golden frame Python→TS, byte-by-byte split, truncated, codec/duration |
| E08.3 | [local-coach-audio-manager.ts](../frontend/src/features/coach/audio/local-coach-audio-manager.ts) `beginStream/pushStream/cancelStream`: reservation и prebuffer 120 мс не duck; chunks back-to-back на audio clock и не дают нового start; чужой `generationId`/scope/отменённый id → `stale`; sequence/codec/rate/length → `invalid`; gap > 250 мс → коэффициент 0, фон восстанавливается, `underrun` в timeline; stall 5 s и watchdog 60 s от первого старта; [network-stream.ts](../frontend/src/features/coach/audio/network-stream.ts) `playCoachStream` требует final frame | [local-coach-stream.test.ts](../frontend/src/features/coach/audio/local-coach-stream.test.ts) |
| E08.4 | `verify_transcript`: `mode=post-factum-transcript` для realtime, `verbatim-input` для TTS, `prevents_audible_error=False` всегда; числа сравниваются отдельно; `route_voice`: factual speech только в verified verbatim path, иначе `None` (local/silence) | transcript/routing tests |

Новые настройки в [config.py](../backend/app/core/config.py): `COACH_VOICE_REALTIME_MODEL=gpt-realtime-2.1-mini`,
`COACH_VOICE_TTS_MODEL=gpt-4o-mini-tts`, `COACH_VOICE_PRICING_VERSION=openai-2026-10-08` (цены сверены с официальной
страницей 08.10.2026), `COACH_VOICE_REALTIME_REASONING_EFFORT` (по умолчанию не задан, см. ниже). Платный голос включается
только парой `COACH_PAID_VOICE_ENABLED` + `COACH_VOICE_PRICING_VERIFIED` и ключом в vault; по умолчанию всё выключено.

## Paid pilot (E08.1/E08.5/E08.6, 08.10.2026)

Запуски через `backend/scripts/coach_pilot.py {voice|ab} --confirm-paid --cap-usd X` (sandbox-БД вне репозитория,
отчёты `backend/coach_packs/pilot/<kind>-<ts>/report.json` + WAV, в git не попадают).

| Запуск | Что | Итог |
|---|---|---|
| `voice-20261008-011613` | 6 фраз × marin/cedar × realtime/tts | 24/24 complete, $0.039; realtime: first audio ≈1.4 s, transcript 12/12 |
| `ab-20261008-011726` | 30 фраз × 2 голоса × 2 адаптера, холодный socket на фразу | $0.187; см. таблицу ниже |
| probe `/tmp/rt_variants.py` | один тёплый socket, 3 варианта × 8 фраз | connect 0,83 s; warm first audio 0,47–0,65 s; 24/24 дословно |
| `ab-20261008-012832/-012903` | realtime, тёплая сессия, `effort=minimal` | marin 22/22, cedar 30/30 дословно; медиана 552/515 ms |
| `ab-20261008-013605` | итоговая конфигурация (warm, effort не задан, `max_output_tokens`) | marin 27/27 дословно, медиана 676 ms; $0.042 |

A/B (холодный socket, `ab-20261008-011726`):

| Адаптер/голос | Дословно | First audio медиана | Цена за секунду звука |
|---|---|---|---|
| realtime marin | 29/30 | 1380 ms | 453 µUSD |
| realtime cedar | 29/30 | 1406 ms | 601 µUSD |
| tts marin | verbatim input | 586 ms | 329 µUSD |
| tts cedar | verbatim input | 585 ms | 330 µUSD |

### Выводы

1. **TTS-модели закрываются 06.01.2027** (`tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`); официальная замена —
   `gpt-realtime-2.1-mini`. Поэтому основной путь — Realtime; TTS годится для A/B и пакетов до этой даты.
2. **Холодная задержка Realtime — это сетевое подключение, а не модель.** WebSocket handshake ≈0,8 s; на тёплом socket
   first audio 0,5–0,7 s, на уровне TTS. Реализовано: `RealtimeVoiceAdapter(keep_alive=True)` — одна сессия на
   последовательные ответы, `asyncio.Lock`, сброс socket при любой ошибке/отмене (отменённый ответ не попадёт в следующий),
   обновление до лимита 60 мин (`MAX_SESSION_S=55 мин`), одна переподключка, если сервер закрыл простаивающий socket
   (запрос не был отправлен), транспортные ошибки → `provider_connect`/`provider_disconnected`.
3. **Дословность.** В холодном A/B оба промаха на фразе «Двадцать один повтор…»: marin перефразировал, cedar добавил
   преамбулу «Сейчас прочитаю текст.». В тёплых прогонах 79/79 дословно. Дополнительное правило «без вступления» эффекта
   не дало — промпт §7 не менялся. Transcript gate остаётся: для пакетов он отклоняет клип, для live — только post-factum.
4. **`reasoning.effort=minimal`** принимается, экономит ≈12 reasoning tokens, задержку почти не меняет, но в
   `response.done` тогда приходит `input_tokens: 0` при реальном вводе (≈130 tokens). Поэтому по умолчанию effort не
   задаётся, а `parse_realtime_usage` при нулевом text input возвращает `PartialUsage` (попытка остаётся обязательством,
   а не «бесплатной»). Прогоны 012832/012903 из-за этого недоучли ≈80 µUSD на фразу.
5. **cedar дороже marin на ≈20 %:** в каждом ответе cedar есть скрытые 160 audio input tokens (128 cached), у marin — 0.
6. **Резерв был в 45 раз больше факта** (60 s звука ≈ $0.068 на любую фразу при факте ≈ $0.0015). Теперь
   `speech_ms_bound(text) = min(60 s, 3 s + 160 ms/символ)` (замер ≈75 ms/символ, запас ×2): резерв ≈ $0.01.
   Граница обеспечена: Realtime получает `max_output_tokens` = bound (сервер сам остановит ответ), `VoiceStreamer`
   обрывает поток с `audio_overrun`, если звука больше границы; пакеты передают `max_output_tokens` из `clip_bounds`.

## Проверки

- Backend: [test_coach_e08_voice.py](../backend/app/tests/test_coach_e08_voice.py) — keep-alive, сброс при ошибке/отмене/
  возрасте, переподключение, транспортные ошибки, `max_output_tokens`, `audio_overrun`, нулевой input usage;
  safe runner **382 PASS**; Ruff PASS.
- Frontend: набор Coach/shell/session/summary — 296 PASS; `tsc` — 23 ошибки baseline, в Coach 0.
- 0 hardware-команд; Coach не импортирует motor/hardware API.

## Осталось

- **E08.7 / E08.G:** прослушать `backend/coach_packs/pilot/ab-20261008-011726/listen-*.wav` и выбрать женский/мужской
  голос (кандидаты marin / cedar) и адаптер для пакетов.
- Live factual speech: `route_voice` пускает факты только в verbatim-путь (TTS). После 06.01.2027 факты остаются за
  локальными клипами/locked clause либо требуют решения принять Realtime с post-factum transcript.
- Production: ключ только из vault, флаги paid по умолчанию выключены.
