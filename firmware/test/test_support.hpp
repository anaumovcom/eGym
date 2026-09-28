#pragma once

#include "core/interfaces.hpp"

#include <array>
#include <vector>

struct EventCollector final : egym::IEventSink {
    std::vector<egym::CoreEvent> events;
    void onEvent(const egym::CoreEvent& event) override { events.push_back(event); }
};

struct LedCollector final : egym::ILedOutput {
    std::array<std::uint16_t, egym::kButtonCount> last{};
    bool fail{false};
    bool write(const std::array<std::uint16_t, egym::kButtonCount>& pwm) override {
        last = pwm;
        return !fail;
    }
    void allOff() override { last.fill(0); }
};

inline egym::SensorSnapshot sensors(bool leftBottom, bool rightBottom, bool leftTop, bool rightTop) {
    return {{{leftBottom, rightBottom, leftTop, rightTop}}};
}
