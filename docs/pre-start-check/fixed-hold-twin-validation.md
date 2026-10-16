# Fixed / isometric hold: twin-only validation, 2026-10-16

## Status: NOT approved for hanging a person

The experimental fixed-force replacement has been **reverted**, not qualified as a fix.
Only narrow PI antiwindup safeguards remain. This is **not a safe suspension system**.
No hardware verification, live API calls, drive commands, calibration writes or database writes
were performed. Soft HOLD / start grip and down/up training laws are unchanged.

## Controller and limits

Fixed/isometric again uses the TRUE original HEAD PI: original spring, damping,
friction compensation, integral gain and clamps. `fixed_integral` is the accumulated
position-error correction in N, not an actual-torque observer. There is no permanent
leak, new return-force cap, velocity cap, or observer history. No new tuning knobs.

The PI candidate is rejected when it would push the FULL shaped output farther into
force, slew, soft-position or raw-torque saturation (including asymmetric pull scale).
Unwinding out of saturation is allowed. Missing, old, duplicate and out-of-order
sample timestamps freeze integration; a fresh timestamp allows it again. Leaving
fixed/isometric clears the integral. Existing force/rate envelopes and ESTOP support
behavior remain in force; none were raised. Plain soft HOLD is unchanged.

The original damping bound is deliberately retained in this fallback. A tested
candidate using full bus + torque lag, a 150 N/s integral growth bound and velocity
bleed did not improve sag and release speed across the matrix. Those changes were
NOT shipped: reducing overshoot alone while increasing peak speed is insufficient.
H1/C1 calibration is not a certification for holding body weight.

## Reproduction and results

Pure TwinBench, x=700 mm, reflected mass 60 kg/side; dt=75 ms,
command delay=2 ticks, torque lag=48 ms; mechanical coupling=4.5 N/mm,
read delay=0 and 1 ticks; profile Ku=1.2264 N/mm,
Tu=0.537 s, loop delay=73.5 ms. Force ramps from t=1 s at -150 N/s
to -300 N/side, stays until t=9 s, then becomes zero abruptly. Run length 25 s.

Baseline is the entire original `MotorCore` executed in an in-memory module from
`git show HEAD:backend/app/motor/core.py`, HEAD at evaluation:
`bca88b938c721501af9841a2f906faf790c47f4d`. Tests pin that commit so future HEAD
movement cannot silently redefine the baseline. No working-tree replacement or stash.

| Metric | Original PI, read 0 | Fallback, read 0 | Original PI, read 1 | Fallback, read 1 |
| --- | ---: | ---: | ---: | ---: |
| Maximum sag | 532.975 mm | identical | 564.629 mm | identical |
| Overshoot above target after release | 575.423 mm | identical | 630.118 mm | identical |
| Peak speed after release | 580.236 mm/s | identical | 698.312 mm/s | identical |
| Tail oscillation (last 40 samples) | 16.838 mm | identical | 186.905 mm | identical |
| Final error at 25 s | 56.470 mm | identical | 93.455 mm | identical |

These are **bad original dynamics**, preserved rather than misrepresented as fixed.
The earlier 518/576/603 probe used a different default mass; it is not the mass-60
matched baseline above. The incoming leaky replacement measured 77.081/83.520/583.944
at read 0, and 134.534/109.029/638.330 at read 1 (sag/overshoot/speed): smaller travel
but worse read-0 speed and permanent loaded error. It is NOT the baseline and is removed.

Tests require exact equality of every force, position and velocity sample against
the original for all 12 combinations: read 0/1, coupling 4.5/40, load 300/300,
300/200 and 200/300 N. Continued hanging for 120 s is also compared at read 0/1;
no claim of settled precision is made. Additional tests exercise full-output
saturation, allowed unwinding, stale timestamps, soft HOLD isolation, transitions,
and ESTOP support. An unholdable 1000 N/side overload reaches the lower stop while
the force remains bounded; this must NOT be described as a successful hold or an
overspeed fault when no such fault occurred.

Validation: 450 pure motor tests passed, including workout; a separate HOLD +
workout run passed 53 tests. Seven API/database cases were excluded from the
isolated motor run because their `client`/`db_session` fixtures require the parent
application setup. No claim is made that those integration cases were validated.

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