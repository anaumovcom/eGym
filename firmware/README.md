# eGym ESP32-S3 panel firmware

Production-oriented PlatformIO/Arduino firmware for the eGym Smith-machine panel. It reads 10 momentary buttons and four paired limit/home sensors through MCP23017, drives ten button LEDs through PCA9685, retains a standalone diagnostic homing implementation, and exchanges JSON Lines over native USB CDC.

## Safety boundary

> **WARNING — this firmware is not a safety-rated controller.** A physical emergency-stop circuit must remove torque through a certified drive STO/contactor path independently of ESP32, USB, I²C, firmware, and the PC. The momentary panel STOP is software-latched, but it is not a substitute for hardware E-stop/STO.

The optional active-low `safetyEnablePin` is a fail-safe auxiliary enable output. It defaults disabled at boot, on STOP, heartbeat loss during motion, sensor mismatch, homing/drive fault, MCP loss, and I²C failure. It is still not safety-rated. While a PC session is active, the backend `MotionController` is the sole owner of machine state and drive homing: firmware buttons emit momentary events and display feedback after backend confirmation. POWER, START/PAUSE, UP and DOWN never locally enable motion or toggle exercise state. Without a PC, POWER only changes the panel's visual standby state and leaves auxiliary enable disabled.

Electrical requirements:

- TL-W5MC1 variants commonly use industrial supply/output levels that are **not ESP32/MCP23017-compatible**. Use correctly designed level conversion or opto-isolation, common-reference and surge protection appropriate to the exact NPN/PNP/NO/NC sensor variant. Never connect a 6–36 V sensor output directly to MCP23017.
- MCP23017 and PCA9685 logic must use the board's 3.3 V-compatible I²C domain with pull-ups to the correct rail. Confirm module pull-ups; many breakout boards pull to their VCC.
- PCA9685 outputs are signal/PWM outputs, not lamp power outputs. Drive every button lamp through a suitably rated logic-level MOSFET/current driver, with flyback protection for inductive loads and a separate fused lamp supply where required.
- Define safe power-up/down behavior in external hardware. ESP32 reset, bootloader mode, crashed firmware, disconnected USB, and stuck I²C must not energize motion.

## Architecture

The code is split intentionally:

- `src/core`: portable C++17 state machines and algorithms; no Arduino headers.
- `src/hal`: Arduino adapters for Wire, MCP23017, PCA9685, USB CDC, and auxiliary safety enable.
- `src/app`: orchestration and policy; translates HAL samples and USB commands into core operations.
- `test`: Unity host tests built by PlatformIO's `native` environment.

Core features:

- 5 ms MCP polling, per-button debounce, `pressed`, `released`, `long_press`, and `repeat` events.
- UP/DOWN hold movement events; LOAD +/- repeat accelerates after a configurable hold time.
- six-row panel geometry independent of PWM channel order.
- gamma-corrected logical brightness to PCA9685 PWM 0..4095.
- non-blocking base/activity/priority-overlay LED layers (`safety > diagnostics > button feedback > decorative`) with emergency override and automatic overlay restoration.
- OFF, BOOTING, HOMING, READY, POSITIONING, EXERCISE_ACTIVE, PAUSED, SET_COMPLETE, WARNING, ERROR, EMERGENCY_STOP, MAINTENANCE, and CALIBRATION indication.
- startup/shutdown row waves, press/release behavior, disabled feedback, direction/hold activity, camera/OK/FAIL/STOP/limit feedback, USB feedback, LED/button self-test.
- debounced paired bottom/top sensing with time and distance windows, invalid-combination detection, pair events, mismatch faults, and homing backoff release checks.
- coarse/controlled-creep/backoff/fine two-pass homing at both boundaries. A boundary is accepted only when both sensors in its pair are active. Results contain physical limits, offset working limits, travel, and known/current position.
- bounded JSON Lines input, protocol version and monotonic sequence handling, duplicate suppression, ping/pong, heartbeat watchdog, and typed events.
- bounded non-blocking structured log queue.
- I²C probing, nine-clock/STOP bus recovery, device reinitialization, and fail-safe behavior.

The drive electrical interface was not specified. Production backend **does not execute** firmware `motion_request` events: it owns drive motion and two-pass homing through `MotionController`/`DriveAdapter` and sends measured position to the panel. Firmware `motion_request` is diagnostic-only. The real Modbus drive adapter remains a safe nonfunctional stub until its register map and hardware braking/STO are validated. No software here replaces an independent hardware STO path.

## Default wiring and configuration

Edit `FirmwareConfig` construction or its fields before creating `FirmwareController`; core logic never refers to fixed hardware channels.

Default I²C: SDA GPIO 8, SCL GPIO 9, 400 kHz; MCP23017 `0x20`; PCA9685 `0x40`, 1 kHz.

| Logical input | MCP pin | Default polarity |
|---|---:|---|
| POWER, UP, DOWN, LOAD+, LOAD-, START/PAUSE, CAMERA, OK | GPA0..GPA7 | active-low, pull-up |
| FAIL, STOP | GPB0..GPB1 | active-low, pull-up |
| LEFT_BOTTOM, RIGHT_BOTTOM, LEFT_TOP, RIGHT_TOP | GPB2..GPB5 | active-low, pull-up |
| reserve | GPB6..GPB7 | unused |

LEDs POWER through STOP map to PCA9685 channels 0..9. Every mapping has an inversion flag and per-channel gain. Logical geometry is fixed independently:

```text
              POWER                 row 0 / center
       UP              DOWN         row 1 / left,right
       LOAD+           LOAD-        row 2 / left,right
       START           CAMERA       row 3 / left,right
       OK              FAIL         row 4 / left,right
              STOP                  row 5 / center
```

Configurable groups include pins/addresses/polarities, poll/PWM rate, debounce and repeat timing, gamma/global/night brightness, animation timing, pair time/distance/timeout windows, homing speeds/backoff/timeouts/search distance and top/bottom offsets.

## Homing contract

Production homing belongs exclusively to backend `MotionController`, which consumes the four fresh panel sensor states and commands the drive adapter directly. The backend never sends firmware `home`. Firmware's two-pass implementation is retained for bench diagnostics, not production drive operation, and is refused during a heartbeat-controlled PC session. Position is unknown after boot and every aborted/faulted diagnostic home.

The backend panel bridge is disabled by default. Install the backend's optional `panel` dependency (pyserial), set `HARDWARE_PANEL_ENABLED=true` and `HARDWARE_PANEL_PORT=COMx` (or the appropriate `/dev/ttyACM*` path), then start the backend. `HARDWARE_PANEL_BAUD` defaults to `115200`. The backend requires a full `status` snapshot and an identity event before accepting panel input. A stalled/unplugged connection during movement stops the backend, and motion is blocked until a fresh, healthy panel handshake. `HARDWARE_PANEL_RX_WATCHDOG_SECONDS` and the heartbeat/reconnect/status intervals can be configured in backend settings. Releasing STOP does not release its latch: the backend waits for firmware acknowledgement before clearing the emergency state.

Panel illumination is configured on the backend with `HARDWARE_PANEL_NIGHT_MODE` (default `false`) and `HARDWARE_PANEL_BRIGHTNESS` (0.1–1.0, default 1.0); the bridge replays both after every handshake. The UI's brightness selector is currently display-only and does not set these hardware options. Emergency LEDs ignore these brightness reductions.

At either boundary, the first side changes coarse motion to controlled creep. If the other side does not arrive inside both configured time and distance windows, motion stops and a side-specific stuck/pair fault is latched. Backoff must release both sensors before fine approach. STOP and drive faults abort every phase.

## JSON Lines protocol v1

One UTF-8 JSON object per line (`\n`), maximum 768 bytes by default. Every PC command contains `v`, a nonempty process-session ID, monotonically increasing `seq`, and `cmd`. A changed session resets firmware RX sequencing so a restarted backend can begin again at sequence 1. Retransmitted/old sequence numbers within one session are acknowledged by parsing but ignored. Events contain firmware-generated `seq`. An overlong physical line is discarded in full through its newline; no JSON-looking tail is executed.

Handshake and heartbeat (send heartbeat faster than the default 1500 ms timeout):

```json
{"v":1,"seq":1,"session":"backend-a1","cmd":"ping"}
{"v":1,"seq":2,"session":"backend-a1","cmd":"heartbeat"}
{"v":1,"seq":3,"session":"backend-a1","cmd":"status"}
```

Typical commands:

```json
{"v":1,"seq":4,"session":"backend-a1","cmd":"position","position_mm":428.3}
{"v":1,"seq":5,"session":"backend-a1","cmd":"move","position_mm":350.0}
{"v":1,"seq":6,"session":"backend-a1","cmd":"set_load","kg":45.0}
{"v":1,"seq":7,"session":"backend-a1","cmd":"start"}
{"v":1,"seq":8,"session":"backend-a1","cmd":"pause"}
{"v":1,"seq":9,"session":"backend-a1","cmd":"stop"}
{"v":1,"seq":10,"session":"backend-a1","cmd":"clear_stop"}
{"v":1,"seq":11,"session":"backend-a1","cmd":"set_machine_state","state":"ready"}
{"v":1,"seq":12,"session":"backend-a1","cmd":"set_night_mode","enabled":true}
{"v":1,"seq":13,"session":"backend-a1","cmd":"drive_fault","enabled":true}
{"v":1,"seq":14,"session":"backend-a1","cmd":"button_feedback","id":"up","request_seq":4,"accepted":false}
{"v":1,"seq":15,"session":"backend-a1","cmd":"set_activity","direction":"down"}
{"v":1,"seq":16,"session":"backend-a1","cmd":"play_effect","effect":"homing_complete"}
{"v":1,"seq":17,"session":"backend-a1","cmd":"set_brightness","brightness":0.4}
```

STOP remains latched after release and can only be cleared explicitly while the physical STOP input is inactive. Commands cannot clear a real external STO circuit.

`button_feedback.request_seq` is the firmware sequence of the original pressed/repeat event; responses to older presses/repeats are ignored, while a quick tap still receives its result after release. Only accepted actions get a success animation. `set_activity` reflects measured motion (`up`, `down`, `stop`) and does not command the drive. `play_effect` accepts `home_detected`, `homing_complete`, `target_reached`, `limit_triggered`, and `set_complete`; effects survive ordinary periodic state sync and are cancelled by a fault or emergency. A completed set returns to the persistent PAUSED state after its temporary effect.

Diagnostics:

```json
{"v":1,"seq":20,"session":"backend-a1","cmd":"firmware_info"}
{"v":1,"seq":21,"session":"backend-a1","cmd":"input_test"}
{"v":1,"seq":22,"session":"backend-a1","cmd":"led_test"}
{"v":1,"seq":23,"session":"backend-a1","cmd":"i2c_test"}
{"v":1,"seq":24,"session":"backend-a1","cmd":"diagnostics"}
```

Representative events:

```json
{"v":1,"seq":1,"type":"version","firmware":"egym-panel-controller","version":"1.0.0","protocol":1}
{"v":1,"seq":2,"type":"pong","request_seq":1,"firmware":"1.0.0"}
{"v":1,"seq":3,"type":"status","firmware":"egym-panel-controller","version":"1.0.0","protocol":1,"machine_state":"ready","fault":"none","stop_latched":false,"input_healthy":true,"buttons":{"power":false,"up":false,"down":false,"load_plus":false,"load_minus":false,"start_pause":false,"camera":false,"ok":false,"fail":false,"stop":false},"sensors":{"left_bottom":false,"right_bottom":false,"left_top":false,"right_top":false},"bottom_pair":false,"top_pair":false,"position_mm":428.3}
{"v":1,"seq":4,"type":"button","id":"load_plus","event":"pressed","value":0.0,"active":true}
{"v":1,"seq":5,"type":"sensor","id":"left_bottom","event":"active","value":0.0,"active":true}
{"v":1,"seq":6,"type":"pair","id":"bottom","event":"confirmed","value":48.2,"active":true}
{"v":1,"seq":7,"type":"motion_request","id":"down","event":"move","value":8.0,"active":true}
{"v":1,"seq":8,"type":"fault","code":"bottom_sensor_mismatch","latched":true}
{"v":1,"seq":9,"type":"machine_state","state":"ready"}
{"v":1,"seq":10,"type":"position","known":true,"mm":985.0,"physical_bottom_mm":50.0,"physical_top_mm":990.0,"working_bottom_mm":55.0,"working_top_mm":985.0,"travel_mm":930.0}
{"v":1,"seq":11,"type":"diagnostic","subsystem":"mcp23017","ok":true,"detail":"detected"}
```

Heartbeat loss always disables the auxiliary enable and requests stop. Loss during homing, positioning, or exercise latches `heartbeat_timeout` and EMERGENCY_STOP. When idle it enters WARNING.

## Build, test, upload, monitor

From this directory:

```text
pio test -e native
pio run -e esp32s3
pio run -e esp32s3 -t upload
pio device monitor -b 115200
```

Use `pio run -e esp32s3 -t clean` after changing framework/toolchain versions. The selected board is `esp32-s3-devkitc-1`; change only the board identifier and pin configuration when using another ESP32-S3 module.

## Test coverage

Host tests cover debounce/bounce rejection, long press and accelerated repeat, pair confirmation and time/distance mismatch, invalid sensor combinations, complete two-boundary two-pass homing, pair fault, backoff release failure and STOP abort, gamma endpoints, physical geometry, symmetric row wave, LED layer restoration/emergency priority, JSON parsing/version/sequence idempotence, event encoding, ping/pong, and heartbeat expiry.

Hardware-in-loop acceptance must additionally verify polarity, every input/LED mapping, sensor timing under real mechanics, MOSFET thermal/current margins, I²C fault injection, USB unplug during every motion phase, reset/brownout behavior, independent STO, and measured stopping distance before operation with a person.
