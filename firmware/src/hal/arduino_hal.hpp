#pragma once

#include "../core/config.hpp"
#include "../core/interfaces.hpp"
#include "../core/protocol.hpp"

#include <Adafruit_MCP23X17.h>
#include <Adafruit_PWMServoDriver.h>
#include <Arduino.h>
#include <Wire.h>

#include <array>
#include <string>

namespace egym {

class I2cBusManager {
public:
    explicit I2cBusManager(const HardwareConfig& config) : config_(config) {}
    bool begin();
    bool recover();
    bool probe(std::uint8_t address);
    std::uint32_t recoveryCount() const { return recoveryCount_; }

private:
    const HardwareConfig& config_;
    std::uint32_t recoveryCount_{0};
};

class McpInputAdapter {
public:
    McpInputAdapter(const HardwareConfig& config, I2cBusManager& bus);
    bool begin();
    bool read(std::array<bool, kButtonCount>& buttons, SensorSnapshot& sensors);
    bool healthy() const { return healthy_; }

private:
    const HardwareConfig& config_;
    I2cBusManager& bus_;
    Adafruit_MCP23X17 mcp_{};
    bool healthy_{false};
};

class PcaLedAdapter final : public ILedOutput {
public:
    PcaLedAdapter(const HardwareConfig& config, I2cBusManager& bus);
    bool begin();
    bool write(const std::array<std::uint16_t, kButtonCount>& pwm) override;
    void allOff() override;
    bool healthy() const { return healthy_; }

private:
    const HardwareConfig& config_;
    I2cBusManager& bus_;
    Adafruit_PWMServoDriver pca_;
    bool healthy_{false};
};

class SafetyEnableAdapter {
public:
    explicit SafetyEnableAdapter(const HardwareConfig& config) : config_(config) {}
    void begin();
    void enable();
    void disable();
    bool enabled() const { return enabled_; }

private:
    const HardwareConfig& config_;
    bool enabled_{false};
};

class UsbCdcTransport final : public ILineTransport {
public:
    explicit UsbCdcTransport(std::size_t maximumLineLength)
        : maximumLineLength_(maximumLineLength), lineBuffer_(maximumLineLength) {}
    void begin(unsigned long baud);
    void poll();
    bool readLine(std::string& line) override;
    bool writeLine(const std::string& line) override;
    bool connected() const override;

private:
    std::size_t maximumLineLength_;
    BoundedLineBuffer lineBuffer_;
    std::string readyLine_;
    bool lineReady_{false};
};

}  // namespace egym
