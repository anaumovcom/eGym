#include "protocol.hpp"

#include <ArduinoJson.h>
#include <egym/version.hpp>

#include <cstdio>
#include <cstring>
#include <cmath>

namespace egym {
namespace {

CommandType parseCommand(const char* name) {
    if (name == nullptr) return CommandType::Invalid;
    const std::string command{name};
    if (command == "ping") return CommandType::Ping;
    if (command == "heartbeat") return CommandType::Heartbeat;
    if (command == "status") return CommandType::Status;
    if (command == "home") return CommandType::Home;
    if (command == "move") return CommandType::Move;
    if (command == "set_load") return CommandType::SetLoad;
    if (command == "start") return CommandType::Start;
    if (command == "pause") return CommandType::Pause;
    if (command == "stop") return CommandType::Stop;
    if (command == "clear_stop") return CommandType::ClearStop;
    if (command == "set_machine_state") return CommandType::SetMachineState;
    if (command == "led_test") return CommandType::LedTest;
    if (command == "input_test") return CommandType::InputTest;
    if (command == "i2c_test") return CommandType::I2cTest;
    if (command == "diagnostics") return CommandType::Diagnostics;
    if (command == "set_night_mode") return CommandType::SetNightMode;
    if (command == "firmware_info") return CommandType::FirmwareInfo;
    if (command == "position") return CommandType::PositionTelemetry;
    if (command == "drive_fault") return CommandType::DriveFault;
    if (command == "button_feedback") return CommandType::ButtonFeedback;
    if (command == "set_activity") return CommandType::SetActivity;
    if (command == "play_effect") return CommandType::PlayEffect;
    if (command == "set_brightness") return CommandType::SetBrightness;
    return CommandType::Invalid;
}

std::string escapeJson(const std::string& value) {
    std::string result;
    result.reserve(value.size() + 8);
    for (const char character : value) {
        switch (character) {
            case '\\': result += "\\\\"; break;
            case '"': result += "\\\""; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default: result += character; break;
        }
    }
    return result;
}

}  // namespace

const char* toString(CommandType command) {
    switch (command) {
        case CommandType::Invalid: return "invalid";
        case CommandType::Ping: return "ping";
        case CommandType::Heartbeat: return "heartbeat";
        case CommandType::Status: return "status";
        case CommandType::Home: return "home";
        case CommandType::Move: return "move";
        case CommandType::SetLoad: return "set_load";
        case CommandType::Start: return "start";
        case CommandType::Pause: return "pause";
        case CommandType::Stop: return "stop";
        case CommandType::ClearStop: return "clear_stop";
        case CommandType::SetMachineState: return "set_machine_state";
        case CommandType::LedTest: return "led_test";
        case CommandType::InputTest: return "input_test";
        case CommandType::I2cTest: return "i2c_test";
        case CommandType::Diagnostics: return "diagnostics";
        case CommandType::SetNightMode: return "set_night_mode";
        case CommandType::FirmwareInfo: return "firmware_info";
        case CommandType::PositionTelemetry: return "position";
        case CommandType::DriveFault: return "drive_fault";
        case CommandType::ButtonFeedback: return "button_feedback";
        case CommandType::SetActivity: return "set_activity";
        case CommandType::PlayEffect: return "play_effect";
        case CommandType::SetBrightness: return "set_brightness";
    }
    return "invalid";
}

ProtocolEngine::ProtocolEngine(ProtocolConfig config) : config_(config) {}

LineBufferResult BoundedLineBuffer::push(char value, std::string& line) {
    if (discardUntilNewline_) {
        if (value == '\n') {
            discardUntilNewline_ = false;
            return LineBufferResult::Overflow;
        }
        return LineBufferResult::None;
    }
    if (value == '\n') {
        line.swap(buffer_);
        buffer_.clear();
        if (!line.empty() && line.back() == '\r') line.pop_back();
        return LineBufferResult::Line;
    }
    if (buffer_.size() >= maximumLineLength_) {
        buffer_.clear();
        discardUntilNewline_ = true;
        return LineBufferResult::None;
    }
    buffer_ += value;
    return LineBufferResult::None;
}

ParseResult ProtocolEngine::parse(const std::string& line, Millis now) {
    if (line.empty() || line.size() > config_.maximumLineLength) {
        return {false, false, "invalid_length", {}};
    }

    JsonDocument document;
    const auto error = deserializeJson(document, line);
    if (error) return {false, false, error.c_str(), {}};
    if (!document.is<JsonObject>()) return {false, false, "object_required", {}};

    const int version = document["v"] | 0;
    if (version != EGYM_PROTOCOL_VERSION) return {false, false, "unsupported_version", {}};
    if (!document["seq"].is<std::uint32_t>()) return {false, false, "sequence_required", {}};
    const char* session = document["session"] | static_cast<const char*>(nullptr);
    if (session == nullptr || session[0] == '\0' || std::strlen(session) > 64U) {
        return {false, false, "session_required", {}};
    }

    ProtocolCommand result;
    result.sequence = document["seq"].as<std::uint32_t>();
    result.type = parseCommand(document["cmd"] | static_cast<const char*>(nullptr));
    if (result.type == CommandType::Invalid) return {false, false, "unknown_command", result};
    if (result.type == CommandType::ButtonFeedback &&
        (!document["request_seq"].is<std::uint32_t>() || document["request_seq"].as<std::uint32_t>() == 0U ||
         !document["accepted"].is<bool>() || !document["id"].is<const char*>())) {
        return {false, false, "invalid_button_feedback", result};
    }
    if (result.type == CommandType::ButtonFeedback) {
        bool known = false;
        for (std::size_t i = 0; i < kButtonCount; ++i) {
            if (std::strcmp(document["id"].as<const char*>(), toString(static_cast<ButtonId>(i))) == 0) known = true;
        }
        if (!known) return {false, false, "invalid_button_id", result};
    }
    if ((result.type == CommandType::SetActivity && !document["direction"].is<const char*>()) ||
        (result.type == CommandType::PlayEffect && !document["effect"].is<const char*>()) ||
        (result.type == CommandType::SetBrightness &&
            (!document["brightness"].is<double>() || !std::isfinite(document["brightness"].as<double>()) ||
             document["brightness"].as<double>() < 0.1 || document["brightness"].as<double>() > 1.0))) {
        return {false, false, "invalid_led_command", result};
    }
    if (result.type == CommandType::SetActivity) {
        const std::string direction = document["direction"].as<const char*>();
        if (direction != "up" && direction != "down" && direction != "stop") return {false, false, "invalid_direction", result};
    }
    if (result.type == CommandType::PlayEffect) {
        const std::string effect = document["effect"].as<const char*>();
        if (effect != "home_detected" && effect != "homing_complete" && effect != "target_reached" &&
            effect != "limit_triggered" && effect != "set_complete") return {false, false, "invalid_effect", result};
    }

    if (session_ != session) {
        session_ = session;
        haveRxSequence_ = false;
        connected_ = false;
    }

    if (haveRxSequence_ && result.sequence <= lastRxSequence_) {
        return {true, true, "", result};
    }
    haveRxSequence_ = true;
    lastRxSequence_ = result.sequence;

    if (document["position_mm"].is<double>()) result.value = document["position_mm"].as<double>();
    else if (document["kg"].is<double>()) result.value = document["kg"].as<double>();
    else if (document["brightness"].is<double>()) result.value = document["brightness"].as<double>();
    result.text = document["state"] | "";
    if (result.type == CommandType::ButtonFeedback) result.text = document["id"] | "";
    if (result.type == CommandType::SetActivity) result.text = document["direction"] | "";
    if (result.type == CommandType::PlayEffect) result.text = document["effect"] | "";
    result.flag = document["enabled"] | false;
    if (result.type == CommandType::ButtonFeedback) {
        result.flag = document["accepted"] | false;
        result.requestSequence = document["request_seq"] | 0U;
    }

    if (result.type == CommandType::Heartbeat || result.type == CommandType::Ping) {
        connected_ = true;
        lastHeartbeatAt_ = now;
    }
    return {true, false, "", result};
}

bool ProtocolEngine::updateHeartbeat(Millis now) {
    if (connected_ && static_cast<Millis>(now - lastHeartbeatAt_) > config_.heartbeatTimeoutMs) {
        connected_ = false;
        return false;
    }
    return connected_;
}

std::string ProtocolEngine::envelope(const std::string& type, const std::string& fields) {
    std::string result = "{\"v\":" + std::to_string(EGYM_PROTOCOL_VERSION) +
        ",\"seq\":" + std::to_string(nextTxSequence()) +
        ",\"type\":\"" + std::string(type) + "\"";
    if (!fields.empty()) {
        result += ",";
        result += fields;
    }
    result += "}\n";
    return result;
}

std::string ProtocolEngine::eventJson(const CoreEvent& event) {
    return envelope(event.type, "\"id\":\"" + escapeJson(event.id) + "\",\"event\":\"" + escapeJson(event.value) +
        "\",\"value\":" + std::to_string(event.number) + ",\"active\":" + (event.flag ? "true" : "false"));
}

std::string ProtocolEngine::stateJson(MachineState state) {
    return envelope("machine_state", "\"state\":\"" + std::string(toString(state)) + "\"");
}

std::string ProtocolEngine::faultJson(FaultCode fault, bool latched) {
    return envelope("fault", "\"code\":\"" + std::string(toString(fault)) + "\",\"latched\":" + (latched ? "true" : "false"));
}

std::string ProtocolEngine::positionJson(const PositionResult& position) {
    char fields[320];
    std::snprintf(fields, sizeof(fields), "\"known\":%s,\"mm\":%.3f,\"physical_bottom_mm\":%.3f,\"physical_top_mm\":%.3f,\"working_bottom_mm\":%.3f,\"working_top_mm\":%.3f,\"travel_mm\":%.3f",
        position.known ? "true" : "false", position.currentMm, position.physicalBottomMm, position.physicalTopMm,
        position.workingBottomMm, position.workingTopMm, position.travelMm);
    return envelope("position", fields);
}

std::string ProtocolEngine::pongJson(std::uint32_t requestSequence) {
    return envelope("pong", "\"request_seq\":" + std::to_string(requestSequence) + ",\"firmware\":\"" EGYM_FIRMWARE_VERSION "\"");
}

std::string ProtocolEngine::diagnosticJson(const std::string& subsystem, bool ok, const std::string& detail) {
    return envelope("diagnostic", "\"subsystem\":\"" + escapeJson(subsystem) + "\",\"ok\":" + (ok ? "true" : "false") +
        ",\"detail\":\"" + escapeJson(detail) + "\"");
}

std::string ProtocolEngine::versionJson() {
    return envelope("version", "\"firmware\":\"" EGYM_FIRMWARE_NAME "\",\"version\":\"" EGYM_FIRMWARE_VERSION "\",\"protocol\":" + std::to_string(EGYM_PROTOCOL_VERSION));
}

std::string ProtocolEngine::statusJson(
    MachineState state,
    FaultCode fault,
    bool stopLatched,
    bool inputHealthy,
    const std::array<bool, kButtonCount>& buttons,
    const SensorSnapshot& sensors,
    double positionMm
) {
    std::string buttonFields;
    for (std::size_t i = 0; i < kButtonCount; ++i) {
        if (!buttonFields.empty()) buttonFields += ',';
        buttonFields += "\"" + std::string(toString(static_cast<ButtonId>(i))) + "\":" + (buttons[i] ? "true" : "false");
    }
    std::string sensorFields;
    for (std::size_t i = 0; i < kSensorCount; ++i) {
        if (!sensorFields.empty()) sensorFields += ',';
        sensorFields += "\"" + std::string(toString(static_cast<SensorId>(i))) + "\":" + (sensors.active[i] ? "true" : "false");
    }
    char position[48];
    std::snprintf(position, sizeof(position), "%.3f", positionMm);
    return envelope(
        "status",
        "\"firmware\":\"" EGYM_FIRMWARE_NAME "\",\"version\":\"" EGYM_FIRMWARE_VERSION
        "\",\"protocol\":" + std::to_string(EGYM_PROTOCOL_VERSION) +
        ",\"machine_state\":\"" + std::string(toString(state)) +
        "\",\"fault\":\"" + std::string(toString(fault)) +
        "\",\"stop_latched\":" + (stopLatched ? "true" : "false") +
        ",\"input_healthy\":" + (inputHealthy ? "true" : "false") +
        ",\"buttons\":{" + buttonFields + "},\"sensors\":{" + sensorFields +
        "},\"bottom_pair\":" + (sensors.bottomPair() ? "true" : "false") +
        ",\"top_pair\":" + (sensors.topPair() ? "true" : "false") +
        ",\"position_mm\":" + position
    );
}

}  // namespace egym
