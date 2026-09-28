#include <unity.h>

#include "core/sensors.hpp"
#include "../test_support.hpp"

using namespace egym;

void settle(SensorMonitor& monitor, const SensorSnapshot& sample, Millis at, double position, EventCollector& sink) {
    monitor.update(sample, at, position, sink);
    monitor.update(sample, at + 5, position, sink);
}

void test_pair_confirms_only_when_both_edges_are_in_window() {
    SensorConfig config;
    config.debounceMs = 5;
    config.pairTimeWindowMs = 100;
    config.secondSensorTimeoutMs = 150;
    config.pairDistanceWindowMm = 3.0;
    config.stuckActiveMs = 10000;
    SensorMonitor monitor(config);
    EventCollector sink;

    settle(monitor, sensors(true, false, false, false), 0, 10.0, sink);
    TEST_ASSERT_EQUAL(FaultCode::None, monitor.update(sensors(true, true, false, false), 50, 12.0, sink));
    TEST_ASSERT_EQUAL(FaultCode::None, monitor.update(sensors(true, true, false, false), 55, 12.0, sink));
    TEST_ASSERT_TRUE(monitor.snapshot().bottomPair());
}

void test_pair_time_mismatch_faults() {
    SensorConfig config;
    config.debounceMs = 1;
    config.pairTimeWindowMs = 30;
    config.secondSensorTimeoutMs = 40;
    config.pairDistanceWindowMm = 5.0;
    config.stuckActiveMs = 10000;
    SensorMonitor monitor(config);
    EventCollector sink;

    settle(monitor, sensors(true, false, false, false), 0, 10.0, sink);
    TEST_ASSERT_EQUAL(FaultCode::BottomSensorMismatch, monitor.update(sensors(true, false, false, false), 45, 10.0, sink));
}

void test_pair_distance_mismatch_and_invalid_combination_fault() {
    SensorConfig config;
    config.debounceMs = 1;
    config.pairTimeWindowMs = 100;
    config.secondSensorTimeoutMs = 200;
    config.pairDistanceWindowMm = 2.0;
    config.stuckActiveMs = 10000;
    SensorMonitor distanceMonitor(config);
    EventCollector sink;
    settle(distanceMonitor, sensors(false, true, false, false), 0, 10.0, sink);
    TEST_ASSERT_EQUAL(FaultCode::BottomSensorMismatch, distanceMonitor.update(sensors(false, true, false, false), 10, 13.0, sink));

    SensorMonitor invalidMonitor(config);
    EventCollector sink2;
    settle(invalidMonitor, sensors(true, true, true, false), 0, 0.0, sink2);
    TEST_ASSERT_EQUAL(FaultCode::InvalidSensorCombination, invalidMonitor.update(sensors(true, true, true, false), 2, 0.0, sink2));
}

void setUp() {}
void tearDown() {}
int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_pair_confirms_only_when_both_edges_are_in_window);
    RUN_TEST(test_pair_time_mismatch_faults);
    RUN_TEST(test_pair_distance_mismatch_and_invalid_combination_fault);
    return UNITY_END();
}
