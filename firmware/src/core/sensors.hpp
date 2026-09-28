#pragma once

#include "config.hpp"
#include "interfaces.hpp"

#include <array>

namespace egym {

class DebouncedSignal {
public:
    bool update(bool raw, Millis now, Millis debounceMs);
    bool active() const { return stable_; }
    Millis activeSince() const { return activeSince_; }

private:
    bool raw_{false};
    bool stable_{false};
    Millis changedAt_{0};
    Millis activeSince_{0};
};

class SensorMonitor {
public:
    explicit SensorMonitor(SensorConfig config);

    FaultCode update(const SensorSnapshot& raw, Millis now, double positionMm, IEventSink& sink);
    const SensorSnapshot& snapshot() const { return stable_; }
    void resetFault() { fault_ = FaultCode::None; }

private:
    struct PairTracker {
        bool waiting{false};
        bool pairReported{false};
        Millis firstAt{0};
        double firstPosition{0.0};
        SensorId first{SensorId::LeftBottom};
    };

    FaultCode updatePair(bool top, Millis now, double positionMm, IEventSink& sink);
    FaultCode checkStuck(Millis now);
    void emitSensorEdges(const SensorSnapshot& previous, IEventSink& sink);

    SensorConfig config_{};
    std::array<DebouncedSignal, kSensorCount> signals_{};
    SensorSnapshot stable_{};
    std::array<bool, kSensorCount> stuckReported_{};
    PairTracker bottom_{};
    PairTracker top_{};
    FaultCode fault_{FaultCode::None};
};

FaultCode missingSensorFault(bool top, const SensorSnapshot& sensors);

}  // namespace egym
