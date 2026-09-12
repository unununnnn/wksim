#include <plan_env/grid_map.h>

#include <nav_msgs/Odometry.h>
#include <ros/ros.h>
#include <sensor_msgs/PointCloud2.h>

#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <exception>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr std::uint64_t kExpectedPointCount = 11000;
constexpr int kObstacleXMinIndex = 95;
constexpr int kObstacleXMaxIndex = 104;
constexpr int kObstacleYMinIndex = 50;
constexpr int kObstacleYMaxIndex = 69;
constexpr int kObstacleZMinIndex = 0;
constexpr int kObstacleZMaxIndex = 54;
constexpr std::uint64_t kExpectedVoxelCount =
    static_cast<std::uint64_t>(kObstacleXMaxIndex - kObstacleXMinIndex + 1) *
    static_cast<std::uint64_t>(kObstacleYMaxIndex - kObstacleYMinIndex + 1) *
    static_cast<std::uint64_t>(kObstacleZMaxIndex - kObstacleZMinIndex + 1);
constexpr double kExpectedResolution = 0.1;
constexpr double kExpectedMapOrigin[3] = {-10.0, -6.0, 0.0};
constexpr double kExpectedMapSize[3] = {20.0, 12.0, 6.0};
constexpr double kExpectedOdomPosition[3] = {-4.0, 0.0, 3.0};
constexpr double kGeometryTolerance = 1e-9;
constexpr double kOdomTolerance = 1e-3;
constexpr double kDefaultTimeoutSeconds = 30.0;
constexpr double kDefaultRateHz = 100.0;
constexpr double kMaximumTimeoutSeconds = 120.0;
constexpr double kMaximumRateHz = 1000.0;

struct ProbeObservation {
  bool map_initialized = false;
  bool map_init_complete = false;

  std::uint64_t cloud_messages = 0;
  std::uint64_t cloud_exact_messages = 0;
  bool cloud_count_match = false;
  bool cloud_frame_match = false;
  bool cloud_layout_valid = false;
  bool cloud_fields_valid = false;
  bool cloud_little_endian = false;
  bool cloud_length_exact = false;
  bool cloud_voxel_set_valid = false;
  bool cloud_contract_seen = false;
  bool cloud_after_map_init = false;
  std::uint32_t cloud_seq = 0;
  std::uint32_t cloud_width = 0;
  std::uint32_t cloud_height = 0;
  std::uint32_t cloud_point_step = 0;
  std::uint32_t cloud_row_step = 0;
  std::size_t cloud_data_bytes = 0;
  std::uint64_t cloud_point_count = 0;
  std::uint64_t cloud_unique_voxel_count = 0;
  std::uint64_t cloud_duplicate_voxel_count = 0;
  std::uint64_t cloud_invalid_point_count = 0;
  std::uint64_t cloud_nonfinite_point_count = 0;
  std::uint64_t cloud_missing_voxel_count = 0;
  std::string cloud_frame;
  ros::Time cloud_stamp;
  std::vector<std::string> cloud_fields;

  std::uint64_t odom_messages = 0;
  bool odom_seen = false;
  bool odom_pose_match = false;
  bool odom_pose_finite = false;
  std::uint32_t odom_seq = 0;
  std::string odom_frame;
  std::string odom_child_frame;
  ros::Time odom_stamp;
  std::array<double, 3> odom_position{{0.0, 0.0, 0.0}};

  bool product_odom_valid = false;
  std::string init_error;

  static float readLittleEndianFloat(const std::uint8_t* bytes) {
    const std::uint32_t bits = static_cast<std::uint32_t>(bytes[0]) |
                               (static_cast<std::uint32_t>(bytes[1]) << 8) |
                               (static_cast<std::uint32_t>(bytes[2]) << 16) |
                               (static_cast<std::uint32_t>(bytes[3]) << 24);
    float value = 0.0F;
    static_assert(sizeof(value) == sizeof(bits), "float32 is required");
    std::memcpy(&value, &bits, sizeof(value));
    return value;
  }

  static bool decodeVoxelIndex(float coordinate, double origin, int min_index,
                               int max_index, int& index) {
    if (!std::isfinite(coordinate)) {
      return false;
    }
    const double index_as_double =
        (static_cast<double>(coordinate) - origin) / kExpectedResolution - 0.5;
    const double rounded = std::round(index_as_double);
    if (!std::isfinite(index_as_double) ||
        std::abs(index_as_double - rounded) > 1e-5 ||
        rounded < static_cast<double>(min_index) ||
        rounded > static_cast<double>(max_index)) {
      return false;
    }
    index = static_cast<int>(rounded);
    const float expected_center = static_cast<float>(
        origin + (static_cast<double>(index) + 0.5) * kExpectedResolution);
    return coordinate == expected_center;
  }

  static std::size_t voxelAddress(int x, int y, int z) {
    const std::size_t y_size =
        static_cast<std::size_t>(kObstacleYMaxIndex - kObstacleYMinIndex + 1);
    return (static_cast<std::size_t>(x - kObstacleXMinIndex) * y_size +
            static_cast<std::size_t>(y - kObstacleYMinIndex)) *
               static_cast<std::size_t>(kObstacleZMaxIndex - kObstacleZMinIndex + 1) +
           static_cast<std::size_t>(z - kObstacleZMinIndex);
  }

  void cloudCallback(const sensor_msgs::PointCloud2ConstPtr& msg) {
    if (!msg) {
      return;
    }

    ++cloud_messages;
    cloud_seq = msg->header.seq;
    cloud_stamp = msg->header.stamp;
    cloud_frame = msg->header.frame_id;
    cloud_width = msg->width;
    cloud_height = msg->height;
    cloud_point_step = msg->point_step;
    cloud_row_step = msg->row_step;
    cloud_data_bytes = msg->data.size();
    cloud_point_count = static_cast<std::uint64_t>(msg->width) *
                        static_cast<std::uint64_t>(msg->height);
    cloud_fields.clear();
    cloud_fields.reserve(msg->fields.size());
    for (const sensor_msgs::PointField& field : msg->fields) {
      cloud_fields.push_back(field.name);
    }

    cloud_fields_valid = msg->fields.size() == 3 &&
                         msg->fields[0].name == "x" &&
                         msg->fields[0].offset == 0 &&
                         msg->fields[0].datatype == sensor_msgs::PointField::FLOAT32 &&
                         msg->fields[0].count == 1 &&
                         msg->fields[1].name == "y" &&
                         msg->fields[1].offset == 4 &&
                         msg->fields[1].datatype == sensor_msgs::PointField::FLOAT32 &&
                         msg->fields[1].count == 1 &&
                         msg->fields[2].name == "z" &&
                         msg->fields[2].offset == 8 &&
                         msg->fields[2].datatype == sensor_msgs::PointField::FLOAT32 &&
                         msg->fields[2].count == 1;
    cloud_little_endian = !msg->is_bigendian;
    const std::uint64_t expected_row_bytes =
        static_cast<std::uint64_t>(msg->width) * static_cast<std::uint64_t>(msg->point_step);
    const std::uint64_t expected_payload_bytes =
        static_cast<std::uint64_t>(msg->row_step) * static_cast<std::uint64_t>(msg->height);
    cloud_length_exact =
        static_cast<std::uint64_t>(msg->row_step) == expected_row_bytes &&
        expected_payload_bytes == static_cast<std::uint64_t>(msg->data.size());
    cloud_layout_valid = cloud_fields_valid && cloud_little_endian &&
                         msg->point_step == 12 && msg->width == kExpectedPointCount &&
                         msg->height == 1 && msg->row_step == msg->width * msg->point_step &&
                         cloud_length_exact;
    cloud_count_match = cloud_point_count == kExpectedPointCount;
    cloud_frame_match = cloud_frame == "world";
    if (cloud_count_match) {
      ++cloud_exact_messages;
    }
    cloud_unique_voxel_count = 0;
    cloud_duplicate_voxel_count = 0;
    cloud_invalid_point_count = 0;
    cloud_nonfinite_point_count = 0;
    cloud_missing_voxel_count = 0;
    cloud_voxel_set_valid = false;
    if (cloud_layout_valid) {
      std::vector<bool> seen(static_cast<std::size_t>(kExpectedVoxelCount), false);
      for (std::uint64_t point = 0; point < kExpectedPointCount; ++point) {
        const std::uint8_t* bytes = msg->data.data() + point * msg->point_step;
        const float x = readLittleEndianFloat(bytes);
        const float y = readLittleEndianFloat(bytes + 4);
        const float z = readLittleEndianFloat(bytes + 8);
        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
          ++cloud_nonfinite_point_count;
          ++cloud_invalid_point_count;
          continue;
        }
        int x_index = 0;
        int y_index = 0;
        int z_index = 0;
        if (!decodeVoxelIndex(x, kExpectedMapOrigin[0], kObstacleXMinIndex,
                              kObstacleXMaxIndex, x_index) ||
            !decodeVoxelIndex(y, kExpectedMapOrigin[1], kObstacleYMinIndex,
                              kObstacleYMaxIndex, y_index) ||
            !decodeVoxelIndex(z, kExpectedMapOrigin[2], kObstacleZMinIndex,
                              kObstacleZMaxIndex, z_index)) {
          ++cloud_invalid_point_count;
          continue;
        }
        const std::size_t address = voxelAddress(x_index, y_index, z_index);
        if (seen[address]) {
          ++cloud_duplicate_voxel_count;
        } else {
          seen[address] = true;
          ++cloud_unique_voxel_count;
        }
      }
      for (bool present : seen) {
        if (!present) {
          ++cloud_missing_voxel_count;
        }
      }
      cloud_voxel_set_valid = cloud_invalid_point_count == 0 &&
                              cloud_duplicate_voxel_count == 0 &&
                              cloud_missing_voxel_count == 0 &&
                              cloud_unique_voxel_count == kExpectedVoxelCount;
    }
    cloud_contract_seen = cloud_contract_seen ||
                          (cloud_count_match && cloud_frame_match && cloud_layout_valid &&
                           cloud_voxel_set_valid);
    if (map_init_complete) {
      cloud_after_map_init = true;
    }
  }

  void odomCallback(const nav_msgs::OdometryConstPtr& msg) {
    if (!msg) {
      return;
    }

    ++odom_messages;
    odom_seen = true;
    odom_seq = msg->header.seq;
    odom_stamp = msg->header.stamp;
    odom_frame = msg->header.frame_id;
    odom_child_frame = msg->child_frame_id;
    odom_position = {{msg->pose.pose.position.x,
                      msg->pose.pose.position.y,
                      msg->pose.pose.position.z}};
    odom_pose_finite = true;
    for (double coordinate : odom_position) {
      odom_pose_finite = odom_pose_finite && std::isfinite(coordinate);
    }
    odom_pose_match = odom_pose_finite;
    for (int axis = 0; axis < 3; ++axis) {
      odom_pose_match = odom_pose_match &&
                        std::abs(odom_position[axis] - kExpectedOdomPosition[axis]) <=
                            kOdomTolerance;
    }
  }
};

struct Query {
  double x;
  double y;
  double z;
  int expected;
  int actual = 0;
  bool has_actual = false;
};

std::array<Query, 8> makeQueries() {
  return {{{-4.0, 0.0, 3.0, 0},
            {4.0, 0.0, 3.0, 0},
            {0.0, 0.0, 3.0, 1},
            {-0.45, -0.95, 0.05, 1},
            {0.55, 1.05, 3.0, 1},
            {2.0, 3.0, 3.0, 0},
            {-10.0, -6.0, 0.0, -1},
            {10.0, 6.0, 6.0, -1}}};
}

void readQueries(GridMap* grid_map, std::array<Query, 8>& queries) {
  for (Query& query : queries) {
    query.has_actual = false;
    if (!grid_map) {
      continue;
    }
    query.actual = grid_map->getInflateOccupancy(
        Eigen::Vector3d(query.x, query.y, query.z));
    query.has_actual = true;
  }
}

void clearQueries(std::array<Query, 8>& queries) {
  for (Query& query : queries) {
    query.has_actual = false;
  }
}

bool queriesPass(const std::array<Query, 8>& queries) {
  for (const Query& query : queries) {
    if (!query.has_actual || query.actual != query.expected) {
      return false;
    }
  }
  return true;
}

bool closeTo(double actual, double expected, double tolerance) {
  return std::isfinite(actual) && std::abs(actual - expected) <= tolerance;
}

std::string jsonString(const std::string& value) {
  std::ostringstream out;
  out << '"';
  for (unsigned char character : value) {
    switch (character) {
      case '"': out << "\\\""; break;
      case '\\': out << "\\\\"; break;
      case '\b': out << "\\b"; break;
      case '\f': out << "\\f"; break;
      case '\n': out << "\\n"; break;
      case '\r': out << "\\r"; break;
      case '\t': out << "\\t"; break;
      default:
        if (character < 0x20) {
          out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
              << static_cast<int>(character) << std::dec << std::setfill(' ');
        } else {
          out << static_cast<char>(character);
        }
    }
  }
  out << '"';
  return out.str();
}

std::string jsonNumber(double value) {
  if (!std::isfinite(value)) {
    return "null";
  }
  std::ostringstream out;
  out << std::setprecision(17) << value;
  return out.str();
}

void writeStamp(std::ostream& out, const ros::Time& stamp) {
  out << "{\"sec\":" << stamp.sec << ",\"nsec\":" << stamp.nsec << '}';
}

void writeDoubleArray(std::ostream& out, const double* values, int count) {
  out << '[';
  for (int i = 0; i < count; ++i) {
    if (i != 0) {
      out << ',';
    }
    out << jsonNumber(values[i]);
  }
  out << ']';
}

void writeDoubleArray(std::ostream& out, const std::array<double, 3>& values) {
  writeDoubleArray(out, values.data(), static_cast<int>(values.size()));
}

void writeFields(std::ostream& out, const std::vector<std::string>& fields) {
  out << '[';
  for (std::size_t index = 0; index < fields.size(); ++index) {
    if (index != 0) {
      out << ',';
    }
    out << jsonString(fields[index]);
  }
  out << ']';
}

class StdoutSilencer {
 public:
  StdoutSilencer() : old_(std::cout.rdbuf(sink_.rdbuf())) {}
  ~StdoutSilencer() { std::cout.rdbuf(old_); }

 private:
  std::ostringstream sink_;
  std::streambuf* old_;
};

}  // namespace

int main(int argc, char** argv) {
  ros::init(argc, argv, "uav1_ego_planner_node");
  ros::NodeHandle nh("~");

  double timeout_seconds = kDefaultTimeoutSeconds;
  double rate_hz = kDefaultRateHz;
  nh.param("probe_timeout_s", timeout_seconds, kDefaultTimeoutSeconds);
  nh.param("probe_rate_hz", rate_hz, kDefaultRateHz);

  const bool timing_config_valid = std::isfinite(timeout_seconds) &&
                                   timeout_seconds > 0.0 &&
                                   timeout_seconds <= kMaximumTimeoutSeconds &&
                                   std::isfinite(rate_hz) && rate_hz > 0.0 &&
                                   rate_hz <= kMaximumRateHz;
  const ros::WallTime start_wall = ros::WallTime::now();
  const ros::WallTime deadline = timing_config_valid
                                     ? start_wall + ros::WallDuration(timeout_seconds)
                                     : start_wall;

  const std::string cloud_topic = nh.resolveName("grid_map/cloud");
  const std::string odom_topic = nh.resolveName("grid_map/odom");
  std::string configured_frame = "world";
  nh.param("grid_map/frame_id", configured_frame, std::string("world"));

  ProbeObservation observation;
  ros::Subscriber cloud_observer = nh.subscribe<sensor_msgs::PointCloud2>(
      "grid_map/cloud", 10, &ProbeObservation::cloudCallback, &observation);
  ros::Subscriber odom_observer = nh.subscribe<nav_msgs::Odometry>(
      "grid_map/odom", 10, &ProbeObservation::odomCallback, &observation);
  (void)cloud_observer;
  (void)odom_observer;

  std::unique_ptr<GridMap> grid_map;
  std::array<Query, 8> queries = makeQueries();
  Eigen::Vector3d map_origin = Eigen::Vector3d::Zero();
  Eigen::Vector3d map_size = Eigen::Vector3d::Zero();
  double map_resolution = 0.0;
  bool map_geometry_match = false;
  bool map_frame_match = configured_frame == "world";
  bool ros_shutdown_before_success = false;

  {
    // cloudCallback prints "no odom!" to std::cout on an early cloud.  Keep
    // the probe's result as exactly one JSON line without altering product code.
    StdoutSilencer silence_product_stdout;
    try {
      grid_map.reset(new GridMap);
      grid_map->initMap(nh);
      observation.map_initialized = true;
      observation.map_init_complete = true;

      map_origin = grid_map->getOrigin();
      grid_map->getRegion(map_origin, map_size);
      // getRegion writes both values; read the origin once more for clarity.
      map_origin = grid_map->getOrigin();
      map_resolution = grid_map->getResolution();
      map_geometry_match = closeTo(map_resolution, kExpectedResolution,
                                   kGeometryTolerance);
      for (int axis = 0; axis < 3; ++axis) {
        map_geometry_match = map_geometry_match &&
                             closeTo(map_origin(axis), kExpectedMapOrigin[axis],
                                     kGeometryTolerance) &&
                             closeTo(map_size(axis), kExpectedMapSize[axis],
                                     kGeometryTolerance);
      }
      map_geometry_match = map_geometry_match && map_frame_match;

      if (timing_config_valid) {
        ros::WallRate rate(rate_hz);
        while (ros::ok() && ros::WallTime::now() < deadline) {
          ros::spinOnce();
          observation.product_odom_valid = grid_map->odomValid();

          const bool latest_cloud_valid = observation.cloud_count_match &&
                                          observation.cloud_frame_match &&
                                          observation.cloud_layout_valid &&
                                          observation.cloud_voxel_set_valid;
          const bool query_ready = observation.product_odom_valid &&
                                   observation.cloud_contract_seen &&
                                   latest_cloud_valid;
          if (query_ready) {
            readQueries(grid_map.get(), queries);
          } else {
            clearQueries(queries);
          }
          if (observation.cloud_contract_seen && latest_cloud_valid &&
              observation.odom_seen && observation.odom_pose_match &&
              observation.product_odom_valid && map_geometry_match &&
              queriesPass(queries)) {
            break;
          }
          rate.sleep();
        }
        if (!ros::ok()) {
          ros_shutdown_before_success = true;
        }
      }
    } catch (const std::exception& error) {
      observation.init_error = error.what();
    } catch (...) {
      observation.init_error = "unknown exception while initializing GridMap";
    }

    if (grid_map) {
      observation.product_odom_valid = grid_map->odomValid();
      const bool latest_cloud_valid = observation.cloud_count_match &&
                                      observation.cloud_frame_match &&
                                      observation.cloud_layout_valid &&
                                      observation.cloud_voxel_set_valid;
      if (observation.product_odom_valid && observation.cloud_contract_seen &&
          latest_cloud_valid) {
        readQueries(grid_map.get(), queries);
      } else {
        clearQueries(queries);
      }
    }
  }

  const ros::WallDuration elapsed = ros::WallTime::now() - start_wall;
  const bool latest_cloud_valid = observation.cloud_count_match &&
                                  observation.cloud_frame_match &&
                                  observation.cloud_layout_valid &&
                                  observation.cloud_voxel_set_valid;
  const bool input_gate = observation.cloud_contract_seen && latest_cloud_valid &&
                          observation.odom_seen && observation.odom_pose_match;
  const bool pass = timing_config_valid && observation.map_initialized &&
                    input_gate && observation.product_odom_valid &&
                    map_geometry_match && queriesPass(queries) &&
                    !ros_shutdown_before_success;
  const bool timed_out = timing_config_valid && !pass &&
                         ros::WallTime::now() >= deadline;

  std::ostringstream result;
  result << '{';
  result << "\"schema\":\"wksim.gridmap-cloud-probe.v1\",";
  result << "\"result\":" << jsonString(pass ? "pass" : "fail") << ',';
  result << "\"node_name\":" << jsonString(ros::this_node::getName()) << ',';
  result << "\"expected_node_name\":\"/uav1_ego_planner_node\",";
  result << "\"wall_deadline_s\":" << jsonNumber(timeout_seconds) << ',';
  result << "\"wall_rate_hz\":" << jsonNumber(rate_hz) << ',';
  result << "\"elapsed_wall_s\":" << jsonNumber(elapsed.toSec()) << ',';
  result << "\"timing_config_valid\":" << (timing_config_valid ? "true" : "false") << ',';
  result << "\"timed_out\":" << (timed_out ? "true" : "false") << ',';
  result << "\"ros_shutdown_before_success\":"
         << (ros_shutdown_before_success ? "true" : "false") << ',';

  result << "\"ros_inputs\":{";
  result << "\"cloud_topic\":" << jsonString(cloud_topic) << ',';
  result << "\"odom_topic\":" << jsonString(odom_topic) << ',';
  result << "\"cloud\":{";
  result << "\"messages\":" << observation.cloud_messages << ',';
  result << "\"exact_point_count_messages\":" << observation.cloud_exact_messages << ',';
  result << "\"seq\":" << observation.cloud_seq << ',';
  result << "\"stamp\":";
  writeStamp(result, observation.cloud_stamp);
  result << ",\"frame_id\":" << jsonString(observation.cloud_frame) << ',';
  result << "\"expected_frame_id\":\"world\",";
  result << "\"width\":" << observation.cloud_width << ',';
  result << "\"height\":" << observation.cloud_height << ',';
  result << "\"point_count\":" << observation.cloud_point_count << ',';
  result << "\"expected_point_count\":" << kExpectedPointCount << ',';
  result << "\"unique_voxel_count\":" << observation.cloud_unique_voxel_count << ',';
  result << "\"expected_unique_voxel_count\":" << kExpectedVoxelCount << ',';
  result << "\"expected_voxel_index_bounds\":{";
  result << "\"x\":[" << kObstacleXMinIndex << ',' << kObstacleXMaxIndex << "],";
  result << "\"y\":[" << kObstacleYMinIndex << ',' << kObstacleYMaxIndex << "],";
  result << "\"z\":[" << kObstacleZMinIndex << ',' << kObstacleZMaxIndex << "]},";
  result << "\"duplicate_voxel_count\":" << observation.cloud_duplicate_voxel_count << ',';
  result << "\"invalid_point_count\":" << observation.cloud_invalid_point_count << ',';
  result << "\"nonfinite_point_count\":" << observation.cloud_nonfinite_point_count << ',';
  result << "\"missing_voxel_count\":" << observation.cloud_missing_voxel_count << ',';
  result << "\"point_step\":" << observation.cloud_point_step << ',';
  result << "\"row_step\":" << observation.cloud_row_step << ',';
  result << "\"data_bytes\":" << observation.cloud_data_bytes << ',';
  result << "\"fields\":";
  writeFields(result, observation.cloud_fields);
  result << ",\"count_match\":" << (observation.cloud_count_match ? "true" : "false");
  result << ",\"frame_match\":" << (observation.cloud_frame_match ? "true" : "false");
  result << ",\"layout_valid\":" << (observation.cloud_layout_valid ? "true" : "false");
  result << ",\"fields_valid\":" << (observation.cloud_fields_valid ? "true" : "false");
  result << ",\"little_endian\":" << (observation.cloud_little_endian ? "true" : "false");
  result << ",\"length_exact\":" << (observation.cloud_length_exact ? "true" : "false");
  result << ",\"voxel_set_valid\":"
         << (observation.cloud_voxel_set_valid ? "true" : "false");
  result << ",\"contract_seen\":" << (observation.cloud_contract_seen ? "true" : "false");
  result << ",\"seen_after_map_init\":"
         << (observation.cloud_after_map_init ? "true" : "false");
  result << "},\"odom\":{";
  result << "\"messages\":" << observation.odom_messages << ',';
  result << "\"seq\":" << observation.odom_seq << ',';
  result << "\"stamp\":";
  writeStamp(result, observation.odom_stamp);
  result << ",\"frame_id\":" << jsonString(observation.odom_frame) << ',';
  result << "\"child_frame_id\":" << jsonString(observation.odom_child_frame) << ',';
  result << "\"position\":";
  writeDoubleArray(result, observation.odom_position);
  result << ",\"expected_position\":";
  writeDoubleArray(result, kExpectedOdomPosition, 3);
  result << ",\"pose_match\":" << (observation.odom_pose_match ? "true" : "false");
  result << ",\"finite\":" << (observation.odom_pose_finite ? "true" : "false");
  result << "}},";

  result << "\"map\":{";
  result << "\"initialized\":" << (observation.map_initialized ? "true" : "false") << ',';
  result << "\"product_odom_valid\":" << (observation.product_odom_valid ? "true" : "false") << ',';
  result << "\"frame_id\":" << jsonString(configured_frame) << ',';
  result << "\"expected_frame_id\":\"world\",";
  result << "\"resolution\":" << jsonNumber(map_resolution) << ',';
  result << "\"expected_resolution\":" << jsonNumber(kExpectedResolution) << ',';
  result << "\"origin\":[" << jsonNumber(map_origin(0)) << ','
         << jsonNumber(map_origin(1)) << ',' << jsonNumber(map_origin(2)) << "],";
  result << "\"expected_origin\":";
  writeDoubleArray(result, kExpectedMapOrigin, 3);
  result << ",\"size\":[" << jsonNumber(map_size(0)) << ','
         << jsonNumber(map_size(1)) << ',' << jsonNumber(map_size(2)) << "],";
  result << "\"expected_size\":";
  writeDoubleArray(result, kExpectedMapSize, 3);
  result << ",\"geometry_match\":" << (map_geometry_match ? "true" : "false");
  result << ",\"frame_match\":" << (map_frame_match ? "true" : "false");
  result << "},";

  result << "\"queries\":[";
  for (std::size_t index = 0; index < queries.size(); ++index) {
    if (index != 0) {
      result << ',';
    }
    const Query& query = queries[index];
    result << "{\"coordinate\":[" << jsonNumber(query.x) << ','
           << jsonNumber(query.y) << ',' << jsonNumber(query.z) << "],";
    result << "\"expected\":" << query.expected << ',';
    result << "\"actual\":";
    if (query.has_actual) {
      result << query.actual;
    } else {
      result << "null";
    }
    result << ",\"pass\":" << (query.has_actual && query.actual == query.expected ? "true" : "false")
           << '}';
  }
  result << "],\"query_set_pass\":" << (queriesPass(queries) ? "true" : "false") << ',';

  result << "\"gates\":{";
  result << "\"cloud_received_11000\":"
         << (observation.cloud_contract_seen && observation.cloud_count_match ? "true" : "false") << ',';
  result << "\"cloud_frame_world\":" << (observation.cloud_frame_match ? "true" : "false") << ',';
  result << "\"cloud_layout_valid\":" << (observation.cloud_layout_valid ? "true" : "false") << ',';
  result << "\"cloud_xyz32_voxel_set\":"
         << (observation.cloud_voxel_set_valid ? "true" : "false") << ',';
  result << "\"odom_received\":" << (observation.odom_seen ? "true" : "false") << ',';
  result << "\"odom_at_contract_start\":" << (observation.odom_pose_match ? "true" : "false") << ',';
  result << "\"input_gate\":" << (input_gate ? "true" : "false") << ',';
  result << "\"map_only\":true";
  result << "},";

  result << "\"limitations\":["
         << "\"map-only probe; it does not start a ROS master or planner\","
         << "\"does not publish control state, flight-control commands, or odometry\","
         << "\"does not establish flight behavior, planner output, or clearance evidence\","
         << "\"cloud identity is checked here by ROS metadata/count/layout and map queries; the publisher owns profile/hash provenance\"]";
  if (!observation.init_error.empty()) {
    result << ",\"error\":" << jsonString(observation.init_error);
  }
  result << '}';

  std::cout << result.str() << '\n';
  return pass ? 0 : 2;
}
