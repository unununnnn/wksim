cmake_minimum_required(VERSION 3.8)
project(prometheus_control)
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(prometheus_msgs REQUIRED)
find_package(wksim_msgs REQUIRED)
find_package(rcl REQUIRED)
find_package(rmw REQUIRED)
ament_get_python_install_dir(PYTHON_INSTALL_DIR)
add_library(wksim_rc_take SHARED src/rc_take.cpp)
ament_target_dependencies(wksim_rc_take rcl rmw)
install(TARGETS wksim_rc_take LIBRARY DESTINATION lib)
ament_python_install_package(${PROJECT_NAME})
# Simulator and wksim_planning are intentional PEP 420 namespace packages.
install(
  FILES
    ../../../Simulator/wksim_runtime/__init__.py
    ../../../Simulator/wksim_runtime/task.py
    ../../../Simulator/wksim_runtime/trajectory_bridge.py
  DESTINATION ${PYTHON_INSTALL_DIR}/Simulator/wksim_runtime
)
install(
  FILES
    ../../../Simulator/wksim_planning/ego_bspline_bridge.py
    ../../../Simulator/wksim_planning/ego_evaluator.py
    ../../../Simulator/wksim_planning/ego_trajectory_adapter.py
    ../../../Simulator/wksim_planning/trajectory_session.py
  DESTINATION ${PYTHON_INSTALL_DIR}/Simulator/wksim_planning
)
install(
  PROGRAMS
    scripts/prometheus_control_node
    scripts/trajectory_bridge_node
  DESTINATION lib/${PROJECT_NAME}
)
install(
  DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
)
ament_export_dependencies(prometheus_msgs wksim_msgs)
ament_package()
