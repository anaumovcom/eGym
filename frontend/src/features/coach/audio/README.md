# NEW E05 local audio core — parent integration API

Core exports are in [index.ts](index.ts); [local-audio-runtime.ts](local-audio-runtime.ts)
adds saved-settings and read-only safety/runtime gates for TEST preview UI.
No automatic count, motor commands, paid dispatch, real voice packs or E08 stream integration.

## Context ownership

- `getSharedAudioContext(): AudioContext | null` — lazy singleton; graceful when
  Web Audio is unavailable. Creating/accessing does **not** resume it.
- `unlockSharedAudioContext(): Promise<boolean>` — call **directly** in a trusted
  click/key handler. Checks browser user activation when available and verifies
  resulting `running` state. No effect/timer unlock, retry, or autoplay fallback.
- Managers never resume, suspend, or close the injected/shared context.

## Manager

`new LocalCoachAudioManager(options?: LocalAudioManagerOptions)`

Options: `context?: AudioContext | null`, `clock?: AudioTimerClock`,
`scope?: CoachScope`, `volume?: number` (0–1, default 1).
`CoachScope` is imported from the existing contracts, not duplicated.
Clock: `now(): number`, `setTimeout(callback, delayMs): unknown`,
`clearTimeout(handle): void`. `now()` and deadlines must use the **same monotonic
time origin** (default `performance.now()`), not Unix timestamps.

- `enqueue(options: PlayLocalOptions): boolean`
- `playLocal(options: PlayLocalOptions): boolean` — equivalent synchronous
  admission APIs. `false` means rejected/cancelled during immediate scheduling;
  `true` means admitted, **not** already started or audible.
- `cancelAll(reason?: AudioReason): void` — default `cancelled`; `AudioReason`
  includes existing `CoachReason` values such as `safety`, `hidden`, `disabled`.
- `cancelScope(scope: CoachScope): void` — exact scope including set/epoch.
- `updateScope(scope: CoachScope): void` — user/run/exercise boundary cancels all;
  same-exercise set/rest/epoch changes preserve started audio, reject old pending.
- `setVolume(volume: number, muted?: boolean): void` — applies volume once at
  master; zero/mute cancels all and rejects admission. Explicit unmute required.
- `snapshot(): LocalAudioSnapshot` — deeply immutable bounded diagnostic value.
- `subscribe(listener: () => void): () => void` — change callback + unsubscribe;
  subscribe then read `snapshot()`. Gains refresh at most every 50ms outside
  lifecycle notifications. Snapshots are value copies, **not** a referentially
  stable `useSyncExternalStore` getter; the parent should store the subscribed
  value in state (or build its own cached adapter).
- `dispose(): void` — idempotent stop/disconnect/timer/subscriber cleanup only.

`PlayLocalOptions`: `id: string` (1–128 chars), `scope: CoachScope`,
`source: 'local' | 'cache'`, `buffer: AudioBuffer`, `startDeadlineMs: number`,
`baseGain: number` (0–1), `delayMs?: number` (0–60000, demo only),
`revalidate: () => boolean` (synchronous, side-effect-free admission/scope check).
Use buffers returned by the fixture/decode APIs below; arbitrary unverified
buffers are rejected. The manager copies and revalidates all samples on admission.
Expired/stale sources are stopped while silent, before gain can be opened.

Snapshot fields: `pending`, `active`, `audible`, `foreground`, `startOrdinal`,
`utterances`, `counters`, `lastActualSource`, `contextState`, `volume`, `muted`,
`reason`, `disposed`, `timeline`. Each utterance has `id`, immutable `scope`,
`source`, `state`, nullable `startOrdinal`, `baseGain`, `coefficient`, computed
current `gain`, `targetGain`, nullable `scheduledStartTime` (audio seconds).
Counters: `enqueued`, `started`, `finished`, `cancelled`, `rejected`.
Timeline: at most 200 `{atMs, reason, startOrdinal, source}` entries, no speech
texts. `audible` is an estimate from running state/envelopes/master settings,
not a measurement of sound at the speaker (a silent clip can still be counted).

### Mixing/timing guarantees

- A scheduled/reserved buffer has gain zero and no ordinal: it never ducks.
- Actual start is **observed** when the running context's audio clock reaches
  `source.start(time)`, with a final deadline/scope/callback check. This is not
  physical playback or output-latency confirmation. A 10ms observer opens the
  initial gain only after validation; delayed/throttled observers may omit the
  initial part of a clip rather than play stale audio.
- Latest observed actual start: coefficient 1. Each of N older started clips:
  `0.65/N`, scaled by its own `baseGain`, never boosted above it.
- Native continuous linear AudioParam ramps: 50ms attack / 150ms restoration;
  native `cancelAndHoldAtTime` or interpolated current-envelope fallback.
- Master `.5 * volume` headroom, then DynamicsCompressor, then destination.
- Only `onended` after an observed start increments `finished`. Deadlines govern
  **starting only**; started audio may finish after its deadline/set transition.
- Limits: 16 pending, 8 scheduled/started sources; 60s, 2,880,000 decoded float
  bytes per utterance; fixed 125s lifetime watchdog. 1024 lifetime IDs, **no
  eviction/replay**. Rejected identified attempts also consume an ID; recreate a
  disposed manager only at a genuinely new parent-owned lifetime/run.
- Count-group semantics and E08 streaming are intentionally not implemented.

## TEST fixtures and preparation

- `FixturePackStorage` implements `LocalFixtureStorage.read(id: TestClipId):
  Promise<Uint8Array<ArrayBuffer>>`. In-memory only.
- `new LocalClipPreparer(context: BaseAudioContext, storage?: LocalFixtureStorage,
  cacheByteLimit?: number)`; `prepare(id: TestClipId): Promise<AudioBuffer>`,
  `clear(): void`, `snapshot(): Readonly<{entries, bytes, inFlight}>`.
- `prepare()` verifies a fixed whitelist and **encoded SHA256 before decode**;
  validates decoded duration/channels/rate (resampling uses the context rate),
  rejects nonfinite samples, normalizes copied peaks to at most .25 without
  amplification. It coalesces decoding and uses a private decoded LRU capped
  at 32MiB. Every caller gets a verified copy; cache data never escapes.
- `createTestClipWav(id: TestClipId): Uint8Array<ArrayBuffer>` and
  `createTestClipBuffer(context: BaseAudioContext, id?: TestClipId): AudioBuffer`
  generate deterministic **TEST tones, not the selected voice**. Default buffer
  ID is `test-sine`; only `test-sine` / `test-chime` exist (250ms, mono 8kHz).
- `LOCAL_FIXTURE_CATALOG`: deeply immutable metadata with IDs, explicit TEST
  labels, encoded sizes, durations, rates, channels, fixed SHA256 hashes.
- Constants: `MAX_DECODED_CACHE_BYTES` (32MiB), `MAX_LOCAL_BUFFER_BYTES`
  (2,880,000), `MAX_LOCAL_DURATION_SECONDS` (60).
- Public types: `AudioReason`, `AudioTimerClock`, `AudioTimelineEvent`,
  `LocalAudioSource`, `LocalAudioSnapshot`, `LocalAudioManagerOptions`,
  `PlayLocalOptions`, `LocalFixtureStorage`, `TestClipId`.

No real packs exist. New real pack manifests require a separate reviewed trust
boundary; this API cannot decode arbitrary filenames/URLs/provider payloads.

## Validation

Vitest uses separate deterministic audio/wall clocks and fake nodes, plus real
SHA256 through a test-only jsdom-to-Node Buffer adapter. The scoped TypeScript
project [tsconfig.tests.json](tsconfig.tests.json) includes tests as well as core.
An isolated frontend-only browser harness additionally checks native
OfflineAudioContext rendering (1/2/3 correlated tones), AudioContext trusted
gesture playback, cancellation, and real header/portal/safety UI. See
[E05 acceptance report](../../../../../plan/13-live-ai-coach-e05-local-audio.md)
and [Playwright config](../../../../playwright.e05.config.ts). No backend or
provider is started. These checks do **not** claim physical speaker delivery,
human listening, real Russian voice intelligibility or inter-sample true peak.