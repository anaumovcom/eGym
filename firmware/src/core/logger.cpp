#include "logger.hpp"

#include <utility>

namespace egym {

const char* toString(LogLevel level) {
    switch (level) {
        case LogLevel::Debug: return "debug";
        case LogLevel::Info: return "info";
        case LogLevel::Warning: return "warning";
        case LogLevel::Error: return "error";
        case LogLevel::Critical: return "critical";
    }
    return "unknown";
}

void StructuredLogger::push(Millis timestamp, LogLevel level, std::string component, std::string message) {
    if (size_ == kCapacity) {
        tail_ = (tail_ + 1) % kCapacity;
        --size_;
        ++dropped_;
    }
    records_[head_] = {timestamp, level, std::move(component), std::move(message)};
    head_ = (head_ + 1) % kCapacity;
    ++size_;
}

bool StructuredLogger::pop(LogRecord& record) {
    if (size_ == 0) return false;
    record = std::move(records_[tail_]);
    tail_ = (tail_ + 1) % kCapacity;
    --size_;
    return true;
}

}  // namespace egym
