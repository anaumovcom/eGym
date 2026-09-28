#include <unity.h>

#include "core/protocol.hpp"

using namespace egym;

void test_ping_connects_and_pong_preserves_request_sequence() {
    ProtocolConfig config;
    ProtocolEngine protocol(config);
    const auto parsed = protocol.parse(R"({"v":1,"seq":7,"session":"host-a","cmd":"ping"})", 100);
    TEST_ASSERT_TRUE(parsed.ok);
    TEST_ASSERT_EQUAL(CommandType::Ping, parsed.command.type);
    TEST_ASSERT_TRUE(protocol.connected());
    const auto pong = protocol.pongJson(parsed.command.sequence);
    TEST_ASSERT_NOT_EQUAL(std::string::npos, pong.find("\"type\":\"pong\""));
    TEST_ASSERT_NOT_EQUAL(std::string::npos, pong.find("\"request_seq\":7"));
}

void test_duplicate_sequence_is_idempotently_ignored() {
    ProtocolEngine protocol(ProtocolConfig{});
    TEST_ASSERT_TRUE(protocol.parse(R"({"v":1,"seq":4,"session":"host-a","cmd":"heartbeat"})", 0).ok);
    const auto duplicate = protocol.parse(R"({"v":1,"seq":4,"session":"host-a","cmd":"stop"})", 1);
    TEST_ASSERT_TRUE(duplicate.ok);
    TEST_ASSERT_TRUE(duplicate.duplicate);
}

void test_heartbeat_timeout_and_invalid_messages() {
    ProtocolConfig config;
    config.heartbeatTimeoutMs = 100;
    ProtocolEngine protocol(config);
    protocol.parse(R"({"v":1,"seq":1,"session":"host-a","cmd":"heartbeat"})", 10);
    TEST_ASSERT_TRUE(protocol.updateHeartbeat(110));
    TEST_ASSERT_FALSE(protocol.updateHeartbeat(111));
    TEST_ASSERT_FALSE(protocol.parse(R"({"v":2,"seq":2,"session":"host-a","cmd":"ping"})", 120).ok);
    TEST_ASSERT_FALSE(protocol.parse(R"({"v":1,"seq":2,"session":"host-a","cmd":"destroy"})", 120).ok);
    TEST_ASSERT_FALSE(protocol.parse(R"({"v":1,"seq":2,"cmd":"ping"})", 120).ok);
}

void test_command_payloads_and_event_encoding() {
    ProtocolEngine protocol(ProtocolConfig{});
    const auto move = protocol.parse(R"({"v":1,"seq":1,"session":"host-a","cmd":"move","position_mm":350.5})", 0);
    TEST_ASSERT_TRUE(move.ok);
    TEST_ASSERT_DOUBLE_WITHIN(0.001, 350.5, move.command.value);
    const auto event = protocol.eventJson({"button", "load_plus", "pressed", 0.0, true});
    TEST_ASSERT_NOT_EQUAL(std::string::npos, event.find("\"type\":\"button\""));
    TEST_ASSERT_EQUAL('\n', event.back());
}

void test_new_backend_session_resets_rx_sequence_and_processes_ping() {
    ProtocolEngine protocol(ProtocolConfig{});
    TEST_ASSERT_TRUE(protocol.parse(R"({"v":1,"seq":99,"session":"host-a","cmd":"heartbeat"})", 10).ok);
    const auto restarted = protocol.parse(R"({"v":1,"seq":1,"session":"host-b","cmd":"ping"})", 20);
    TEST_ASSERT_TRUE(restarted.ok);
    TEST_ASSERT_FALSE(restarted.duplicate);
    TEST_ASSERT_EQUAL(CommandType::Ping, restarted.command.type);
    TEST_ASSERT_TRUE(protocol.connected());
}

void test_led_feedback_command_requires_identity_and_valid_brightness() {
    ProtocolEngine protocol(ProtocolConfig{});
    const auto feedback = protocol.parse(R"({"v":1,"seq":1,"session":"host-a","cmd":"button_feedback","id":"up","request_seq":9,"accepted":true})", 1);
    TEST_ASSERT_TRUE(feedback.ok);
    TEST_ASSERT_EQUAL_UINT32(9, feedback.command.requestSequence);
    TEST_ASSERT_TRUE(feedback.command.flag);
    TEST_ASSERT_FALSE(protocol.parse(R"({"v":1,"seq":2,"session":"host-a","cmd":"button_feedback","id":"up","accepted":true})", 2).ok);
    TEST_ASSERT_FALSE(protocol.parse(R"({"v":1,"seq":3,"session":"host-a","cmd":"set_brightness","brightness":1.5})", 3).ok);
    const auto activity = protocol.parse(R"({"v":1,"seq":4,"session":"host-a","cmd":"set_activity","direction":"down"})", 4);
    TEST_ASSERT_TRUE(activity.ok);
    TEST_ASSERT_EQUAL_STRING("down", activity.command.text.c_str());
}

void test_overflow_discards_through_newline_without_executing_tail() {
    BoundedLineBuffer buffer(8);
    std::string line;
    const std::string physical = "123456789{\"cmd\":\"stop\"}\n";
    LineBufferResult result = LineBufferResult::None;
    for (const char value : physical) result = buffer.push(value, line);
    TEST_ASSERT_EQUAL(LineBufferResult::Overflow, result);
    TEST_ASSERT_TRUE(line.empty());

    const std::string valid = "{}\n";
    for (const char value : valid) result = buffer.push(value, line);
    TEST_ASSERT_EQUAL(LineBufferResult::Line, result);
    TEST_ASSERT_EQUAL_STRING("{}", line.c_str());
}

void setUp() {}
void tearDown() {}
int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_ping_connects_and_pong_preserves_request_sequence);
    RUN_TEST(test_duplicate_sequence_is_idempotently_ignored);
    RUN_TEST(test_heartbeat_timeout_and_invalid_messages);
    RUN_TEST(test_command_payloads_and_event_encoding);
    RUN_TEST(test_new_backend_session_resets_rx_sequence_and_processes_ping);
    RUN_TEST(test_led_feedback_command_requires_identity_and_valid_brightness);
    RUN_TEST(test_overflow_discards_through_newline_without_executing_tail);
    return UNITY_END();
}
