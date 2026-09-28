#include "app/firmware_controller.hpp"

namespace {
egym::FirmwareConfig config;
egym::FirmwareController controller(config);
}  // namespace

void setup() {
    controller.begin();
}

void loop() {
    controller.tick();
    yield();
}
