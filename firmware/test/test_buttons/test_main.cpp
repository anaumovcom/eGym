#include <unity.h>

#include "core/button.hpp"
#include "../test_support.hpp"

using namespace egym;

void test_debounce_rejects_bounce_and_emits_edges() {
    EventCollector sink;
    ButtonBehavior behavior;
    behavior.debounceMs = 20;
    DebouncedButton button(ButtonId::Ok, behavior);

    button.update(true, 1, sink);
    button.update(false, 8, sink);
    button.update(true, 12, sink);
    button.update(true, 31, sink);
    TEST_ASSERT_EQUAL_UINT32(0, sink.events.size());
    button.update(true, 32, sink);
    TEST_ASSERT_EQUAL_UINT32(1, sink.events.size());
    TEST_ASSERT_EQUAL_STRING("pressed", sink.events[0].value.c_str());

    button.update(false, 40, sink);
    button.update(false, 60, sink);
    TEST_ASSERT_EQUAL_UINT32(2, sink.events.size());
    TEST_ASSERT_EQUAL_STRING("released", sink.events[1].value.c_str());
}

void test_long_press_and_accelerated_repeat() {
    EventCollector sink;
    ButtonBehavior behavior;
    behavior.debounceMs = 5;
    behavior.longPressMs = 50;
    behavior.repeat = true;
    behavior.repeatDelayMs = 30;
    behavior.repeatIntervalMs = 20;
    behavior.accelerationAfterMs = 70;
    behavior.acceleratedIntervalMs = 5;
    DebouncedButton button(ButtonId::LoadPlus, behavior);

    button.update(true, 0, sink);
    button.update(true, 5, sink);
    button.update(true, 35, sink);
    button.update(true, 55, sink);
    button.update(true, 75, sink);
    button.update(true, 80, sink);

    TEST_ASSERT_EQUAL_UINT32(6, sink.events.size());
    TEST_ASSERT_EQUAL_STRING("pressed", sink.events[0].value.c_str());
    TEST_ASSERT_EQUAL_STRING("repeat", sink.events[1].value.c_str());
    TEST_ASSERT_EQUAL_STRING("long_press", sink.events[2].value.c_str());
    TEST_ASSERT_EQUAL_STRING("repeat", sink.events[5].value.c_str());
}

void setUp() {}
void tearDown() {}
int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_debounce_rejects_bounce_and_emits_edges);
    RUN_TEST(test_long_press_and_accelerated_repeat);
    return UNITY_END();
}
