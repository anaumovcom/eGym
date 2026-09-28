#include "types.hpp"

namespace egym {

const char* toString(ButtonId id) {
    static constexpr const char* names[] = {"power", "up", "down", "load_plus", "load_minus", "start_pause", "camera", "ok", "fail", "stop"};
    const auto i = index(id);
    return i < kButtonCount ? names[i] : "unknown";
}

const char* toString(SensorId id) {
    static constexpr const char* names[] = {"left_bottom", "right_bottom", "left_top", "right_top"};
    const auto i = index(id);
    return i < kSensorCount ? names[i] : "unknown";
}

const char* toString(ButtonEventType event) {
    switch (event) {
        case ButtonEventType::Pressed: return "pressed";
        case ButtonEventType::Released: return "released";
        case ButtonEventType::LongPress: return "long_press";
        case ButtonEventType::Repeat: return "repeat";
    }
    return "unknown";
}

const char* toString(MachineState state) {
    switch (state) {
        case MachineState::Off: return "off";
        case MachineState::Booting: return "booting";
        case MachineState::Homing: return "homing";
        case MachineState::Ready: return "ready";
        case MachineState::Positioning: return "positioning";
        case MachineState::ExerciseActive: return "exercise_active";
        case MachineState::Paused: return "paused";
        case MachineState::SetComplete: return "set_complete";
        case MachineState::Warning: return "warning";
        case MachineState::Error: return "error";
        case MachineState::EmergencyStop: return "emergency_stop";
        case MachineState::Maintenance: return "maintenance";
        case MachineState::Calibration: return "calibration";
    }
    return "unknown";
}

const char* toString(FaultCode fault) {
    switch (fault) {
        case FaultCode::None: return "none";
        case FaultCode::BottomSensorMismatch: return "bottom_sensor_mismatch";
        case FaultCode::TopSensorMismatch: return "top_sensor_mismatch";
        case FaultCode::LeftBottomStuck: return "left_bottom_stuck";
        case FaultCode::RightBottomStuck: return "right_bottom_stuck";
        case FaultCode::LeftTopStuck: return "left_top_stuck";
        case FaultCode::RightTopStuck: return "right_top_stuck";
        case FaultCode::BottomPairTimeout: return "bottom_pair_timeout";
        case FaultCode::TopPairTimeout: return "top_pair_timeout";
        case FaultCode::InvalidSensorCombination: return "invalid_sensor_combination";
        case FaultCode::HomingTimeout: return "homing_timeout";
        case FaultCode::HomingDistance: return "homing_distance";
        case FaultCode::BackoffReleaseFailed: return "backoff_release_failed";
        case FaultCode::DriveFault: return "drive_fault";
        case FaultCode::HeartbeatTimeout: return "heartbeat_timeout";
        case FaultCode::McpUnavailable: return "mcp_unavailable";
        case FaultCode::PcaUnavailable: return "pca_unavailable";
        case FaultCode::I2cBusFault: return "i2c_bus_fault";
        case FaultCode::ProtocolError: return "protocol_error";
        case FaultCode::EmergencyStop: return "emergency_stop";
    }
    return "unknown";
}

}  // namespace egym
