cmake_minimum_required(VERSION 3.8)
project(plan_env)

set(CMAKE_BUILD_TYPE "Release")
# The installed Noetic/log4cxx headers use std::shared_mutex (C++17).
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -Wall -g")

find_package(OpenCV REQUIRED)


find_package(catkin REQUIRED COMPONENTS
  roscpp
  rospy
  std_msgs
  visualization_msgs
  cv_bridge
  message_filters
  laser_geometry
  sensor_msgs
  prometheus_msgs
)

find_package(Eigen3 REQUIRED)
find_package(PCL 1.7 REQUIRED)

catkin_package(
 INCLUDE_DIRS include
 LIBRARIES plan_env
 CATKIN_DEPENDS roscpp std_msgs prometheus_msgs
 DEPENDS OpenCV
#  DEPENDS system_lib
)

include_directories( 
    SYSTEM 
    include 
    /home/amov/Prometheus/devel/include/prometheus_msgs/ParamSettings.h
    ${catkin_INCLUDE_DIRS}
    ${Eigen3_INCLUDE_DIRS} 
    ${PCL_INCLUDE_DIRS}
    ${OpenCV_INCLUDE_DIRS}
)

link_directories(${PCL_LIBRARY_DIRS})

add_library( plan_env 
    src/grid_map.cpp 
    src/raycast.cpp
    src/obj_predictor.cpp 
    )
add_dependencies(plan_env ${catkin_EXPORTED_TARGETS})
target_link_libraries( plan_env
    ${catkin_LIBRARIES} 
    ${PCL_LIBRARIES}
    ${OpenCV_LIBS}
    )  

add_executable(obj_generator
    src/obj_generator.cpp 
)
target_link_libraries(obj_generator 
    ${catkin_LIBRARIES}
    )

add_executable(laser_to_pointcloud
    src/laser_to_pointcloud.cpp 
)
target_link_libraries(laser_to_pointcloud 
    ${catkin_LIBRARIES}
    )
add_executable(su17_depth_to_cloud
    src/su17_depth_to_cloud.cpp 
)
target_link_libraries(su17_depth_to_cloud 
    ${catkin_LIBRARIES}
    ${OpenCV_LIBRARIES}
    ${PCL_LIBRARIES}
    )
    
add_executable(su17_rvl_encoder src/su17_rvl_encoder.cpp)
target_link_libraries(su17_rvl_encoder
  ${catkin_LIBRARIES}
  ${OpenCV_LIBS}
  ${PCL_LIBRARIES}
)

add_executable(su17_rvl_decoder src/su17_rvl_decoder.cpp)
target_link_libraries(su17_rvl_decoder
  ${catkin_LIBRARIES}
  ${OpenCV_LIBS}
  ${PCL_LIBRARIES}
)

foreach(message_consumer obj_generator laser_to_pointcloud su17_depth_to_cloud
                         su17_rvl_encoder su17_rvl_decoder)
  add_dependencies(${message_consumer} ${catkin_EXPORTED_TARGETS})
endforeach()
    
