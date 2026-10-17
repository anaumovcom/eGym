# U05 — semantic playback memory (2026-10-17)

## Implemented scope

- Last five playback-started lines, at most 600 characters each, with the actual
  validated author intent, semantic category, playback status and source-record
  fact provenance. Started/interrupted lines explicitly have `fullTextHeard=false`:
  their draft is not represented as fully heard. Failed/unstarted drafts never enter
  heard history. Text-only decisions do not fabricate audio playback.
- Separate metadata-only attempted ledger and started/completed/interrupted ledgers.
  Tips use `(tipId, version)`, not wording or a set-specific topic key. Only natural
  playback completion explains a tip. Interrupted tips may be explained in a later
  opportunity; delayed completion cannot resurrect an interrupted explanation.
- Humor uses `AuthorOutcome.intent`, not trigger T46 or merely allowed intents.
  Two consecutive heard humor lines remove humor from the next request; validation
  also rejects a stale humor request. Category/intent/energy diversity guards apply
  to discretionary humor/support, not necessary factual summaries or reviewed tips.
- Optional single workout motif, only when callbacks are enabled and a safe long-rest
  opportunity actually produces humor containing the offered motif. No introduction
  quota and no fabricated shared biography. At most one callback, only after a
  completed introduction, at least 60 seconds later and in a different rest scope.
- Same-user/same-ledger-run reconnect restores memory, technical event deduplication,
  Director counts, pacing and safety state, not pending events, audio, tasks or ACKs.
  Cache capacity 32 runs, hard 24-hour monotonic TTL without reconnect renewal.
  Each run bounds starts/terminal statuses to 256, completed tip versions to 256,
  attempts/fact mentions/Director count maps to 1024, fingerprints to 64 and
  audible records to 64. Expiry/eviction clears raw conversation data in place.
- `memoryEnabled=true` preserves current-conversation behavior under existing coach
  consent; it is independent of analytics `historyConsent`. Disabling memory saves
  no heard conversation or attempts and sends no conversation memory to the author.
  Technical pacing/safety and event deduplication remain active.
- Separate `crossWorkoutMemory=false` default and explicit settings UI opt-in. The
  cross-run cache contains only four saved enum preferences: style, humor, verbosity,
  praise. No free text, names, biography, feelings or inferred achievements. At most
  128 users; fixed seven-day retention of unchanged metadata, no reconnect renewal.
- Settings withdrawal and DELETE memory clear live sockets, disconnected cached runs,
  motif/callback state and cross-run metadata. In-flight old drafts are invalidated;
  memory revisions prevent author completion after deletion from refilling even the
  attempted ledger. User-switch UI responses are rejected/aborted.

## Limits and consent boundaries

- Both conversation caches are process-local: backend restart/another worker does
  not restore them. There is no new durable memory table, encryption claim or 0013
  migration. Preferences and consent flags use the existing saved preferences schema.
  The deletion response remains `persistentMemory=false` for this reason.
- Achievement memory is intentionally not collected. Current authoritative training
  facts/comparisons still use their existing ownership, provenance and analytics
  consent rules; speech is never promoted into a training fact.
- TTL is checked on store accesses / prompt construction, not by a background timer.
  Expired entries cannot be restored or used as author context on subsequent access.
- Deleting coach memory does not delete analytics results, explicit coach settings,
  billing ledger entries or safety/pacing state. Keeping opt-in enabled permits new
  memory from subsequent activity; disable the separate switch to stop collection.
- These are synthetic offline validations, not acoustic proof that a human heard
  every phoneme. No paid provider, physical hardware, production/user DB, dotenv,
  secrets or migrations were accessed. U06/U07 are not implemented or enabled here.

## Validation

- Offline backend runner: **849 passed, 5 skipped, 9 warnings**; 27 new U05 tests.
- Frontend coach plus explicit feedback and exercise-session screen integration:
  **22 files, 522 passed**. Existing jsdom media-play warnings remain non-failing.
- Scoped Ruff and whitespace checks pass. TypeScript retains **23 known unrelated
  diagnostics**, none in coach/U05 files; whole-project type-check is not green.
- Explicit legacy baseline changes: approved P0/P1/P2 text stays verbatim; prompt
  version moves 0.9 → 0.10 for bounded memory data and safety modules. The old test
  expecting zero clearable memory after socket close now expects the cached run to
  be cleared too. No regression guard was removed to hide failures.