# Request IDs increase across setup and command inputs within one control epoch.
uint32 VERSION=1
uint32 version
string<=64 run_id
string<=32 control_epoch
uint64 request_id
prometheus_msgs/UAVCommand command
