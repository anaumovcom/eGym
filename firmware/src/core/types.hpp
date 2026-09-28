#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

namespace egym {

constexpr std::size_t kButtonCount = 10;
constexpr std::size_t kSensorCount = 4;
constexpr std::size_t kPanelRows = 6;

using Millis = std::uint32_t;

enum class ButtonId : std::uint8_t {
    Power,
    Up,
    Down,
    LoadPlus,
    LoadMinus,
    StartPause,
    Camera,
    Ok,
    Fail,
    Stop,
    Count
};

enum class SensorId : std::uint8_t {
    LeftBottom,
    RightBottom,
    LeftTop,
    RightTop,
    Count
};

enum class ButtonEventType : std::uint8_t { Pressed, Released, LongPress, Repeat };
enum class Column : std::int8_t { Left = -1, Center = 0, Right = 1 };
enum class Direction : std::int8_t { Down = -1, Stop = 0, Up = 1 };

enum class MachineState : std::uint8_t {
    Off,
    Booting,
    Homing,
    Ready,
    Positioning,
    ExerciseActive,
    Paused,
    SetComplete,
    Warning,
    Error,
    EmergencyStop,
    Maintenance,
    Calibration
};

enum class FaultCode : std::uint8_t {
    None,
    BottomSensorMismatch,
    TopSensorMismatch,
    LeftBottomStuck,
    RightBottomStuck,
    LeftTopStuck,
    RightTopStuck,
    BottomPairTimeout,
    TopPairTimeout,
    InvalidSensorCombination,
    HomingTimeout,
    HomingDistance,
    BackoffReleaseFailed,
    DriveFault,
    HeartbeatTimeout,
    McpUnavailable,
    PcaUnavailable,
    I2cBusFault,
    ProtocolError,
    EmergencyStop
};

enum class PatternId : std::uint8_t {
    None,
    StartupWave,
    ShutdownWave,
    StartupComplete,
    ButtonPress,
    DisabledFeedback,
    HomeDetected,
    HomingComplete,
    TargetReached,
    CameraShutter,
    OkDoublePulse,
    FailPulse,
    StopPressed,
    LimitTriggered,
    UsbConnected,
    UsbDisconnected,
    PcActivity,
    LedSelfTest,
    ButtonSelfTest,
    SensorDiagnostic,
    SetCompleteEffect
};

struct PanelPoint {
    std::uint8_t row;
    Column column;
};

struct SensorSnapshot {
    std::array<bool, kSensorCount> active{};

    bool get(SensorId id) const { return active[static_cast<std::size_t>(id)]; }
    bool bottomPair() const { return get(SensorId::LeftBottom) && get(SensorId::RightBottom); }
    bool topPair() const { return get(SensorId::LeftTop) && get(SensorId::RightTop); }
};

struct PositionResult {
    bool known{false};
    double physicalBottomMm{0.0};
    double physicalTopMm{0.0};
    double workingBottomMm{0.0};
    double workingTopMm{0.0};
    double travelMm{0.0};
    double currentMm{0.0};
};

struct MotionRequest {
    Direction direction{Direction::Stop};
    double speedMmPerSecond{0.0};
    bool stop{true};
};

struct CoreEvent {
    std::string type;
    std::string id;
    std::string value;
    double number{0.0};
    bool flag{false};
};

constexpr std::size_t index(ButtonId id) { return static_cast<std::size_t>(id); }
constexpr std::size_t index(SensorId id) { return static_cast<std::size_t>(id); }

const char* toString(ButtonId id);
const char* toString(SensorId id);
const char* toString(ButtonEventType event);
const char* toString(MachineState state);
const char* toString(FaultCode fault);

}  // namespace egym
