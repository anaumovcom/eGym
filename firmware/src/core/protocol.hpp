#pragma once

#include "config.hpp"

#include <array>
#include <cstdint>
#include <string>

namespace egym {

enum class CommandType : std::uint8_t {
    Invalid,
    Ping,
    Heartbeat,
    Status,
    Home,
    Move,
    SetLoad,
    Start,
    Pause,
    Stop,
    ClearStop,
    SetMachineState,
    LedTest,
    InputTest,
    I2cTest,
    Diagnostics,
    SetNightMode,
    FirmwareInfo,
    PositionTelemetry,
    DriveFault,
    ButtonFeedback,
    SetActivity,
    PlayEffect,
    SetBrightness
};

struct ProtocolCommand {
    CommandType type{CommandType::Invalid};
    std::uint32_t sequence{0};
    double value{0.0};
    std::string text;
    bool flag{false};
    std::uint32_t requestSequence{0};
};

struct ParseResult {
    bool ok{false};
    bool duplicate{false};
    std::string error;
    ProtocolCommand command{};
};

enum class LineBufferResult : std::uint8_t { None, Line, Overflow };

class BoundedLineBuffer {
public:
    explicit BoundedLineBuffer(std::size_t maximumLineLength) : maximumLineLength_(maximumLineLength) {
        buffer_.reserve(maximumLineLength);
    }

    LineBufferResult push(char value, std::string& line);
    bool discarding() const { return discardUntilNewline_; }

private:
    std::size_t maximumLineLength_;
    std::string buffer_;
    bool discardUntilNewline_{false};
};

class ProtocolEngine {
public:
    explicit ProtocolEngine(ProtocolConfig config);

    ParseResult parse(const std::string& line, Millis now);
    bool updateHeartbeat(Millis now);
    bool connected() const { return connected_; }
    std::uint32_t nextTxSequence() { return ++txSequence_; }
    std::uint32_t lastTxSequence() const { return txSequence_; }
    void markDisconnected() { connected_ = false; }

    std::string eventJson(const CoreEvent& event);
    std::string stateJson(MachineState state);
    std::string faultJson(FaultCode fault, bool latched);
    std::string positionJson(const PositionResult& position);
    std::string pongJson(std::uint32_t requestSequence);
    std::string diagnosticJson(const std::string& subsystem, bool ok, const std::string& detail);
    std::string versionJson();
    std::string statusJson(
        MachineState state,
        FaultCode fault,
        bool stopLatched,
        bool inputHealthy,
        const std::array<bool, kButtonCount>& buttons,
        const SensorSnapshot& sensors,
        double positionMm
    );

private:
    std::string envelope(const std::string& type, const std::string& fields);

    ProtocolConfig config_{};
    bool connected_{false};
    Millis lastHeartbeatAt_{0};
    std::uint32_t lastRxSequence_{0};
    bool haveRxSequence_{false};
    std::uint32_t txSequence_{0};
    std::string session_;
};

const char* toString(CommandType command);

}  // namespace egym
