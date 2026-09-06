cmake_minimum_required(VERSION 3.8)
project(wksim_msgs)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(prometheus_msgs REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/SetupRequest.msg"
  "msg/CommandRequest.msg"
  "msg/SessionState.msg"
  DEPENDENCIES prometheus_msgs
)
ament_export_dependencies(rosidl_default_runtime prometheus_msgs)
ament_package()
