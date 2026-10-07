# E08 — streaming voice и выбор моделей/голосов

**Дата:** 07.10.2026. **Статус:** offline-часть готова (E08.2–E08.4); E08.1 реализован, но не проверен на реальном аккаунте;
E08.5–E08.7 и E08.G заблокированы платным pilot и прослушиванием.

## Что сделано

| Пункт | Реализация | Проверка |
|---|---|---|
| E08.1 (код) | [voice.py](../backend/app/services/coach/voice.py): единый `VoiceCapability`; `TtsVoiceAdapter` (streaming PCM, verbatim input) и `RealtimeVoiceAdapter` (out-of-band `response.create`, `conversation:"none"`, только audio, usage из `response.done`); prompts §7 дословно (`coach-voice-0.3`); repr без ключа, URL whitelist; `voice_pricing` = unverified, TTS без enforceable bounds | MockTransport/FakeSocket, verbatim prompts |
| E08.2 | Wire `ECA1 \| u32 header \| JSON CoachAudio \| PCM s16le`: Python `encode_frame/decode_frame/PcmFramer`, TS [coach-frames.ts](../frontend/src/features/coach/audio/coach-frames.ts) (`CoachFrameReader` не зависит от сетевого chunking); bounds 4 KiB header / 96 000 B frame / 60 s stream; `VoiceStreamer`: reserve→dispatch→settle, first-audio timeout 5 s, watchdog 60 s без продления пакетами, cancel/aclose → unsettled | golden frame Python→TS, byte-by-byte split, truncated, codec/duration |
| E08.3 | [local-coach-audio-manager.ts](../frontend/src/features/coach/audio/local-coach-audio-manager.ts) `beginStream/pushStream/cancelStream`: reservation и prebuffer 120 мс не duck; chunks back-to-back на audio clock и не дают нового start; чужой `generationId`/scope/отменённый id → `stale`; sequence/codec/rate/length → `invalid`; gap > 250 мс → коэффициент 0, фон восстанавливается, `underrun` в timeline; stall 5 s и watchdog 60 s от первого старта; [network-stream.ts](../frontend/src/features/coach/audio/network-stream.ts) `playCoachStream` требует final frame | [local-coach-stream.test.ts](../frontend/src/features/coach/audio/local-coach-stream.test.ts) |
| E08.4 | `verify_transcript`: `mode=post-factum-transcript` для realtime, `verbatim-input` для TTS, `prevents_audible_error=False` всегда; числа сравниваются отдельно; `route_voice`: factual speech только в verified verbatim path, иначе `None` (local/silence) | transcript/routing tests |

Новые настройки в [config.py](../backend/app/core/config.py): `COACH_VOICE_REALTIME_MODEL=gpt-realtime-2.1-mini`,
`COACH_VOICE_TTS_MODEL=gpt-4o-mini-tts`, `COACH_VOICE_PRICING_VERSION=plan-0.3-unverified`. Все capability `verified=False`,
поэтому factual-путь сейчас не маршрутизируется в сеть, а `reserve` для голоса даёт `strict_cap_unprovable`.

## Проверки

- Backend: [test_coach_e08_voice.py](../backend/app/tests/test_coach_e08_voice.py) — 19 PASS, включён в `backend/scripts/check_coach_e02.py`; Ruff PASS.
- Frontend: [coach-frames.test.ts](../frontend/src/features/coach/audio/coach-frames.test.ts), [local-coach-stream.test.ts](../frontend/src/features/coach/audio/local-coach-stream.test.ts);
  набор Coach/shell/session/summary — **283 PASS** (было 270); `tsc` — 23 ошибки baseline, в Coach 0.
- 0 paid-запросов, 0 hardware-команд; Coach не импортирует motor/hardware API.

## Блокировки

- **E08.1 (проверка):** реальные model IDs, voices, цены и доступ аккаунта не проверены — нужен ключ в vault. Код adapters готов.
- **E08.5 paid voice pilot:** нет ключа и подтверждённой цены; `ledger.dispatch` для голоса остаётся fail-closed
  (non-test dispatch разрешён только `luna-text`). Pilot-скрипт не создавался, чтобы не открывать платный путь без проверенной цены.
- **E08.6–E08.7, E08.G:** A/B и выбор голоса требуют прослушивания пользователем. До этого E09 не генерирует окончательные пакеты.
