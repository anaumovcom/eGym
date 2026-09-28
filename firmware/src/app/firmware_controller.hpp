#pragma once

#include "../core/button.hpp"
#include "../core/homing.hpp"
#include "../core/led.hpp"
#include "../core/logger.hpp"
#include "../core/protocol.hpp"
#include "../core/sensors.hpp"
#include "../hal/arduino_hal.hpp"

namespace egym {

class FirmwareController final : public IEventSink {
public:
    explicit FirmwareController(FirmwareConfig config);

    void begin();
    void tick();
    void onEvent(const CoreEvent& event) override;

private:
    void pollInputs(Millis now);
    void pollUsb(Millis now);
    void handleCommand(const ProtocolCommand& command, Millis now);
    void handleButton(const CoreEvent& event, Millis now);
    void applyMotion(const MotionRequest& request, Millis now);
    void setState(MachineState state, Millis now);
    void latchFault(FaultCode fault, Millis now, bool emergency);
    void clearEmergency(Millis now);
    void runDiagnostics(Millis now);
    void flushLogs();
    void send(std::string line);
    MachineState parseState(const std::string& state) const;

    FirmwareConfig config_;
    I2cBusManager i2c_;
    McpInputAdapter inputs_;
    PcaLedAdapter ledOutput_;
    SafetyEnableAdapter safetyEnable_;
    UsbCdcTransport usb_;
    ButtonBank buttons_;
    SensorMonitor sensors_;
    HomingController homing_;
    LedEngine leds_;
    ProtocolEngine protocol_;
    StructuredLogger logger_;
    std::array<bool, kButtonCount> rawButtons_{};
    std::array<std::uint32_t, kButtonCount> pendingFeedback_{};
    SensorSnapshot rawSensors_{};
    MachineState state_{MachineState::Booting};
    FaultCode fault_{FaultCode::None};
    bool stopLatched_{false};
    bool driveFault_{false};
    bool inputHealthy_{false};
    bool ledHealthy_{false};
    bool previousProtocolConnected_{false};
    double positionMm_{0.0};
    Millis lastInputPollAt_{0};
    Millis bootedAt_{0};
    Millis lastStatusAt_{0};
};

}  // namespace egym
