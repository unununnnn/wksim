cmake_minimum_required(VERSION 3.8)
project(prometheus_msgs)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "action/CheckForObjects.action"
  "msg/ArucoInfo.msg"
  "msg/BasicDataTypeAndValue.msg"
  "msg/BoundingBox.msg"
  "msg/BoundingBoxes.msg"
  "msg/Bspline.msg"
  "msg/Control.msg"
  "msg/CustomDataSegment.msg"
  "msg/DepthCompressed.msg"
  "msg/DetectionInfo.msg"
  "msg/DetectionInfoSub.msg"
  "msg/FormationAssign.msg"
  "msg/GPSData.msg"
  "msg/GimbalControl.msg"
  "msg/GimbalState.msg"
  "msg/GlobalAruco.msg"
  "msg/LinktrackNode2.msg"
  "msg/LinktrackNodeframe2.msg"
  "msg/LivoxCustomMsg.msg"
  "msg/LivoxCustomPoint.msg"
  "msg/MultiArucoInfo.msg"
  "msg/MultiBsplines.msg"
  "msg/MultiDetectionInfo.msg"
  "msg/MultiDetectionInfoSub.msg"
  "msg/MultiUAVState.msg"
  "msg/MultiUGVState.msg"
  "msg/OffsetPose.msg"
  "msg/ParamSettings.msg"
  "msg/PositionReference.msg"
  "msg/ROI.msg"
  "msg/StartScript.msg"
  "msg/StationCommand.msg"
  "msg/SwarmCommand.msg"
  "msg/Target.msg"
  "msg/TargetsInFrame.msg"
  "msg/TextInfo.msg"
  "msg/UAVCommand.msg"
  "msg/UAVControlState.msg"
  "msg/UAVSetup.msg"
  "msg/UAVState.msg"
  "msg/UGVCommand.msg"
  "msg/UGVState.msg"
  "msg/VisionDiff.msg"
  "msg/WindowPosition.msg"
  "srv/GetLocationSource.srv"
  "srv/GimbalFollowTrackResSevice.srv"
  "srv/SwitchLocationSource.srv"
  DEPENDENCIES builtin_interfaces std_msgs geometry_msgs sensor_msgs
)
ament_export_dependencies(rosidl_default_runtime)
install(FILES UPSTREAM.json LICENSE DESTINATION share/${PROJECT_NAME})
ament_package()
