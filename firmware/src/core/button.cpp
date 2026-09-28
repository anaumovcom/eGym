#include "button.hpp"

namespace egym {
namespace {

bool elapsed(Millis now, Millis since, Millis duration) {
    return static_cast<Millis>(now - since) >= duration;
}

}  // namespace

DebouncedButton::DebouncedButton(ButtonId id, ButtonBehavior behavior) {
    configure(id, behavior);
}

void DebouncedButton::configure(ButtonId id, ButtonBehavior behavior) {
    id_ = id;
    behavior_ = behavior;
}

void DebouncedButton::emit(ButtonEventType type, IEventSink& sink) const {
    sink.onEvent({"button", toString(id_), toString(type), 0.0, stableActive_});
}

void DebouncedButton::update(bool rawActive, Millis now, IEventSink& sink) {
    if (rawActive != rawActive_) {
        rawActive_ = rawActive;
        rawChangedAt_ = now;
    }

    if (rawActive_ != stableActive_ && elapsed(now, rawChangedAt_, behavior_.debounceMs)) {
        stableActive_ = rawActive_;
        if (stableActive_) {
            pressedAt_ = now;
            nextRepeatAt_ = now + behavior_.repeatDelayMs;
            longPressSent_ = false;
            emit(ButtonEventType::Pressed, sink);
        } else {
            emit(ButtonEventType::Released, sink);
            longPressSent_ = false;
        }
    }

    if (!stableActive_) {
        return;
    }

    if (!longPressSent_ && elapsed(now, pressedAt_, behavior_.longPressMs)) {
        longPressSent_ = true;
        emit(ButtonEventType::LongPress, sink);
    }

    if (behavior_.repeat && static_cast<std::int32_t>(now - nextRepeatAt_) >= 0) {
        emit(ButtonEventType::Repeat, sink);
        const bool accelerated = elapsed(now, pressedAt_, behavior_.accelerationAfterMs);
        nextRepeatAt_ = now + (accelerated ? behavior_.acceleratedIntervalMs : behavior_.repeatIntervalMs);
    }
}

ButtonBank::ButtonBank(const std::array<ButtonBehavior, kButtonCount>& behavior) {
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        buttons_[i].configure(static_cast<ButtonId>(i), behavior[i]);
    }
}

void ButtonBank::update(const std::array<bool, kButtonCount>& raw, Millis now, IEventSink& sink) {
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        buttons_[i].update(raw[i], now, sink);
    }
}

}  // namespace egym
