#include "arduino_hal.hpp"

#include <algorithm>

namespace egym {

bool I2cBusManager::begin() {
    return Wire.begin(config_.i2cSda, config_.i2cScl, config_.i2cHz);
}

bool I2cBusManager::probe(std::uint8_t address) {
    Wire.beginTransmission(address);
    return Wire.endTransmission() == 0;
}

bool I2cBusManager::recover() {
    ++recoveryCount_;
    Wire.end();
    pinMode(config_.i2cSda, INPUT_PULLUP);
    pinMode(config_.i2cScl, OUTPUT_OPEN_DRAIN);
    digitalWrite(config_.i2cScl, HIGH);
    delayMicroseconds(5);
    for (int pulse = 0; pulse < 9 && digitalRead(config_.i2cSda) == LOW; ++pulse) {
        digitalWrite(config_.i2cScl, LOW);
        delayMicroseconds(5);
        digitalWrite(config_.i2cScl, HIGH);
        delayMicroseconds(5);
    }
    pinMode(config_.i2cSda, OUTPUT_OPEN_DRAIN);
    digitalWrite(config_.i2cSda, LOW);
    delayMicroseconds(5);
    digitalWrite(config_.i2cScl, HIGH);
    delayMicroseconds(5);
    digitalWrite(config_.i2cSda, HIGH);
    delayMicroseconds(5);
    return begin();
}

McpInputAdapter::McpInputAdapter(const HardwareConfig& config, I2cBusManager& bus)
    : config_(config), bus_(bus) {}

bool McpInputAdapter::begin() {
    healthy_ = bus_.probe(config_.mcpAddress) && mcp_.begin_I2C(config_.mcpAddress, &Wire);
    if (!healthy_) return false;
    for (const auto& channel : config_.buttons) mcp_.pinMode(channel.mcpPin, channel.activeLow ? INPUT_PULLUP : INPUT);
    for (const auto& channel : config_.sensors) mcp_.pinMode(channel.mcpPin, channel.activeLow ? INPUT_PULLUP : INPUT);
    return true;
}

bool McpInputAdapter::read(std::array<bool, kButtonCount>& buttons, SensorSnapshot& sensors) {
    if (!healthy_ && !begin()) return false;
    if (!bus_.probe(config_.mcpAddress)) {
        healthy_ = false;
        return false;
    }
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        const auto& channel = config_.buttons[i];
        const bool high = mcp_.digitalRead(channel.mcpPin) == HIGH;
        buttons[i] = channel.activeLow ? !high : high;
    }
    for (std::size_t i = 0; i < kSensorCount; ++i) {
        const auto& channel = config_.sensors[i];
        const bool high = mcp_.digitalRead(channel.mcpPin) == HIGH;
        sensors.active[i] = channel.activeLow ? !high : high;
    }
    return true;
}

PcaLedAdapter::PcaLedAdapter(const HardwareConfig& config, I2cBusManager& bus)
    : config_(config), bus_(bus), pca_(config.pcaAddress, Wire) {}

bool PcaLedAdapter::begin() {
    healthy_ = bus_.probe(config_.pcaAddress) && pca_.begin();
    if (healthy_) {
        pca_.setPWMFreq(config_.pcaFrequencyHz);
        allOff();
    }
    return healthy_;
}

bool PcaLedAdapter::write(const std::array<std::uint16_t, kButtonCount>& pwm) {
    if (!healthy_ && !begin()) return false;
    if (!bus_.probe(config_.pcaAddress)) {
        healthy_ = false;
        return false;
    }
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        const auto& channel = config_.leds[i];
        const float gained = std::min(4095.0F, static_cast<float>(pwm[i]) * channel.gain);
        std::uint16_t value = static_cast<std::uint16_t>(gained);
        if (channel.inverted) value = static_cast<std::uint16_t>(4095U - value);
        pca_.setPin(channel.pwmChannel, value, false);
    }
    return true;
}

void PcaLedAdapter::allOff() {
    for (const auto& channel : config_.leds) pca_.setPin(channel.pwmChannel, channel.inverted ? 4095 : 0, false);
}

void SafetyEnableAdapter::begin() {
    if (!config_.safetyEnablePresent) return;
    pinMode(config_.safetyEnablePin, OUTPUT);
    disable();
}

void SafetyEnableAdapter::enable() {
    if (!config_.safetyEnablePresent) return;
    digitalWrite(config_.safetyEnablePin, config_.safetyEnableActiveLow ? LOW : HIGH);
    enabled_ = true;
}

void SafetyEnableAdapter::disable() {
    if (!config_.safetyEnablePresent) return;
    digitalWrite(config_.safetyEnablePin, config_.safetyEnableActiveLow ? HIGH : LOW);
    enabled_ = false;
}

void UsbCdcTransport::begin(unsigned long baud) {
    Serial.begin(baud);
}

void UsbCdcTransport::poll() {
    while (Serial.available() > 0 && !lineReady_) {
        const char value = static_cast<char>(Serial.read());
        const auto result = lineBuffer_.push(value, readyLine_);
        if (result == LineBufferResult::Line) {
            lineReady_ = true;
        } else if (result == LineBufferResult::Overflow) {
            readyLine_.assign(maximumLineLength_ + 1U, '!');
            lineReady_ = true;
        }
    }
}

bool UsbCdcTransport::readLine(std::string& line) {
    if (!lineReady_) return false;
    line = readyLine_;
    lineReady_ = false;
    return true;
}

bool UsbCdcTransport::writeLine(const std::string& line) {
    return Serial.write(reinterpret_cast<const std::uint8_t*>(line.data()), line.size()) == line.size();
}

bool UsbCdcTransport::connected() const {
    return static_cast<bool>(Serial);
}

}  // namespace egym
