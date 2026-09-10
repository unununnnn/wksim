// SPDX-License-Identifier: Apache-2.0
// Humble rclpy exposes the subscription pointer, but drops the RMW writer GID.
// Called only while its Python handle is held, on an unspun receiver node.
#include <rcl/subscription.h>
#include <rcl/error_handling.h>
#include <rmw/types.h>
#include <rmw/serialized_message.h>
#include <cstring>

extern "C" size_t wksim_rc_gid_size() { return RMW_GID_STORAGE_SIZE; }

extern "C" int wksim_rc_take(
    const rcl_subscription_t * subscription, unsigned char * buffer, size_t capacity,
    size_t * size, unsigned char * gid, int64_t * source, int64_t * received)
{
    auto message = rmw_get_zero_initialized_serialized_message();
    auto allocator = rcutils_get_default_allocator();
    if (rmw_serialized_message_init(&message, capacity, &allocator) != RMW_RET_OK) return -1;
    rmw_message_info_t info{};
    auto status = rcl_take_serialized_message(subscription, &message, &info, nullptr);
    int result = 0;
    if (status == RCL_RET_OK) {
        *size = message.buffer_length;
        if (*size > capacity) result = -2;
        else {
            std::memcpy(buffer, message.buffer, *size);
            std::memcpy(gid, info.publisher_gid.data, RMW_GID_STORAGE_SIZE);
            *source = info.source_timestamp;
            *received = info.received_timestamp;
            result = 1;
        }
    } else if (status != RCL_RET_SUBSCRIPTION_TAKE_FAILED) result = -1;
    if (status != RCL_RET_OK) rcl_reset_error();
    if (rmw_serialized_message_fini(&message) != RMW_RET_OK) return -1;
    return result;
}
