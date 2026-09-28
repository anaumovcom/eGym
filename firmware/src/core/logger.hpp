#pragma once

#include "types.hpp"

#include <array>
#include <cstddef>
#include <string>

namespace egym {

enum class LogLevel : std::uint8_t { Debug, Info, Warning, Error, Critical };

struct LogRecord {
    Millis timestamp{0};
    LogLevel level{LogLevel::Info};
    std::string component;
    std::string message;
};

class StructuredLogger {
public:
    static constexpr std::size_t kCapacity = 32;

    void push(Millis timestamp, LogLevel level, std::string component, std::string message);
    bool pop(LogRecord& record);
    std::size_t dropped() const { return dropped_; }

private:
    std::array<LogRecord, kCapacity> records_{};
    std::size_t head_{0};
    std::size_t tail_{0};
    std::size_t size_{0};
    std::size_t dropped_{0};
};

const char* toString(LogLevel level);

}  // namespace egym
