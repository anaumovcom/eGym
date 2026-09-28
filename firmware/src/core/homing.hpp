#pragma once

#include "config.hpp"
#include "interfaces.hpp"

namespace egym {

enum class HomingPhase : std::uint8_t {
    Idle,
    BottomCoarse,
    BottomCreep,
    BottomBackoff,
    BottomFine,
    TopCoarse,
    TopCreep,
    TopBackoff,
    TopFine,
    ApplyTopOffset,
    Complete,
    Fault,
    Aborted
};

struct HomingUpdate {
    MotionRequest motion{};
    HomingPhase phase{HomingPhase::Idle};
    FaultCode fault{FaultCode::None};
    bool changed{false};
};

class HomingController {
public:
    explicit HomingController(HomingConfig config);

    HomingUpdate start(Millis now, double positionMm, const SensorSnapshot& sensors, IEventSink& sink);
    HomingUpdate update(Millis now, double positionMm, const SensorSnapshot& sensors, bool stopRequested, bool driveFault, IEventSink& sink);
    HomingUpdate abort(FaultCode reason, IEventSink& sink);

    HomingPhase phase() const { return phase_; }
    FaultCode fault() const { return fault_; }
    const PositionResult& result() const { return result_; }
    bool running() const;

private:
    HomingUpdate transition(HomingPhase next, Millis now, double positionMm, IEventSink& sink, bool preserveFirstEdge = false);
    HomingUpdate fail(FaultCode fault, double positionMm, IEventSink& sink);
    MotionRequest motionFor(HomingPhase phase) const;
    bool phaseTimedOut(Millis now) const;
    bool searchDistanceExceeded(double positionMm) const;

    HomingConfig config_{};
    HomingPhase phase_{HomingPhase::Idle};
    FaultCode fault_{FaultCode::None};
    PositionResult result_{};
    Millis startedAt_{0};
    Millis phaseStartedAt_{0};
    double phaseStartPosition_{0.0};
    bool firstEdge_{false};
    Millis firstEdgeAt_{0};
    double firstEdgePosition_{0.0};
};

const char* toString(HomingPhase phase);

}  // namespace egym
