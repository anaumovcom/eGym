#include <unity.h>

#include "core/homing.hpp"
#include "../test_support.hpp"

using namespace egym;

HomingConfig fastConfig() {
    HomingConfig config;
    config.backoffDistanceMm = 8.0;
    config.pairTimeWindowMs = 100;
    config.pairDistanceWindowMm = 4.0;
    config.phaseTimeoutMs = 1000;
    config.totalTimeoutMs = 5000;
    config.maximumSearchDistanceMm = 2000;
    config.bottomOffsetMm = 5;
    config.topOffsetMm = 5;
    return config;
}

void test_two_pass_bottom_and_top_homing_success() {
    EventCollector sink;
    HomingController homing(fastConfig());
    TEST_ASSERT_EQUAL(HomingPhase::BottomCoarse, homing.start(0, 100, sensors(false, false, false, false), sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::BottomCreep, homing.update(10, 50, sensors(true, false, false, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::BottomCreep, homing.update(15, 49, sensors(true, false, false, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::BottomBackoff, homing.update(20, 48, sensors(true, true, false, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::BottomFine, homing.update(40, 57, sensors(false, false, false, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::BottomFine, homing.update(50, 51, sensors(false, true, false, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::TopCoarse, homing.update(55, 50, sensors(true, true, false, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::TopCreep, homing.update(100, 990, sensors(false, false, true, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::TopCreep, homing.update(105, 991, sensors(false, false, true, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::TopBackoff, homing.update(110, 992, sensors(false, false, true, true), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::TopFine, homing.update(130, 983, sensors(false, false, false, false), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::TopFine, homing.update(140, 989, sensors(false, false, false, true), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::ApplyTopOffset, homing.update(145, 990, sensors(false, false, true, true), false, false, sink).phase);
    TEST_ASSERT_EQUAL(HomingPhase::Complete, homing.update(150, 985, sensors(false, false, false, false), false, false, sink).phase);
    TEST_ASSERT_TRUE(homing.result().known);
    TEST_ASSERT_DOUBLE_WITHIN(0.001, 55.0, homing.result().workingBottomMm);
    TEST_ASSERT_DOUBLE_WITHIN(0.001, 985.0, homing.result().workingTopMm);
    TEST_ASSERT_DOUBLE_WITHIN(0.001, 930.0, homing.result().travelMm);
}

void test_pair_timeout_fault_and_stop_abort() {
    EventCollector sink;
    HomingController mismatch(fastConfig());
    mismatch.start(0, 100, sensors(false, false, false, false), sink);
    mismatch.update(10, 50, sensors(true, false, false, false), false, false, sink);
    mismatch.update(20, 49, sensors(true, false, false, false), false, false, sink);
    const auto fault = mismatch.update(121, 48, sensors(true, false, false, false), false, false, sink);
    TEST_ASSERT_EQUAL(HomingPhase::Fault, fault.phase);
    TEST_ASSERT_EQUAL(FaultCode::RightBottomStuck, fault.fault);
    TEST_ASSERT_TRUE(fault.motion.stop);

    HomingController stopped(fastConfig());
    stopped.start(0, 100, sensors(false, false, false, false), sink);
    const auto aborted = stopped.update(5, 99, sensors(false, false, false, false), true, false, sink);
    TEST_ASSERT_EQUAL(HomingPhase::Aborted, aborted.phase);
    TEST_ASSERT_EQUAL(FaultCode::EmergencyStop, aborted.fault);
    TEST_ASSERT_TRUE(aborted.motion.stop);
}

void test_backoff_requires_both_sensors_to_release() {
    EventCollector sink;
    auto config = fastConfig();
    HomingController homing(config);
    homing.start(0, 100, sensors(true, true, false, false), sink);
    const auto fault = homing.update(50, 82, sensors(true, false, false, false), false, false, sink);
    TEST_ASSERT_EQUAL(HomingPhase::Fault, fault.phase);
    TEST_ASSERT_EQUAL(FaultCode::BackoffReleaseFailed, fault.fault);
}

void test_coarse_to_creep_preserves_first_edge_window_until_pair() {
    EventCollector sink;
    HomingController homing(fastConfig());
    homing.start(0, 100, sensors(false, false, false, false), sink);
    TEST_ASSERT_EQUAL(
        HomingPhase::BottomCreep,
        homing.update(10, 50, sensors(true, false, false, false), false, false, sink).phase
    );
    const auto latePair = homing.update(110, 49, sensors(true, true, false, false), false, false, sink);
    TEST_ASSERT_EQUAL(HomingPhase::Fault, latePair.phase);
    TEST_ASSERT_EQUAL(FaultCode::BottomPairTimeout, latePair.fault);
}

void setUp() {}
void tearDown() {}
int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_two_pass_bottom_and_top_homing_success);
    RUN_TEST(test_pair_timeout_fault_and_stop_abort);
    RUN_TEST(test_backoff_requires_both_sensors_to_release);
    RUN_TEST(test_coarse_to_creep_preserves_first_edge_window_until_pair);
    return UNITY_END();
}
