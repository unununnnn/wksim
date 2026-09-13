# GridMap cloud probe

This target is a create-only ROS1 validation probe for the frozen
`ego-single-box-v1` GridMap boundary. It links the already-built `plan_env`
library and calls only its public `GridMap` API. `GridMap::initMap` owns the
actual `grid_map/cloud` and `grid_map/odom` subscriptions, so the occupancy
queries are driven by product callbacks from ROS messages. The probe does not
start `roscore`, a planner, a publisher, a flight controller, or a command
stream.

Build it from an already sourced ROS1/catkin environment in which the real
`plan_env` package is built:

```bash
source /opt/ros/noetic/setup.bash
source /path/to/the/catkin_ws/devel/setup.bash
cmake -S validation/gridmap_cloud_probe -B /tmp/wksim-gridmap-cloud-probe
cmake --build /tmp/wksim-gridmap-cloud-probe --parallel
```

The owning session must start its isolated ROS master and load the existing
`advanced_param_wksim_single_box.xml` values into the private namespace
`/uav1_ego_planner_node` without launching the planner. The GridMap-required
values are `grid_map/resolution=0.1`, `map_size_x/y/z=20/12/6`,
`map_origin_x/y=-10/-6`, `local_update_range_x/y/z=9/7/6`,
`obstacles_inflation=0.8`, `ground_height=0`, `virtual_ceil_height=5.5`,
`skip_pixel=2`, `pose_type=2`, and `frame_id=world`; load the complete
parameter block from
`Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/advanced_param_wksim_single_box.xml`
when preparing the session. For a parameter-only load that does not launch
the `<node>` in that file, run this in the already-running isolated master
(with `WKSIM_ROOT` set to the checkout path):

```bash
export WKSIM_ROOT=/path/to/wksim
python3 - "$WKSIM_ROOT/Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/advanced_param_wksim_single_box.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET
import rospy

rospy.init_node("gridmap_param_loader", anonymous=False, disable_signals=True)
for param in ET.parse(sys.argv[1]).getroot().find("node").findall("param"):
    kind = param.attrib["type"]
    value = param.attrib["value"]
    if kind == "int":
        value = int(value)
    elif kind == "double":
        value = float(value)
    elif kind == "bool":
        value = value.lower() == "true"
    rospy.set_param("/uav1_ego_planner_node/" + param.attrib["name"], value)
PY
```

The probe itself reads these external parameters through
`ros::NodeHandle("~")` and does not recreate them.

Run it with private remaps to the fixed input topics. The `~` source names are
intentional: they match the private names used by `GridMap::initMap`.

```bash
/tmp/wksim-gridmap-cloud-probe/gridmap_cloud_probe \
  __name:=uav1_ego_planner_node \
  ~grid_map/cloud:=/map_generator/global_cloud \
  ~grid_map/odom:=/uav1/prometheus/odom \
  _probe_timeout_s:=30.0 _probe_rate_hz:=100.0
```

The cloud publisher must send the frozen 11,000 point `sensor_msgs/PointCloud2`
payload on `/map_generator/global_cloud` with frame `world`; odometry must
provide the real contract start pose `(-4, 0, 3)` on the remapped odom topic.
Keep both inputs alive until the probe exits, or use a latched publisher. The
probe uses `ros::WallTime` and `ros::WallRate`, so a frozen `/clock` cannot
extend or prevent its deadline.

The process writes exactly one JSON result line to stdout. Before any map
query, it requires product `odomValid()` and a cloud contract that has exactly
three ordered `x/y/z` `FLOAT32` fields at offsets `0/4/8`, little-endian
encoding, `point_step=12`, no row padding, and an exactly sized payload. Every
point is decoded as XYZ32 and checked against the complete unique profile
voxel set: x indices `95..104`, y indices `50..69`, z indices `0..54`, using
the float32 voxel-center values. NaN/Inf, wrong centers, duplicates, and
missing voxels fail the input gate. The JSON records these actual and expected
voxel counts along with resolved ROS topics, cloud/odom metadata, map geometry,
every requested coordinate with expected and actual occupancy, gate values,
and failure/pass status. The result is map-only evidence and carries explicit
limitations for flight, planner-output, and clearance claims.
