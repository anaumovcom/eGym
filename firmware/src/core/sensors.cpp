#include "sensors.hpp"

#include <cmath>

namespace egym {
namespace {

bool elapsed(Millis now, Millis since, Millis duration) {
    return static_cast<Millis>(now - since) >= duration;
}

}  // namespace

bool DebouncedSignal::update(bool raw, Millis now, Millis debounceMs) {
    if (raw != raw_) {
        raw_ = raw;
        changedAt_ = now;
    }
    if (stable_ != raw_ && elapsed(now, changedAt_, debounceMs)) {
        stable_ = raw_;
        if (stable_) {
            activeSince_ = now;
        }
        return true;
    }
    return false;
}

SensorMonitor::SensorMonitor(SensorConfig config) : config_(config) {}

void SensorMonitor::emitSensorEdges(const SensorSnapshot& previous, IEventSink& sink) {
    for (std::size_t i = 0; i < kSensorCount; ++i) {
        if (previous.active[i] != stable_.active[i]) {
            sink.onEvent({"sensor", toString(static_cast<SensorId>(i)), stable_.active[i] ? "active" : "inactive", 0.0, stable_.active[i]});
        }
    }
}

FaultCode SensorMonitor::updatePair(bool top, Millis now, double positionMm, IEventSink& sink) {
    const SensorId leftId = top ? SensorId::LeftTop : SensorId::LeftBottom;
    const SensorId rightId = top ? SensorId::RightTop : SensorId::RightBottom;
    const bool left = stable_.get(leftId);
    const bool right = stable_.get(rightId);
    PairTracker& tracker = top ? top_ : bottom_;

    if (!left && !right) {
        tracker = {};
        return FaultCode::None;
    }

    if (left && right) {
        if (tracker.waiting) {
            const bool timeOk = !elapsed(now, tracker.firstAt, config_.pairTimeWindowMs + 1U);
            const bool distanceOk = std::abs(positionMm - tracker.firstPosition) <= config_.pairDistanceWindowMm;
            if (!timeOk || !distanceOk) {
                return top ? FaultCode::TopSensorMismatch : FaultCode::BottomSensorMismatch;
            }
        }
        if (!tracker.pairReported) {
            tracker.pairReported = true;
            sink.onEvent({"pair", top ? "top" : "bottom", "confirmed", positionMm, true});
        }
        tracker.waiting = false;
        return FaultCode::None;
    }

    if (!tracker.waiting) {
        tracker.waiting = true;
        tracker.firstAt = now;
        tracker.firstPosition = positionMm;
        tracker.first = left ? leftId : rightId;
        sink.onEvent({"pair", top ? "top" : "bottom", "first_edge", positionMm, false});
    }

    if (elapsed(now, tracker.firstAt, config_.secondSensorTimeoutMs) ||
        std::abs(positionMm - tracker.firstPosition) > config_.pairDistanceWindowMm) {
        return top ? FaultCode::TopSensorMismatch : FaultCode::BottomSensorMismatch;
    }
    return FaultCode::None;
}

FaultCode SensorMonitor::checkStuck(Millis now) {
    static constexpr std::array<FaultCode, kSensorCount> faults{{
        FaultCode::LeftBottomStuck, FaultCode::RightBottomStuck,
        FaultCode::LeftTopStuck, FaultCode::RightTopStuck
    }};
    for (std::size_t i = 0; i < kSensorCount; ++i) {
        if (!signals_[i].active()) {
            stuckReported_[i] = false;
        } else if (!stuckReported_[i] && elapsed(now, signals_[i].activeSince(), config_.stuckActiveMs)) {
            stuckReported_[i] = true;
            return faults[i];
        }
    }
    return FaultCode::None;
}

FaultCode SensorMonitor::update(const SensorSnapshot& raw, Millis now, double positionMm, IEventSink& sink) {
    const FaultCode previousFault = fault_;
    const SensorSnapshot previous = stable_;
    for (std::size_t i = 0; i < kSensorCount; ++i) {
        signals_[i].update(raw.active[i], now, config_.debounceMs);
        stable_.active[i] = signals_[i].active();
    }
    emitSensorEdges(previous, sink);

    if ((stable_.get(SensorId::LeftBottom) && stable_.get(SensorId::LeftTop)) ||
        (stable_.get(SensorId::RightBottom) && stable_.get(SensorId::RightTop))) {
        fault_ = FaultCode::InvalidSensorCombination;
    }
    if (fault_ == FaultCode::None) {
        fault_ = updatePair(false, now, positionMm, sink);
    }
    if (fault_ == FaultCode::None) {
        fault_ = updatePair(true, now, positionMm, sink);
    }
    if (fault_ == FaultCode::None) {
        fault_ = checkStuck(now);
    }
    if (fault_ != FaultCode::None && fault_ != previousFault) {
        sink.onEvent({"fault", toString(fault_), "latched", positionMm, true});
    }
    return fault_;
}

FaultCode missingSensorFault(bool top, const SensorSnapshot& sensors) {
    const bool left = sensors.get(top ? SensorId::LeftTop : SensorId::LeftBottom);
    const bool right = sensors.get(top ? SensorId::RightTop : SensorId::RightBottom);
    if (!left && right) {
        return top ? FaultCode::LeftTopStuck : FaultCode::LeftBottomStuck;
    }
    if (left && !right) {
        return top ? FaultCode::RightTopStuck : FaultCode::RightBottomStuck;
    }
    return top ? FaultCode::TopPairTimeout : FaultCode::BottomPairTimeout;
}

}  // namespace egym
