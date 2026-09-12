cmake_minimum_required(VERSION 3.8)
project(gridmap_cloud_probe LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# This is intentionally a small standalone CMake target.  The real GridMap
# implementation is supplied by the already-built plan_env catkin package;
# this target does not compile or copy product sources.
find_package(catkin REQUIRED COMPONENTS
  nav_msgs
  pcl_ros
  pcl_conversions
  laser_geometry
  cv_bridge
  plan_env
  roscpp
  sensor_msgs
)
find_package(Eigen3 REQUIRED)

add_executable(gridmap_cloud_probe gridmap_cloud_probe.cpp)
target_include_directories(gridmap_cloud_probe PRIVATE
  ${catkin_INCLUDE_DIRS}
  ${plan_env_INCLUDE_DIRS}
  ${EIGEN3_INCLUDE_DIRS}
)
target_compile_options(gridmap_cloud_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(gridmap_cloud_probe PRIVATE
  ${catkin_LIBRARIES}
)
add_dependencies(gridmap_cloud_probe ${catkin_EXPORTED_TARGETS})
