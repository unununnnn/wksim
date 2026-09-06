# A new control-node process creates a new opaque epoch, not a physics reset.
uint32 VERSION=1
uint32 version
string<=64 run_id
string<=32 control_epoch
uint64 sequence
uint64 last_request_id
uint64 native_generation
# Source stamp stays in state.header; receive/publication use this WSL boot's monotonic clock.
string<=16 source_clock
bool source_received_valid
float64 source_received_monotonic_s
float64 published_monotonic_s
prometheus_msgs/UAVState state
prometheus_msgs/UAVControlState control
