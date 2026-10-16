# Fixed / isometric hold: twin-only validation, 2026-10-16

## Status: NOT approved for hanging a person

The slow PI integral was replaced by a momentum disturbance observer (DOB). The DOB
reacts in about 0.17 s, where the integral took about 1 s or longer (Ti ≈ 1.07 s).
This was validated **only on the twin**. No hardware verification, live API calls,
drive commands, calibration writes or database writes were performed. Soft HOLD,
start grip and the down/up training laws are unchanged. This is **not a safe
suspension system**.

## Root cause

The spring stiffness can't be raised: with 60 kg of reflected mass and a 73.5 ms loop
delay, the hold is already near its stability margin. The original PI integral built
up the user's force over ≈ 1 s, so the bar sagged by more than 0.5 m before the
integral caught up. On release the integral then pushed the bar up by more than 0.5 m.

## Controller

`fixed_integral` is an estimate of the user's force, computed from the bar's momentum
(`MotorCore._observe_fixed`):

```
applied = command(t − loop_delay), filtered through torque_lag   # from command history
needed  = mean(applied) − gravity − ripple − friction(v) − m·Δv/dt
bias   += (needed − bias) · (1 − exp(−dt / FIXED_OBSERVER_S))     # τ = 0.17 s
```

The bias is added to the original spring and damping law. Neither the stiffness nor
the force envelope was raised.

- **Fresh frames only.** Missing, duplicate, stale and out-of-order timestamps freeze
  the bias. The first fresh frame only primes the observer.
- **Saturation.** The bias never grows deeper into the saturation of the full shaped
  output (force, slew, soft position, raw torque, asymmetric pull); it may only unwind.
  It is clamped to ±envelope max force. Leaving fixed/isometric clears it.
- **Still deadband.** When the bar is still (|v| < 1 mm/s) and within
  `FIXED_STILL_DEADBAND_MM` = 6 mm of the target, the bias is not updated. Without
  the deadband, static friction caused stick-slip hunting (±7 mm, ~13 s period) at
  read delay 1.
- τ = 0.13 s already rings. Slower values of τ sag more and hunt.
- Using the measured drive torque (PA_1C4) as the observer's force input performed
  worse in the twin and was rejected.

## Reproduction and results

Pure TwinBench setup:
- x = 700 mm, reflected mass 60 kg/side, dt = 75 ms
- command delay 2 ticks, torque lag 48 ms, mechanical coupling 4.5 N/mm
- read delay 0 and 1 ticks
- profile Ku = 1.2264 N/mm, Tu = 0.537 s, loop delay 73.5 ms

The load ramps from t = 1 s at −150 N/s to −300 N/side, holds until t = 9 s, then drops
to zero abruptly. Run length is 25 s. The baseline is the original `MotorCore` from
commit `bca88b938c721501af9841a2f906faf790c47f4d`, run in memory.

| Metric | Original PI, read 0 | Observer, read 0 | Original PI, read 1 | Observer, read 1 |
| --- | ---: | ---: | ---: | ---: |
| Maximum sag | 533 mm | 85.5 mm | 565 mm | 127.7 mm |
| Overshoot after release | 575 mm | 219 mm | 630 mm | 241.5 mm |
| Peak speed after release | 580 mm/s | 617 mm/s | 698 mm/s | 635 mm/s |
| Tail oscillation | 16.8 mm | 0 | 186.9 mm | 0 |
| Final error at 25 s | 56.5 mm | 5.0 mm | 93.5 mm | 5.7 mm |

The release impulse is physical: torque is stored across the bus delay and torque lag.
The observer does not remove it. At read delay 1 with an asymmetric 300/200 N load,
peak release speed is 692 mm/s against 591 mm/s for the original, so the tests allow
up to 1.25× the original.

Robustness matrix, all with tail oscillation < 10 mm and final error < 8 mm:

| Case | Sag (mm) |
| --- | ---: |
| mass 45 kg | 98 |
| mass 80 kg | 95 |
| mass 80 kg, read delay 1 | 133 |
| stiction +30 N | 108 |
| command delay 3 ticks | 128 |
| command delay 1 tick | 75 |
| Coulomb friction 30/80 N | 86 |
| position noise 0.3 mm | 86 |
| load 500/500 N | 116 |

Fast hanging ramps of 1000–3000 N/s still sag 262–269 mm, and 415 mm at read delay 1.
In these cases the drive is at the 700 N envelope limit, so the sag is a force limit,
not an observer limit.

Tests in `backend/app/tests/motor/test_fixed_hold.py`:
- **Observer vs. original PI.** 12 combinations: read delay 0/1, coupling 4.5/40,
  loads 300/300, 300/200 and 200/300 N. Pass criteria:
  - sag < 140 mm and < 1/3 of the original
  - overshoot < 260 mm and < 1/2 of the original
  - release speed < 1.25× the original
  - tail oscillation < 10 mm and final error < 8 mm
- **Continued hanging for 120 s at read delay 0/1.** The settled range must be < 10 mm
  and the final error < 8 mm.
- **Plant-mismatch robustness.** Mass, stiction and command-delay variations.
- **Other cases:**
  - saturation (no deeper, only unwinding) and stale timestamps
  - soft HOLD isolation, transitions and ESTOP support
  - an unholdable overload that stays force-bounded

Validation: 503 pure motor tests passed.

## Physical limitation and unloaded-first checks

A controller without an independent load measurement cannot detect a sudden disappearance
of a static load before motion starts. The old torque remains active through sampling,
queued commands and current lag; changing gains or discharging an integral after detection
cannot undo that impulse. Force/speed commands are not a mechanical brake, and ESTOP
support torque is not guaranteed to support an additional hanging load.

1. Keep human access below/around the bar excluded. Provide rated mechanical catches,
   restraint and a verified independent stop path before any bench experiment.
2. Start **unloaded**, low in travel with adequate stop clearance. Verify signs, encoder,
   actual-torque scale, timestamps, measured delay/jitter and support/ESTOP behavior.
3. Verify no self-motion in soft HOLD and fixed/isometric transitions; then loss-of-frame,
   write-failure and saturation behavior, without bypassing any existing interlock.
4. Only under an approved engineering test procedure use small restrained inert reference
   weights, progressively checking asymmetric force and release with independent telemetry.
   Never use a hanging person as a calibration load or as the release test.
5. Reject the setup if displacement/speed exceed the approved risk-assessment limits.
   Do not raise the force envelope to hide sag. A personnel-safe fixed hold requires
   independently assessed mechanical restraint and/or suitably rated force/brake sensing.