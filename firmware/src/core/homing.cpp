#include "homing.hpp"
#include "sensors.hpp"

#include <cmath>

namespace egym {
namespace {

bool elapsed(Millis now, Millis since, Millis duration) {
    return static_cast<Millis>(now - since) >= duration;
}

bool singleBottom(const SensorSnapshot& sensors) {
    return sensors.get(SensorId::LeftBottom) != sensors.get(SensorId::RightBottom);
}

bool singleTop(const SensorSnapshot& sensors) {
    return sensors.get(SensorId::LeftTop) != sensors.get(SensorId::RightTop);
}

}  // namespace

const char* toString(HomingPhase phase) {
    switch (phase) {
        case HomingPhase::Idle: return "idle";
        case HomingPhase::BottomCoarse: return "bottom_coarse";
        case HomingPhase::BottomCreep: return "bottom_creep";
        case HomingPhase::BottomBackoff: return "bottom_backoff";
        case HomingPhase::BottomFine: return "bottom_fine";
        case HomingPhase::TopCoarse: return "top_coarse";
        case HomingPhase::TopCreep: return "top_creep";
        case HomingPhase::TopBackoff: return "top_backoff";
        case HomingPhase::TopFine: return "top_fine";
        case HomingPhase::ApplyTopOffset: return "apply_top_offset";
        case HomingPhase::Complete: return "complete";
        case HomingPhase::Fault: return "fault";
        case HomingPhase::Aborted: return "aborted";
    }
    return "unknown";
}

HomingController::HomingController(HomingConfig config) : config_(config) {}

bool HomingController::running() const {
    return phase_ != HomingPhase::Idle && phase_ != HomingPhase::Complete && phase_ != HomingPhase::Fault && phase_ != HomingPhase::Aborted;
}

MotionRequest HomingController::motionFor(HomingPhase phase) const {
    switch (phase) {
        case HomingPhase::BottomCoarse: return {Direction::Down, config_.coarseSpeedMmPerSecond, false};
        case HomingPhase::BottomCreep: return {Direction::Down, config_.creepSpeedMmPerSecond, false};
        case HomingPhase::BottomBackoff: return {Direction::Up, config_.backoffSpeedMmPerSecond, false};
        case HomingPhase::BottomFine: return {Direction::Down, config_.fineSpeedMmPerSecond, false};
        case HomingPhase::TopCoarse: return {Direction::Up, config_.coarseSpeedMmPerSecond, false};
        case HomingPhase::TopCreep: return {Direction::Up, config_.creepSpeedMmPerSecond, false};
        case HomingPhase::TopBackoff: return {Direction::Down, config_.backoffSpeedMmPerSecond, false};
        case HomingPhase::TopFine: return {Direction::Up, config_.fineSpeedMmPerSecond, false};
        case HomingPhase::ApplyTopOffset: return {Direction::Down, config_.fineSpeedMmPerSecond, false};
        default: return {Direction::Stop, 0.0, true};
    }
}

HomingUpdate HomingController::transition(HomingPhase next, Millis now, double positionMm, IEventSink& sink, bool preserveFirstEdge) {
    phase_ = next;
    phaseStartedAt_ = now;
    phaseStartPosition_ = positionMm;
    if (!preserveFirstEdge) firstEdge_ = false;
    sink.onEvent({"state", "homing", toString(next), positionMm, running()});
    return {motionFor(next), phase_, fault_, true};
}

HomingUpdate HomingController::fail(FaultCode fault, double positionMm, IEventSink& sink) {
    fault_ = fault;
    phase_ = HomingPhase::Fault;
    result_.known = false;
    sink.onEvent({"fault", toString(fault), "homing_aborted", positionMm, true});
    return {motionFor(phase_), phase_, fault_, true};
}

HomingUpdate HomingController::start(Millis now, double positionMm, const SensorSnapshot& sensors, IEventSink& sink) {
    fault_ = FaultCode::None;
    result_ = {};
    startedAt_ = now;
    if ((sensors.get(SensorId::LeftBottom) && sensors.get(SensorId::LeftTop)) ||
        (sensors.get(SensorId::RightBottom) && sensors.get(SensorId::RightTop))) {
        return fail(FaultCode::InvalidSensorCombination, positionMm, sink);
    }
    if (singleBottom(sensors)) {
        return fail(FaultCode::BottomSensorMismatch, positionMm, sink);
    }
    if (singleTop(sensors)) {
        return fail(FaultCode::TopSensorMismatch, positionMm, sink);
    }
    if (sensors.bottomPair()) {
        return transition(HomingPhase::BottomBackoff, now, positionMm, sink);
    }
    return transition(HomingPhase::BottomCoarse, now, positionMm, sink);
}

bool HomingController::phaseTimedOut(Millis now) const {
    return elapsed(now, phaseStartedAt_, config_.phaseTimeoutMs) || elapsed(now, startedAt_, config_.totalTimeoutMs);
}

bool HomingController::searchDistanceExceeded(double positionMm) const {
    return std::abs(positionMm - phaseStartPosition_) > config_.maximumSearchDistanceMm;
}

HomingUpdate HomingController::abort(FaultCode reason, IEventSink& sink) {
    fault_ = reason;
    phase_ = HomingPhase::Aborted;
    result_.known = false;
    sink.onEvent({"fault", toString(reason), "homing_aborted", result_.currentMm, true});
    return {motionFor(phase_), phase_, fault_, true};
}

HomingUpdate HomingController::update(Millis now, double positionMm, const SensorSnapshot& sensors, bool stopRequested, bool driveFault, IEventSink& sink) {
    result_.currentMm = positionMm;
    if (!running()) {
        return {motionFor(phase_), phase_, fault_, false};
    }
    if (stopRequested) {
        return abort(FaultCode::EmergencyStop, sink);
    }
    if (driveFault) {
        return abort(FaultCode::DriveFault, sink);
    }
    if (phaseTimedOut(now)) {
        return fail(FaultCode::HomingTimeout, positionMm, sink);
    }
    if (searchDistanceExceeded(positionMm)) {
        return fail(FaultCode::HomingDistance, positionMm, sink);
    }
    if ((sensors.get(SensorId::LeftBottom) && sensors.get(SensorId::LeftTop)) ||
        (sensors.get(SensorId::RightBottom) && sensors.get(SensorId::RightTop))) {
        return fail(FaultCode::InvalidSensorCombination, positionMm, sink);
    }

    const bool bottomSearch = phase_ == HomingPhase::BottomCoarse || phase_ == HomingPhase::BottomCreep || phase_ == HomingPhase::BottomFine;
    const bool topSearch = phase_ == HomingPhase::TopCoarse || phase_ == HomingPhase::TopCreep || phase_ == HomingPhase::TopFine;
    const bool single = bottomSearch ? singleBottom(sensors) : (topSearch ? singleTop(sensors) : false);
    const bool pair = bottomSearch ? sensors.bottomPair() : (topSearch ? sensors.topPair() : false);
    if (single && !firstEdge_) {
        firstEdge_ = true;
        firstEdgeAt_ = now;
        firstEdgePosition_ = positionMm;
        if (phase_ == HomingPhase::BottomCoarse) return transition(HomingPhase::BottomCreep, now, positionMm, sink, true);
        if (phase_ == HomingPhase::TopCoarse) return transition(HomingPhase::TopCreep, now, positionMm, sink, true);
    }
    if ((single || pair) && firstEdge_ && (elapsed(now, firstEdgeAt_, config_.pairTimeWindowMs) ||
        std::abs(positionMm - firstEdgePosition_) > config_.pairDistanceWindowMm)) {
        return fail(missingSensorFault(topSearch, sensors), positionMm, sink);
    }

    switch (phase_) {
        case HomingPhase::BottomCoarse:
        case HomingPhase::BottomCreep:
            if (sensors.bottomPair()) return transition(HomingPhase::BottomBackoff, now, positionMm, sink);
            break;
        case HomingPhase::BottomBackoff:
            if (!sensors.get(SensorId::LeftBottom) && !sensors.get(SensorId::RightBottom)) {
                if (std::abs(positionMm - phaseStartPosition_) >= config_.backoffDistanceMm) {
                    return transition(HomingPhase::BottomFine, now, positionMm, sink);
                }
            } else if (std::abs(positionMm - phaseStartPosition_) > config_.backoffDistanceMm * 2.0) {
                return fail(FaultCode::BackoffReleaseFailed, positionMm, sink);
            }
            break;
        case HomingPhase::BottomFine:
            if (sensors.bottomPair()) {
                result_.physicalBottomMm = positionMm;
                result_.workingBottomMm = positionMm + config_.bottomOffsetMm;
                return transition(HomingPhase::TopCoarse, now, positionMm, sink);
            }
            break;
        case HomingPhase::TopCoarse:
        case HomingPhase::TopCreep:
            if (sensors.topPair()) return transition(HomingPhase::TopBackoff, now, positionMm, sink);
            break;
        case HomingPhase::TopBackoff:
            if (!sensors.get(SensorId::LeftTop) && !sensors.get(SensorId::RightTop)) {
                if (std::abs(positionMm - phaseStartPosition_) >= config_.backoffDistanceMm) {
                    return transition(HomingPhase::TopFine, now, positionMm, sink);
                }
            } else if (std::abs(positionMm - phaseStartPosition_) > config_.backoffDistanceMm * 2.0) {
                return fail(FaultCode::BackoffReleaseFailed, positionMm, sink);
            }
            break;
        case HomingPhase::TopFine:
            if (sensors.topPair()) {
                result_.physicalTopMm = positionMm;
                result_.workingTopMm = positionMm - config_.topOffsetMm;
                result_.travelMm = result_.workingTopMm - result_.workingBottomMm;
                if (result_.travelMm <= 0.0) return fail(FaultCode::HomingDistance, positionMm, sink);
                return transition(HomingPhase::ApplyTopOffset, now, positionMm, sink);
            }
            break;
        case HomingPhase::ApplyTopOffset:
            if (positionMm <= result_.workingTopMm) {
                result_.known = true;
                result_.currentMm = positionMm;
                return transition(HomingPhase::Complete, now, positionMm, sink);
            }
            break;
        default: break;
    }
    return {motionFor(phase_), phase_, fault_, false};
}

}  // namespace egym
