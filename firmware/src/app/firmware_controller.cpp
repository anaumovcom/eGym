#include "firmware_controller.hpp"

#include <Arduino.h>

#include <utility>

namespace egym {

FirmwareController::FirmwareController(FirmwareConfig config)
    : config_(std::move(config)),
      i2c_(config_.hardware),
      inputs_(config_.hardware, i2c_),
      ledOutput_(config_.hardware, i2c_),
      safetyEnable_(config_.hardware),
      usb_(config_.protocol.maximumLineLength),
      buttons_(config_.buttonBehavior),
      sensors_(config_.sensors),
      homing_(config_.homing),
      leds_(config_.led, ledOutput_),
      protocol_(config_.protocol) {}

void FirmwareController::begin() {
    usb_.begin(115200);
    safetyEnable_.begin();
    safetyEnable_.disable();
    bootedAt_ = millis();
    logger_.push(bootedAt_, LogLevel::Info, "system", "firmware_start");

    if (!i2c_.begin()) {
        latchFault(FaultCode::I2cBusFault, bootedAt_, true);
        return;
    }
    inputHealthy_ = inputs_.begin();
    ledHealthy_ = ledOutput_.begin();
    if (!inputHealthy_) {
        latchFault(FaultCode::McpUnavailable, bootedAt_, true);
        return;
    }
    if (!ledHealthy_) {
        latchFault(FaultCode::PcaUnavailable, bootedAt_, false);
        return;
    }
    setState(MachineState::Booting, bootedAt_);
    leds_.play(PatternId::StartupWave, bootedAt_);
    send(protocol_.versionJson());
}

void FirmwareController::send(std::string line) {
    usb_.writeLine(line);
}

void FirmwareController::setState(MachineState state, Millis now) {
    if (state_ == state) return;
    state_ = state;
    leds_.setMachineState(state, now);
    send(protocol_.stateJson(state));
    logger_.push(now, LogLevel::Info, "state", toString(state));
}

void FirmwareController::latchFault(FaultCode fault, Millis now, bool emergency) {
    if (fault_ == fault && stopLatched_) return;
    fault_ = fault;
    stopLatched_ = stopLatched_ || emergency;
    safetyEnable_.disable();
    applyMotion({Direction::Stop, 0.0, true}, now);
    leds_.setEmergency(emergency, now);
    setState(emergency ? MachineState::EmergencyStop : MachineState::Error, now);
    send(protocol_.faultJson(fault, true));
    logger_.push(now, emergency ? LogLevel::Critical : LogLevel::Error, "fault", toString(fault));
}

void FirmwareController::clearEmergency(Millis now) {
    if (!inputHealthy_ || rawButtons_[index(ButtonId::Stop)] || buttons_.pressed(ButtonId::Stop)) return;
    stopLatched_ = false;
    driveFault_ = false;
    fault_ = FaultCode::None;
    sensors_.resetFault();
    leds_.setEmergency(false, now);
    setState(MachineState::Ready, now);
    send(protocol_.faultJson(FaultCode::None, false));
}

void FirmwareController::applyMotion(const MotionRequest& request, Millis now) {
    if (request.stop || stopLatched_ || fault_ != FaultCode::None) {
        safetyEnable_.disable();
    } else {
        safetyEnable_.enable();
    }
    const char* direction = request.direction == Direction::Up ? "up" : (request.direction == Direction::Down ? "down" : "stop");
    onEvent({"motion_request", direction, request.stop ? "stop" : "move", request.speedMmPerSecond, !request.stop});
    logger_.push(now, LogLevel::Debug, "motion", direction);
}

void FirmwareController::onEvent(const CoreEvent& event) {
    const Millis now = millis();
    const auto line = protocol_.eventJson(event);
    if (event.type == "button" && (event.value == "pressed" || event.value == "repeat") && protocol_.connected()) {
        for (std::size_t i = 0; i < kButtonCount; ++i) {
            if (event.id == toString(static_cast<ButtonId>(i))) pendingFeedback_[i] = protocol_.lastTxSequence();
        }
    }
    send(line);
    if (event.type == "button") handleButton(event, now);
}

void FirmwareController::handleButton(const CoreEvent& event, Millis now) {
    ButtonId button = ButtonId::Power;
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        if (event.id == toString(static_cast<ButtonId>(i))) button = static_cast<ButtonId>(i);
    }
    const bool pressed = event.value == "pressed";
    const bool released = event.value == "released";

    if (button == ButtonId::Stop && pressed) {
        latchFault(FaultCode::EmergencyStop, now, true);
        leds_.play(PatternId::StopPressed, now, button);
        return;
    }
    if (released) {
        leds_.setButtonHeld(button, false, now);
    }
    if ((button == ButtonId::LoadPlus || button == ButtonId::LoadMinus) && (pressed || event.value == "repeat")) {
        // The event itself is the requested load step; the PC remains authoritative for load control.
    }
    if (button == ButtonId::Power && pressed) {
        if (!protocol_.connected()) {
            safetyEnable_.disable();
            if (state_ == MachineState::Off) {
                bootedAt_ = now;
                setState(MachineState::Booting, now);
                leds_.play(PatternId::StartupWave, now);
            } else if (!homing_.running() && !stopLatched_ && fault_ == FaultCode::None) {
                leds_.play(PatternId::ShutdownWave, now);
                setState(MachineState::Off, now);
            }
        }
    }
    if (pressed && !protocol_.connected() && button != ButtonId::Power) leds_.play(PatternId::DisabledFeedback, now, button);
}

void FirmwareController::pollInputs(Millis now) {
    if (static_cast<Millis>(now - lastInputPollAt_) < config_.hardware.inputPollMs) return;
    lastInputPollAt_ = now;
    if (!inputs_.read(rawButtons_, rawSensors_)) {
        inputHealthy_ = false;
        safetyEnable_.disable();
        latchFault(FaultCode::McpUnavailable, now, true);
        if (i2c_.recover()) {
            inputHealthy_ = inputs_.begin();
            ledHealthy_ = ledOutput_.begin();
        }
        return;
    }
    inputHealthy_ = true;

    // STOP bypasses debounce for the safety latch. Other button semantics remain debounced.
    if (rawButtons_[index(ButtonId::Stop)] && !stopLatched_) latchFault(FaultCode::EmergencyStop, now, true);
    buttons_.update(rawButtons_, now, *this);
    const FaultCode sensorFault = sensors_.update(rawSensors_, now, positionMm_, *this);
    if (sensorFault != FaultCode::None) latchFault(sensorFault, now, true);
}

MachineState FirmwareController::parseState(const std::string& state) const {
    for (int value = static_cast<int>(MachineState::Off); value <= static_cast<int>(MachineState::Calibration); ++value) {
        const auto candidate = static_cast<MachineState>(value);
        if (state == toString(candidate)) return candidate;
    }
    return state_;
}

void FirmwareController::handleCommand(const ProtocolCommand& command, Millis now) {
    switch (command.type) {
        case CommandType::Ping:
            send(protocol_.pongJson(command.sequence));
            break;
        case CommandType::Heartbeat:
            break;
        case CommandType::Status: {
            std::array<bool, kButtonCount> buttonStates{};
            for (std::size_t i = 0; i < kButtonCount; ++i) {
                buttonStates[i] = buttons_.pressed(static_cast<ButtonId>(i));
            }
            send(protocol_.statusJson(
                state_, fault_, stopLatched_, inputHealthy_, buttonStates, sensors_.snapshot(), positionMm_
            ));
            break;
        }
        case CommandType::Stop:
            latchFault(FaultCode::EmergencyStop, now, true);
            break;
        case CommandType::ClearStop:
            clearEmergency(now);
            break;
        case CommandType::Home: {
            if (stopLatched_ || protocol_.connected()) {
                leds_.play(PatternId::DisabledFeedback, now, ButtonId::StartPause);
                break;
            }
            const auto result = homing_.start(now, positionMm_, sensors_.snapshot(), *this);
            if (result.phase == HomingPhase::Fault || result.phase == HomingPhase::Aborted) {
                latchFault(result.fault, now, true);
                break;
            }
            setState(MachineState::Homing, now);
            leds_.setActivity(Direction::Down, ButtonId::Down, true, now);
            applyMotion(result.motion, now);
            break;
        }
        case CommandType::PositionTelemetry:
            positionMm_ = command.value;
            break;
        case CommandType::DriveFault:
            driveFault_ = command.flag;
            if (driveFault_) latchFault(FaultCode::DriveFault, now, true);
            break;
        case CommandType::Move:
            if (!stopLatched_ && protocol_.connected()) {
                setState(MachineState::Positioning, now);
                onEvent({"move_target", "bar", "position_mm", command.value, true});
            }
            break;
        case CommandType::Start:
            if (!stopLatched_) setState(MachineState::ExerciseActive, now);
            break;
        case CommandType::Pause:
            if (!stopLatched_) setState(MachineState::Paused, now);
            break;
        case CommandType::SetMachineState:
            if (!stopLatched_) {
                const MachineState next = parseState(command.text);
                if (next == MachineState::SetComplete) leds_.play(PatternId::SetCompleteEffect, now);
                if (next == MachineState::Off && state_ != MachineState::Off) leds_.play(PatternId::ShutdownWave, now);
                if (state_ == MachineState::Off && next != MachineState::Off) leds_.play(PatternId::StartupWave, now);
                setState(next, now);
            }
            break;
        case CommandType::ButtonFeedback:
            for (std::size_t i = 0; i < kButtonCount; ++i) {
                if (command.text != toString(static_cast<ButtonId>(i)) || pendingFeedback_[i] != command.requestSequence) continue;
                pendingFeedback_[i] = 0;
                const auto button = static_cast<ButtonId>(i);
                if (!command.flag) {
                    leds_.setButtonHeld(button, false, now);
                    leds_.play(PatternId::DisabledFeedback, now, button);
                } else if (button != ButtonId::Power && button != ButtonId::Stop) {
                    if (rawButtons_[i] && (button == ButtonId::Up || button == ButtonId::Down)) leds_.setButtonHeld(button, true, now);
                    if (button == ButtonId::Camera) leds_.play(PatternId::CameraShutter, now, button);
                    else if (button == ButtonId::Ok) leds_.play(PatternId::OkDoublePulse, now, button);
                    else if (button == ButtonId::Fail) leds_.play(PatternId::FailPulse, now, button);
                    else if (button != ButtonId::Up && button != ButtonId::Down) leds_.play(PatternId::ButtonPress, now, button);
                }
            }
            break;
        case CommandType::SetActivity:
            if (!stopLatched_) {
                const Direction direction = command.text == "up" ? Direction::Up : (command.text == "down" ? Direction::Down : Direction::Stop);
                leds_.setActivity(direction, direction == Direction::Down ? ButtonId::Down : ButtonId::Up, direction != Direction::Stop, now);
            }
            break;
        case CommandType::PlayEffect:
            if (!stopLatched_) {
                if (command.text == "home_detected") leds_.play(PatternId::HomeDetected, now);
                else if (command.text == "homing_complete") leds_.play(PatternId::HomingComplete, now);
                else if (command.text == "target_reached") leds_.play(PatternId::TargetReached, now);
                else if (command.text == "limit_triggered") leds_.play(PatternId::LimitTriggered, now);
                else if (command.text == "set_complete") leds_.play(PatternId::SetCompleteEffect, now);
            }
            break;
        case CommandType::SetBrightness:
            if (command.value >= 0.1 && command.value <= 1.0) leds_.setBrightness(static_cast<float>(command.value));
            break;
        case CommandType::LedTest:
            leds_.play(PatternId::LedSelfTest, now);
            break;
        case CommandType::InputTest:
            leds_.play(PatternId::ButtonSelfTest, now);
            for (std::size_t i = 0; i < kButtonCount; ++i) onEvent({"diagnostic_input", toString(static_cast<ButtonId>(i)), "button", 0.0, rawButtons_[i]});
            for (std::size_t i = 0; i < kSensorCount; ++i) onEvent({"diagnostic_input", toString(static_cast<SensorId>(i)), "sensor", 0.0, sensors_.snapshot().active[i]});
            break;
        case CommandType::I2cTest:
            send(protocol_.diagnosticJson("mcp23017", inputs_.healthy(), inputs_.healthy() ? "detected" : "unavailable"));
            send(protocol_.diagnosticJson("pca9685", ledOutput_.healthy(), ledOutput_.healthy() ? "detected" : "unavailable"));
            break;
        case CommandType::Diagnostics:
            runDiagnostics(now);
            break;
        case CommandType::SetNightMode:
            leds_.setNightMode(command.flag);
            break;
        case CommandType::FirmwareInfo:
            send(protocol_.versionJson());
            break;
        case CommandType::SetLoad:
            onEvent({"load_request", "load", "kg", command.value, true});
            break;
        case CommandType::Invalid:
            break;
    }
}

void FirmwareController::pollUsb(Millis now) {
    usb_.poll();
    std::string line;
    while (usb_.readLine(line)) {
        const ParseResult result = protocol_.parse(line, now);
        if (!result.ok) {
            send(protocol_.faultJson(FaultCode::ProtocolError, false));
            logger_.push(now, LogLevel::Warning, "protocol", result.error);
        } else if (!result.duplicate) {
            handleCommand(result.command, now);
        }
    }

    const bool connected = protocol_.updateHeartbeat(now);
    if (previousProtocolConnected_ && !connected) {
        pendingFeedback_.fill(0);
        for (std::size_t i = 0; i < kButtonCount; ++i) leds_.setButtonHeld(static_cast<ButtonId>(i), false, now);
        leds_.setActivity(Direction::Stop, ButtonId::Up, false, now);
        safetyEnable_.disable();
        applyMotion({Direction::Stop, 0.0, true}, now);
        if (homing_.running() || state_ == MachineState::Positioning || state_ == MachineState::ExerciseActive) {
            latchFault(FaultCode::HeartbeatTimeout, now, true);
        } else {
            setState(MachineState::Warning, now);
            leds_.play(PatternId::UsbDisconnected, now);
        }
    } else if (!previousProtocolConnected_ && connected) {
        leds_.play(PatternId::UsbConnected, now);
    }
    previousProtocolConnected_ = connected;
}

void FirmwareController::runDiagnostics(Millis now) {
    send(protocol_.diagnosticJson("usb", usb_.connected(), usb_.connected() ? "connected" : "not_enumerated"));
    send(protocol_.diagnosticJson("mcp23017", inputs_.healthy(), inputs_.healthy() ? "detected" : "unavailable"));
    send(protocol_.diagnosticJson("pca9685", ledOutput_.healthy(), ledOutput_.healthy() ? "detected" : "unavailable"));
    send(protocol_.diagnosticJson("i2c", inputs_.healthy() && ledOutput_.healthy(), "recoveries=" + std::to_string(i2c_.recoveryCount())));
    leds_.play(PatternId::LedSelfTest, now);
}

void FirmwareController::flushLogs() {
    LogRecord record;
    if (!logger_.pop(record)) return;
    onEvent({"log", record.component, std::string(toString(record.level)) + ":" + record.message, static_cast<double>(record.timestamp), false});
}

void FirmwareController::tick() {
    const Millis now = millis();
    pollInputs(now);
    pollUsb(now);

    if (state_ == MachineState::Booting && !protocol_.connected() && static_cast<Millis>(now - bootedAt_) >= config_.led.startupWaveMs && fault_ == FaultCode::None) {
        leds_.play(PatternId::StartupComplete, now);
        setState(MachineState::Ready, now);
    }

    if (homing_.running()) {
        const auto update = homing_.update(now, positionMm_, sensors_.snapshot(), stopLatched_, driveFault_, *this);
        if (update.changed) {
            applyMotion(update.motion, now);
            if (update.phase == HomingPhase::BottomBackoff || update.phase == HomingPhase::TopBackoff) leds_.play(PatternId::HomeDetected, now);
            if (update.phase == HomingPhase::Complete) {
                leds_.setActivity(Direction::Stop, ButtonId::Power, false, now);
                leds_.play(PatternId::HomingComplete, now);
                setState(MachineState::Ready, now);
                send(protocol_.positionJson(homing_.result()));
            } else if (update.phase == HomingPhase::Fault || update.phase == HomingPhase::Aborted) {
                latchFault(update.fault, now, true);
            } else {
                const Direction direction = update.motion.direction;
                leds_.setActivity(direction, direction == Direction::Up ? ButtonId::Up : ButtonId::Down, !update.motion.stop, now);
            }
        }
    }

    if (!leds_.update(now) && ledHealthy_) {
        ledHealthy_ = false;
        safetyEnable_.disable();
        latchFault(FaultCode::PcaUnavailable, now, false);
    }
    if (static_cast<Millis>(now - lastStatusAt_) >= config_.protocol.statusIntervalMs) {
        lastStatusAt_ = now;
        send(protocol_.positionJson(homing_.result().known ? homing_.result() : PositionResult{false, 0, 0, 0, 0, 0, positionMm_}));
    }
    flushLogs();
}

}  // namespace egym
