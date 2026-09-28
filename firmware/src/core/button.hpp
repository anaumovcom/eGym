#pragma once

#include "config.hpp"
#include "interfaces.hpp"

#include <array>

namespace egym {

class DebouncedButton {
public:
    DebouncedButton() = default;
    DebouncedButton(ButtonId id, ButtonBehavior behavior);

    void configure(ButtonId id, ButtonBehavior behavior);
    void update(bool rawActive, Millis now, IEventSink& sink);
    bool pressed() const { return stableActive_; }

private:
    void emit(ButtonEventType type, IEventSink& sink) const;

    ButtonId id_{ButtonId::Power};
    ButtonBehavior behavior_{};
    bool rawActive_{false};
    bool stableActive_{false};
    bool longPressSent_{false};
    Millis rawChangedAt_{0};
    Millis pressedAt_{0};
    Millis nextRepeatAt_{0};
};

class ButtonBank {
public:
    explicit ButtonBank(const std::array<ButtonBehavior, kButtonCount>& behavior);
    void update(const std::array<bool, kButtonCount>& raw, Millis now, IEventSink& sink);
    bool pressed(ButtonId id) const { return buttons_[index(id)].pressed(); }

private:
    std::array<DebouncedButton, kButtonCount> buttons_{};
};

}  // namespace egym
