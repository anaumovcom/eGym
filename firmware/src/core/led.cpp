#include "led.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace egym {
namespace {

constexpr float kPi = 3.14159265358979323846F;
constexpr float kTransparent = -1.0F;

float clamp(float value) {
    return std::max(0.0F, std::min(1.0F, value));
}

std::uint8_t overlayPriority(PatternId pattern) {
    switch (pattern) {
        case PatternId::StopPressed:
        case PatternId::LimitTriggered:
            return 3;
        case PatternId::StartupWave:
        case PatternId::ShutdownWave:
        case PatternId::SetCompleteEffect:
        case PatternId::LedSelfTest:
        case PatternId::ButtonSelfTest:
        case PatternId::SensorDiagnostic:
            return 2;
        case PatternId::ButtonPress:
        case PatternId::DisabledFeedback:
        case PatternId::HomeDetected:
        case PatternId::HomingComplete:
        case PatternId::TargetReached:
        case PatternId::CameraShutter:
        case PatternId::OkDoublePulse:
        case PatternId::FailPulse:
            return 1;
        default:
            return 0;
    }
}

}  // namespace

std::uint16_t GammaCorrector::toPwm(float brightness) const {
    const float corrected = std::pow(clamp(brightness), gamma_);
    return static_cast<std::uint16_t>(std::lround(corrected * 4095.0F));
}

LedEngine::LedEngine(LedConfig config, ILedOutput& output)
    : config_(config), output_(output), gamma_(config.gamma) {}

void LedEngine::setMachineState(MachineState state, Millis now) {
    if (state_ == state) return;
    state_ = state;
    stateStartedAt_ = now;
    if (state == MachineState::Error) {
        overlay_.active = false;
    }
    if (state == MachineState::EmergencyStop) {
        setEmergency(true, now);
    } else if (emergency_) {
        setEmergency(false, now);
    }
}

void LedEngine::setActivity(Direction direction, ButtonId focus, bool active, Millis now) {
    if (activityDirection_ == direction && activityFocus_ == focus && activityActive_ == active) return;
    activityDirection_ = direction;
    activityFocus_ = focus;
    activityActive_ = active;
    activityStartedAt_ = now;
}

void LedEngine::setButtonHeld(ButtonId button, bool held, Millis now) {
    if (held_[index(button)] == held) return;
    held_[index(button)] = held;
    if (held) activityStartedAt_ = now;
}

Millis LedEngine::patternDuration(PatternId pattern) const {
    switch (pattern) {
        case PatternId::StartupWave: return config_.startupWaveMs;
        case PatternId::ShutdownWave: return config_.shutdownWaveMs;
        case PatternId::ButtonPress: return config_.pressDurationMs;
        case PatternId::DisabledFeedback: return config_.disabledDurationMs;
        case PatternId::SetCompleteEffect: return 1500;
        case PatternId::HomingComplete: return 650;
        case PatternId::LedSelfTest: return 7600;
        case PatternId::ButtonSelfTest: return std::numeric_limits<Millis>::max();
        case PatternId::SensorDiagnostic: return std::numeric_limits<Millis>::max();
        case PatternId::CameraShutter: return 340;
        case PatternId::OkDoublePulse: return 650;
        case PatternId::FailPulse: return 700;
        case PatternId::StopPressed: return 400;
        case PatternId::LimitTriggered: return 650;
        default: return 450;
    }
}

void LedEngine::play(PatternId pattern, Millis now, ButtonId target) {
    if (emergency_ || state_ == MachineState::Error || state_ == MachineState::EmergencyStop) return;
    const Millis duration = patternDuration(pattern);
    if (overlay_.active && static_cast<Millis>(now - overlay_.startedAt) >= overlay_.duration) {
        overlay_.active = false;
    }
    const std::uint8_t priority = overlayPriority(pattern);
    if (overlay_.active && priority < overlay_.priority) return;
    overlay_ = {pattern, target, now, duration, priority, pattern != PatternId::None};
}

void LedEngine::setEmergency(bool active, Millis now) {
    emergency_ = active;
    emergencyStartedAt_ = now;
    if (active) {
        overlay_.active = false;
    }
}

float LedEngine::breathe(Millis now, Millis period, float low, float high) {
    if (period == 0) return high;
    const float phase = static_cast<float>(now % period) / static_cast<float>(period);
    const float wave = (1.0F - std::cos(2.0F * kPi * phase)) * 0.5F;
    return low + (high - low) * wave;
}

float LedEngine::pulse(Millis elapsedMs, Millis duration, float low, float high) {
    if (duration == 0 || elapsedMs >= duration) return low;
    const float phase = static_cast<float>(elapsedMs) / static_cast<float>(duration);
    if (phase < 0.25F) {
        return low + (high - low) * (phase / 0.25F);
    }
    const float decay = (phase - 0.25F) / 0.75F;
    return high + (low - high) * decay;
}

BrightnessFrame LedEngine::transparentFrame() {
    BrightnessFrame result{};
    result.fill(kTransparent);
    return result;
}

void LedEngine::apply(BrightnessFrame& destination, const BrightnessFrame& layer) {
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        if (layer[i] >= 0.0F) destination[i] = clamp(layer[i]);
    }
}

BrightnessFrame LedEngine::baseFrame(Millis now) const {
    BrightnessFrame frame{};
    switch (state_) {
        case MachineState::Off:
            frame[index(ButtonId::Power)] = breathe(now, 3500, 0.04F, 0.08F);
            frame[index(ButtonId::Stop)] = 0.03F;
            break;
        case MachineState::Booting:
            frame.fill(0.10F); frame[index(ButtonId::Power)] = 0.45F; frame[index(ButtonId::Stop)] = 0.30F;
            break;
        case MachineState::Homing:
            frame.fill(0.07F); frame[index(ButtonId::Power)] = 0.30F; frame[index(ButtonId::StartPause)] = 0.10F; frame[index(ButtonId::Stop)] = 0.35F;
            break;
        case MachineState::Ready:
            frame = {0.40F, 0.30F, 0.30F, 0.35F, 0.35F, 0.60F, 0.20F, 0.20F, 0.10F, 0.30F};
            break;
        case MachineState::Positioning:
            frame = {0.30F, 0.15F, 0.15F, 0.12F, 0.12F, 0.20F, 0.10F, 0.10F, 0.08F, 0.40F};
            break;
        case MachineState::ExerciseActive:
            frame = {0.30F, 0.15F, 0.15F, 0.30F, 0.30F, breathe(now, 1800, 0.35F, 1.0F), 0.20F, 0.15F, 0.10F, 0.40F};
            break;
        case MachineState::Paused:
            frame = {0.25F, 0.10F, 0.10F, 0.15F, 0.15F, breathe(now, 2300, 0.20F, 0.60F), 0.15F, 0.20F, 0.20F, 0.35F};
            break;
        case MachineState::SetComplete:
            frame = {0.35F, 0.20F, 0.20F, 0.20F, 0.20F, 0.35F, 0.15F, breathe(now, 900, 0.30F, 0.80F), 0.10F, 0.30F};
            break;
        case MachineState::Warning:
            frame.fill(0.10F); frame[index(ButtonId::Fail)] = breathe(now, 2500, 0.15F, 0.55F); frame[index(ButtonId::Stop)] = 0.45F;
            break;
        case MachineState::Error:
            frame.fill(0.05F); frame[index(ButtonId::Power)] = 0.20F; frame[index(ButtonId::Fail)] = breathe(now, 850, 0.20F, 1.0F); frame[index(ButtonId::Stop)] = 0.60F;
            break;
        case MachineState::EmergencyStop:
            break;
        case MachineState::Maintenance:
            frame.fill(0.08F); frame[index(ButtonId::Power)] = breathe(now, 1800, 0.20F, 0.60F); frame[index(ButtonId::Camera)] = breathe(now + 900, 1800, 0.20F, 0.60F); frame[index(ButtonId::Stop)] = 0.40F;
            break;
        case MachineState::Calibration:
            frame.fill(0.10F); frame[index(ButtonId::Up)] = 0.50F; frame[index(ButtonId::Down)] = 0.50F; frame[index(ButtonId::Ok)] = 0.60F; frame[index(ButtonId::Stop)] = 0.35F;
            break;
    }
    return frame;
}

BrightnessFrame LedEngine::activityFrame(Millis now) const {
    auto frame = transparentFrame();
    if (activityActive_) {
        const float active = breathe(now - activityStartedAt_, state_ == MachineState::Positioning ? 1200 : 650, 0.35F, 1.0F);
        if (activityDirection_ == Direction::Up) {
            frame[index(ButtonId::Up)] = active;
            frame[index(ButtonId::Down)] = 0.10F;
        } else if (activityDirection_ == Direction::Down) {
            frame[index(ButtonId::Down)] = active;
            frame[index(ButtonId::Up)] = 0.10F;
        } else {
            frame[index(activityFocus_)] = active;
        }
    }
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        if (held_[i]) frame[i] = breathe(now - activityStartedAt_, 650, 0.50F, 1.0F);
    }
    return frame;
}

BrightnessFrame LedEngine::overlayFrame(Millis now, bool& finished) const {
    auto frame = transparentFrame();
    finished = false;
    if (!overlay_.active) return frame;
    const Millis elapsedMs = now - overlay_.startedAt;
    finished = elapsedMs >= overlay_.duration;
    if (finished) return frame;

    switch (overlay_.pattern) {
        case PatternId::StartupWave:
        case PatternId::ShutdownWave: {
            const bool reverse = overlay_.pattern == PatternId::ShutdownWave;
            const Millis slot = std::max<Millis>(1, overlay_.duration / kPanelRows);
            const std::uint8_t activeRow = std::min<std::uint8_t>(kPanelRows - 1, static_cast<std::uint8_t>(elapsedMs / slot));
            for (std::size_t i = 0; i < kButtonCount; ++i) {
                const std::uint8_t row = reverse ? static_cast<std::uint8_t>(kPanelRows - 1 - kPanelGeometry[i].row) : kPanelGeometry[i].row;
                frame[i] = row == activeRow ? pulse(elapsedMs % slot, slot, reverse ? 0.0F : 0.20F, reverse ? 0.40F : 1.0F) : (row < activeRow ? (reverse ? 0.0F : 0.20F) : 0.08F);
            }
            break;
        }
        case PatternId::ButtonPress:
            frame[index(overlay_.target)] = pulse(elapsedMs, overlay_.duration, 0.55F, 1.0F);
            break;
        case PatternId::DisabledFeedback:
            frame[index(overlay_.target)] = pulse(elapsedMs, overlay_.duration, 0.05F, 0.50F);
            frame[index(ButtonId::Fail)] = pulse(elapsedMs, overlay_.duration, 0.10F, 0.80F);
            break;
        case PatternId::CameraShutter:
            frame[index(ButtonId::Camera)] = elapsedMs < 100 ? 1.0F : (elapsedMs < 210 ? 0.15F : 0.70F);
            break;
        case PatternId::OkDoublePulse:
        case PatternId::HomingComplete:
            frame[index(ButtonId::Ok)] = ((elapsedMs / 250U) % 2U == 0U) ? pulse(elapsedMs % 250U, 250, 0.20F, 1.0F) : 0.20F;
            break;
        case PatternId::SetCompleteEffect:
            frame.fill(0.12F);
            frame[index(ButtonId::Ok)] = breathe(elapsedMs, 500, 0.40F, 1.0F);
            frame[index(ButtonId::StartPause)] = 0.60F;
            break;
        case PatternId::FailPulse:
            frame[index(ButtonId::Fail)] = ((elapsedMs / 170U) % 2U == 0U) ? 1.0F : 0.20F;
            break;
        case PatternId::StopPressed:
            frame.fill(0.07F); frame[index(ButtonId::Stop)] = 1.0F;
            break;
        case PatternId::LimitTriggered:
            frame.fill(0.05F); frame[index(ButtonId::Stop)] = 1.0F; frame[index(ButtonId::Fail)] = ((elapsedMs / 120U) % 2U == 0U) ? 1.0F : 0.15F;
            break;
        case PatternId::HomeDetected:
        case PatternId::TargetReached:
            frame[index(ButtonId::Ok)] = pulse(elapsedMs, overlay_.duration, 0.20F, 1.0F);
            break;
        case PatternId::UsbConnected:
            frame[index(ButtonId::Power)] = pulse(elapsedMs, overlay_.duration, 0.30F, 0.70F);
            frame[index(ButtonId::Camera)] = pulse(elapsedMs, overlay_.duration, 0.20F, 0.60F);
            break;
        case PatternId::UsbDisconnected:
            frame[index(ButtonId::Fail)] = pulse(elapsedMs, overlay_.duration, 0.10F, 0.40F);
            break;
        case PatternId::PcActivity:
            frame[index(ButtonId::Camera)] = pulse(elapsedMs, 60, 0.20F, 0.35F);
            break;
        case PatternId::LedSelfTest: {
            const Millis perLed = 600;
            if (elapsedMs < perLed * kButtonCount) {
                const std::size_t led = std::min<std::size_t>(kButtonCount - 1, elapsedMs / perLed);
                frame.fill(0.0F);
                frame[led] = pulse(elapsedMs % perLed, perLed, 0.0F, 1.0F);
            } else {
                const Millis allElapsed = elapsedMs - perLed * kButtonCount;
                frame.fill(allElapsed < 300 ? 0.20F : (allElapsed < 600 ? 0.50F : (allElapsed < 900 ? 1.0F : 0.0F)));
            }
            break;
        }
        case PatternId::ButtonSelfTest:
            for (std::size_t i = 0; i < kButtonCount; ++i) frame[i] = held_[i] ? 1.0F : 0.10F;
            break;
        case PatternId::StartupComplete:
            frame.fill(pulse(elapsedMs, overlay_.duration, 0.20F, 0.50F));
            break;
        default:
            frame[index(overlay_.target)] = pulse(elapsedMs, overlay_.duration, 0.20F, 1.0F);
            break;
    }
    return frame;
}

BrightnessFrame LedEngine::emergencyFrame(Millis now) const {
    BrightnessFrame frame{};
    frame.fill(0.02F);
    const bool high = ((now - emergencyStartedAt_) % config_.emergencyPeriodMs) < (config_.emergencyPeriodMs / 2U);
    frame[index(ButtonId::Stop)] = high ? 1.0F : 0.20F;
    frame[index(ButtonId::Fail)] = high ? 0.75F : 0.25F;
    return frame;
}

void LedEngine::compose(Millis now) {
    composed_ = baseFrame(now);
    if (state_ != MachineState::Error && state_ != MachineState::EmergencyStop) {
        apply(composed_, activityFrame(now));
    }
    bool finished = false;
    apply(composed_, overlayFrame(now, finished));
    if (finished) overlay_.active = false;
    if (emergency_) composed_ = emergencyFrame(now);

    const float scale = emergency_ ? 1.0F : config_.globalBrightness * brightness_ * (nightMode_ ? config_.nightScale : 1.0F);
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        pwm_[i] = gamma_.toPwm(composed_[i] * scale);
    }
}

bool LedEngine::update(Millis now) {
    if (static_cast<Millis>(now - lastFrameAt_) < config_.frameIntervalMs) return true;
    lastFrameAt_ = now;
    compose(now);
    return output_.write(pwm_);
}

}  // namespace egym
