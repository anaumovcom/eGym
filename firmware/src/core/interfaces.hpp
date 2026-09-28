#pragma once

#include "types.hpp"

#include <array>
#include <cstdint>
#include <string>

namespace egym {

class IEventSink {
public:
    virtual ~IEventSink() = default;
    virtual void onEvent(const CoreEvent& event) = 0;
};

class ILedOutput {
public:
    virtual ~ILedOutput() = default;
    virtual bool write(const std::array<std::uint16_t, kButtonCount>& pwm) = 0;
    virtual void allOff() = 0;
};

class IMotionOutput {
public:
    virtual ~IMotionOutput() = default;
    virtual void requestMotion(const MotionRequest& request) = 0;
    virtual void emergencyStop() = 0;
};

class ILineTransport {
public:
    virtual ~ILineTransport() = default;
    virtual bool readLine(std::string& line) = 0;
    virtual bool writeLine(const std::string& line) = 0;
    virtual bool connected() const = 0;
};

}  // namespace egym
