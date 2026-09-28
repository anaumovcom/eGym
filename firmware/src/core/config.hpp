#pragma once

#include "types.hpp"

#include <array>
#include <cstdint>

namespace egym {

struct ButtonBehavior {
    std::uint16_t debounceMs{25};
    std::uint16_t longPressMs{700};
    std::uint16_t repeatDelayMs{450};
    std::uint16_t repeatIntervalMs{120};
    std::uint16_t acceleratedIntervalMs{45};
    std::uint16_t accelerationAfterMs{1800};
    bool repeat{false};
    bool continuousHold{false};
};

struct InputChannel {
    std::uint8_t mcpPin;
    bool activeLow;
};

struct LedChannel {
    std::uint8_t pwmChannel;
    bool inverted;
    float gain;
};

struct HardwareConfig {
    std::int8_t i2cSda{8};
    std::int8_t i2cScl{9};
    std::uint32_t i2cHz{400000};
    std::uint8_t mcpAddress{0x20};
    std::uint8_t pcaAddress{0x40};
    std::uint16_t pcaFrequencyHz{1000};
    std::uint16_t inputPollMs{5};
    bool safetyEnablePresent{false};
    std::int8_t safetyEnablePin{14};
    bool safetyEnableActiveLow{true};
    std::array<InputChannel, kButtonCount> buttons{{
        {0, true}, {1, true}, {2, true}, {3, true}, {4, true},
        {5, true}, {6, true}, {7, true}, {8, true}, {9, true}
    }};
    std::array<InputChannel, kSensorCount> sensors{{
        {10, true}, {11, true}, {12, true}, {13, true}
    }};
    std::array<LedChannel, kButtonCount> leds{{
        {0, false, 1.0F}, {1, false, 1.0F}, {2, false, 1.0F}, {3, false, 1.0F}, {4, false, 1.0F},
        {5, false, 1.0F}, {6, false, 1.0F}, {7, false, 1.0F}, {8, false, 1.0F}, {9, false, 1.0F}
    }};
};

struct SensorConfig {
    std::uint16_t debounceMs{15};
    std::uint16_t pairTimeWindowMs{120};
    std::uint16_t secondSensorTimeoutMs{250};
    double pairDistanceWindowMm{4.0};
    std::uint32_t stuckActiveMs{10000};
};

struct HomingConfig {
    double coarseSpeedMmPerSecond{40.0};
    double creepSpeedMmPerSecond{8.0};
    double fineSpeedMmPerSecond{4.0};
    double backoffSpeedMmPerSecond{12.0};
    double backoffDistanceMm{8.0};
    double maximumSearchDistanceMm{2200.0};
    std::uint32_t phaseTimeoutMs{45000};
    std::uint32_t totalTimeoutMs{120000};
    std::uint16_t pairTimeWindowMs{120};
    double pairDistanceWindowMm{4.0};
    double bottomOffsetMm{5.0};
    double topOffsetMm{5.0};
};

struct LedConfig {
    float gamma{2.2F};
    float globalBrightness{1.0F};
    float nightScale{0.4F};
    std::uint16_t frameIntervalMs{10};
    std::uint16_t pressDurationMs{260};
    std::uint16_t disabledDurationMs{350};
    std::uint16_t startupWaveMs{900};
    std::uint16_t shutdownWaveMs{800};
    std::uint16_t emergencyPeriodMs{600};
};

struct ProtocolConfig {
    std::uint32_t heartbeatTimeoutMs{1500};
    std::uint32_t statusIntervalMs{500};
    std::size_t maximumLineLength{768};
};

struct FirmwareConfig {
    HardwareConfig hardware{};
    SensorConfig sensors{};
    HomingConfig homing{};
    LedConfig led{};
    ProtocolConfig protocol{};
    std::array<ButtonBehavior, kButtonCount> buttonBehavior{};

    FirmwareConfig() {
        buttonBehavior[index(ButtonId::Up)].repeat = true;
        buttonBehavior[index(ButtonId::Up)].continuousHold = true;
        buttonBehavior[index(ButtonId::Down)].repeat = true;
        buttonBehavior[index(ButtonId::Down)].continuousHold = true;
        buttonBehavior[index(ButtonId::LoadPlus)].repeat = true;
        buttonBehavior[index(ButtonId::LoadMinus)].repeat = true;
    }
};

constexpr std::array<PanelPoint, kButtonCount> kPanelGeometry{{
    {0, Column::Center}, {1, Column::Left}, {1, Column::Right},
    {2, Column::Left}, {2, Column::Right}, {3, Column::Left},
    {3, Column::Right}, {4, Column::Left}, {4, Column::Right},
    {5, Column::Center}
}};

}  // namespace egym
