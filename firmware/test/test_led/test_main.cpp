#include <unity.h>

#include "core/led.hpp"
#include "../test_support.hpp"

using namespace egym;

void test_gamma_endpoints_and_midpoint() {
    GammaCorrector gamma(2.2F);
    TEST_ASSERT_EQUAL_UINT16(0, gamma.toPwm(0.0F));
    TEST_ASSERT_EQUAL_UINT16(4095, gamma.toPwm(1.0F));
    TEST_ASSERT_UINT16_WITHIN(2, 891, gamma.toPwm(0.5F));
}

void test_panel_geometry_rows_and_columns() {
    TEST_ASSERT_EQUAL_UINT8(0, kPanelGeometry[index(ButtonId::Power)].row);
    TEST_ASSERT_EQUAL(Column::Center, kPanelGeometry[index(ButtonId::Power)].column);
    TEST_ASSERT_EQUAL_UINT8(1, kPanelGeometry[index(ButtonId::Up)].row);
    TEST_ASSERT_EQUAL(Column::Left, kPanelGeometry[index(ButtonId::Up)].column);
    TEST_ASSERT_EQUAL(Column::Right, kPanelGeometry[index(ButtonId::Down)].column);
    TEST_ASSERT_EQUAL_UINT8(5, kPanelGeometry[index(ButtonId::Stop)].row);
}

void test_startup_wave_uses_symmetric_rows() {
    LedCollector output;
    LedConfig config;
    config.frameIntervalMs = 1;
    config.startupWaveMs = 600;
    LedEngine engine(config, output);
    engine.setMachineState(MachineState::Booting, 0);
    engine.play(PatternId::StartupWave, 0);
    engine.update(150); // Row 1, UP + DOWN.
    TEST_ASSERT_FLOAT_WITHIN(0.001F, engine.logicalFrame()[index(ButtonId::Up)], engine.logicalFrame()[index(ButtonId::Down)]);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::Up)] > engine.logicalFrame()[index(ButtonId::LoadPlus)]);
}

void test_overlay_restores_base_and_emergency_has_highest_priority() {
    LedCollector output;
    LedConfig config;
    config.frameIntervalMs = 1;
    config.pressDurationMs = 100;
    LedEngine engine(config, output);
    engine.setMachineState(MachineState::Ready, 0);
    engine.update(1);
    const float readyStart = engine.logicalFrame()[index(ButtonId::StartPause)];
    engine.play(PatternId::ButtonPress, 2, ButtonId::StartPause);
    engine.update(30);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::StartPause)] > readyStart);
    engine.update(103);
    TEST_ASSERT_FLOAT_WITHIN(0.001F, readyStart, engine.logicalFrame()[index(ButtonId::StartPause)]);

    engine.play(PatternId::OkDoublePulse, 110, ButtonId::Ok);
    engine.setEmergency(true, 111);
    engine.update(112);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::Stop)] > 0.9F);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::Ok)] < 0.05F);
}

void test_persistent_diagnostic_rejects_button_overlay_and_error_cancels_it() {
    LedCollector output;
    LedConfig config;
    config.frameIntervalMs = 1;
    LedEngine engine(config, output);
    engine.setMachineState(MachineState::Maintenance, 0);
    engine.play(PatternId::ButtonSelfTest, 1);
    engine.setButtonHeld(ButtonId::Ok, true, 2);
    engine.play(PatternId::ButtonPress, 3, ButtonId::Power);
    engine.update(4);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::Ok)] > 0.9F);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::Power)] < 0.2F);

    engine.setMachineState(MachineState::Error, 5);
    engine.update(6);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::Fail)] > engine.logicalFrame()[index(ButtonId::Ok)]);
}

void test_error_and_emergency_ignore_button_feedback_and_dimming() {
    LedCollector output;
    LedConfig config;
    config.frameIntervalMs = 1;
    config.globalBrightness = 0.1F;
    LedEngine engine(config, output);
    engine.setNightMode(true);
    engine.setBrightness(0.1F);
    engine.setMachineState(MachineState::Error, 1);
    engine.play(PatternId::ButtonPress, 2, ButtonId::Up);
    engine.update(3);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::Up)] < 0.1F);
    engine.setEmergency(true, 4);
    engine.update(5);
    TEST_ASSERT_EQUAL_UINT16(4095, engine.pwmFrame()[index(ButtonId::Stop)]);
}

void test_repeat_does_not_restart_activity_pulse() {
    LedCollector output;
    LedConfig config;
    config.frameIntervalMs = 1;
    LedEngine engine(config, output);
    engine.setMachineState(MachineState::Positioning, 0);
    engine.setActivity(Direction::Up, ButtonId::Up, true, 1);
    engine.setButtonHeld(ButtonId::Up, true, 1);
    engine.update(302);
    const auto brightness = engine.logicalFrame()[index(ButtonId::Up)];
    engine.setActivity(Direction::Up, ButtonId::Up, true, 302);
    engine.setButtonHeld(ButtonId::Up, true, 302);
    engine.update(303);
    TEST_ASSERT_FLOAT_WITHIN(0.03F, brightness, engine.logicalFrame()[index(ButtonId::Up)]);
}

void test_transition_effect_survives_paused_state_and_homing_has_two_peaks() {
    LedCollector output;
    LedConfig config;
    config.frameIntervalMs = 1;
    LedEngine engine(config, output);
    engine.setMachineState(MachineState::SetComplete, 0);
    engine.play(PatternId::SetCompleteEffect, 1);
    engine.setMachineState(MachineState::Paused, 2);
    engine.update(250);
    TEST_ASSERT_TRUE(engine.logicalFrame()[index(ButtonId::Ok)] > 0.4F);
    engine.update(1502);
    TEST_ASSERT_FLOAT_WITHIN(0.01F, 0.20F, engine.logicalFrame()[index(ButtonId::Ok)]);

    engine.play(PatternId::HomingComplete, 1510);
    engine.update(1570);
    const auto first = engine.logicalFrame()[index(ButtonId::Ok)];
    engine.update(1820);
    TEST_ASSERT_FLOAT_WITHIN(0.05F, first, engine.logicalFrame()[index(ButtonId::Ok)]);
}

void test_power_wave_is_not_replaced_by_button_press() {
    LedCollector output;
    LedConfig config;
    config.frameIntervalMs = 1;
    config.startupWaveMs = 600;
    LedEngine engine(config, output);
    engine.setMachineState(MachineState::Booting, 0);
    engine.play(PatternId::StartupWave, 0);
    engine.play(PatternId::ButtonPress, 1, ButtonId::Up);
    engine.update(150);
    TEST_ASSERT_FLOAT_WITHIN(0.01F, engine.logicalFrame()[index(ButtonId::Up)], engine.logicalFrame()[index(ButtonId::Down)]);
}

void setUp() {}
void tearDown() {}
int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_gamma_endpoints_and_midpoint);
    RUN_TEST(test_panel_geometry_rows_and_columns);
    RUN_TEST(test_startup_wave_uses_symmetric_rows);
    RUN_TEST(test_overlay_restores_base_and_emergency_has_highest_priority);
    RUN_TEST(test_persistent_diagnostic_rejects_button_overlay_and_error_cancels_it);
    RUN_TEST(test_error_and_emergency_ignore_button_feedback_and_dimming);
    RUN_TEST(test_repeat_does_not_restart_activity_pulse);
    RUN_TEST(test_transition_effect_survives_paused_state_and_homing_has_two_peaks);
    RUN_TEST(test_power_wave_is_not_replaced_by_button_press);
    return UNITY_END();
}
