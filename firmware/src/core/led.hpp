#pragma once

#include "config.hpp"
#include "interfaces.hpp"

#include <array>
#include <cstdint>

namespace egym {

using BrightnessFrame = std::array<float, kButtonCount>;

class GammaCorrector {
public:
    explicit GammaCorrector(float gamma = 2.2F) : gamma_(gamma) {}
    std::uint16_t toPwm(float brightness) const;

private:
    float gamma_;
};

class LedEngine {
public:
    LedEngine(LedConfig config, ILedOutput& output);

    void setMachineState(MachineState state, Millis now);
    void setActivity(Direction direction, ButtonId focus, bool active, Millis now);
    void play(PatternId pattern, Millis now, ButtonId target = ButtonId::Power);
    void setButtonHeld(ButtonId button, bool held, Millis now);
    void setNightMode(bool enabled) { nightMode_ = enabled; }
    void setBrightness(float brightness) { brightness_ = brightness; }
    void setEmergency(bool active, Millis now);
    bool update(Millis now);

    const BrightnessFrame& logicalFrame() const { return composed_; }
    const std::array<std::uint16_t, kButtonCount>& pwmFrame() const { return pwm_; }

private:
    struct Layer {
        PatternId pattern{PatternId::None};
        ButtonId target{ButtonId::Power};
        Millis startedAt{0};
        Millis duration{0};
        std::uint8_t priority{0};
        bool active{false};
    };

    BrightnessFrame baseFrame(Millis now) const;
    BrightnessFrame activityFrame(Millis now) const;
    BrightnessFrame overlayFrame(Millis now, bool& finished) const;
    BrightnessFrame emergencyFrame(Millis now) const;
    void compose(Millis now);
    static float breathe(Millis now, Millis period, float low, float high);
    static float pulse(Millis elapsedMs, Millis duration, float low, float high);
    static BrightnessFrame transparentFrame();
    static void apply(BrightnessFrame& destination, const BrightnessFrame& layer);
    Millis patternDuration(PatternId pattern) const;

    LedConfig config_{};
    ILedOutput& output_;
    GammaCorrector gamma_;
    MachineState state_{MachineState::Off};
    Millis stateStartedAt_{0};
    bool activityActive_{false};
    Direction activityDirection_{Direction::Stop};
    ButtonId activityFocus_{ButtonId::Power};
    Millis activityStartedAt_{0};
    std::array<bool, kButtonCount> held_{};
    Layer overlay_{};
    bool emergency_{false};
    Millis emergencyStartedAt_{0};
    bool nightMode_{false};
    float brightness_{1.0F};
    Millis lastFrameAt_{0};
    BrightnessFrame composed_{};
    std::array<std::uint16_t, kButtonCount> pwm_{};
};

}  // namespace egym
