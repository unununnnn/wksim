"""Native DDS flight-control diagnostic, not the Prometheus application adapter.

The mission runner retains MAVLink as an independent telemetry observer only.
PX4 commands use its exact versioned uORB ROS schemas. ArduCopter uses native
services and its global-position topic. No MAVLink control fallback exists here.
"""
import json
import math
import time


def enu_to_ned(vector):
    return [vector[1], vector[0], -vector[2]]


def angle_error(actual, target):
    if not math.isfinite(actual) or not math.isfinite(target):
        raise ValueError("Yaw comparison requires finite angles")
    return abs(math.atan2(math.sin(actual - target), math.cos(actual - target)))


def ned_yaw_to_enu(yaw):
    if not math.isfinite(yaw):
        raise ValueError("DDS heading must be finite")
    return math.atan2(math.cos(yaw), math.sin(yaw))


def quaternion_yaw(q):
    values = (q.x, q.y, q.z, q.w)
    norm = sum(v * v for v in values)
    if not all(math.isfinite(v) for v in values) or not math.isfinite(norm) or norm < 1e-12:
        raise ValueError("Invalid DDS orientation quaternion")
    return math.atan2(2 * (q.w * q.z + q.x * q.y), norm - 2 * (q.y * q.y + q.z * q.z))


def offset_latlon(latitude, longitude, north, east):
    """Small local test offset, metres, WGS84 equatorial radius; not navigation."""
    return (latitude + math.degrees(north / 6378137.0),
            longitude + math.degrees(east / (6378137.0 * math.cos(math.radians(latitude)))))


def px4_topic(direction, name, message_type):
    version = getattr(message_type, "MESSAGE_VERSION", 0)
    return f"/wksim_px4_21/fmu/{direction}/{name}" + (f"_v{version}" if version else "")


class NativeDDS:
    def __init__(self, stack, result_dir, *, state_extension=False):
        import rclpy
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rosidl_runtime_py.convert import message_to_ordereddict

        self.ros = rclpy
        self.to_dict = message_to_ordereddict
        self.is_ap = stack == "arducopter"
        self.latest, self.received_at, self.counts, self.topics = {}, {}, {}, {}
        self.commands, self.positions = [], []
        self.failsafe_observed = False
        self.setpoint = None
        self.target_yaw_enu = None
        self.last_send = 0.0
        self.pending = None
        self.started = time.monotonic()
        self.log = (result_dir / "dds.jsonl").open("x", encoding="utf-8", buffering=1)
        rclpy.init(args=[])
        self.node = rclpy.create_node(f"wksim_{stack}_native_validation")
        self.subscriptions = []
        self.publishers = {}
        self.services = {}
        sensor_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                                durability=DurabilityPolicy.VOLATILE)

        def subscribe(key, cls, topic):
            self.topics[key] = topic
            self.subscriptions.append(self.node.create_subscription(cls, topic,
                                      lambda msg: self.receive(key, msg), sensor_qos))

        if self.is_ap:
            from ardupilot_msgs.msg import Status, GlobalPosition
            from ardupilot_msgs.srv import ArmMotors, ModeSwitch, Takeoff
            from geometry_msgs.msg import PoseStamped, TwistStamped
            from geographic_msgs.msg import GeoPointStamped
            subscribe("status", Status, "/ap/status")
            subscribe("position", PoseStamped, "/ap/pose/filtered")
            subscribe("velocity", TwistStamped, "/ap/twist/filtered")
            subscribe("origin", GeoPointStamped, "/ap/gps_global_origin/filtered")
            if state_extension:
                from ardupilot_msgs.msg import WksimState
                subscribe("wksim_state", WksimState, "/ap/wksim/local_state_v1")
            self.position_type = GlobalPosition
            self.publishers["position"] = self.node.create_publisher(GlobalPosition, "/ap/cmd_gps_pose", 10)
            for key, cls, topic in (("arm", ArmMotors, "/ap/arm_motors"),
                                    ("mode", ModeSwitch, "/ap/mode_switch"),
                                    ("takeoff", Takeoff, "/ap/experimental/takeoff")):
                self.services[key] = (self.node.create_client(cls, topic), cls)
        else:
            from px4_msgs.msg import (VehicleStatus, VehicleLocalPosition, VehicleCommandAck, FailsafeFlags, TimesyncStatus,
                                      OffboardControlMode, TrajectorySetpoint, VehicleCommand)
            subscribe("status", VehicleStatus, px4_topic("out", "vehicle_status", VehicleStatus))
            subscribe("position", VehicleLocalPosition, px4_topic("out", "vehicle_local_position", VehicleLocalPosition))
            subscribe("ack", VehicleCommandAck, px4_topic("out", "vehicle_command_ack", VehicleCommandAck))
            subscribe("failsafe_flags", FailsafeFlags, px4_topic("out", "failsafe_flags", FailsafeFlags))
            subscribe("timesync", TimesyncStatus, px4_topic("out", "timesync_status", TimesyncStatus))
            self.position_type, self.offboard_type, self.command_type = TrajectorySetpoint, OffboardControlMode, VehicleCommand
            for key, cls, name in (("position", TrajectorySetpoint, "trajectory_setpoint"),
                                    ("offboard", OffboardControlMode, "offboard_control_mode"),
                                    ("command", VehicleCommand, "vehicle_command")):
                self.publishers[key] = self.node.create_publisher(cls, px4_topic("in", name, cls), 1)

    def receive(self, key, message):
        self.latest[key] = message
        self.received_at[key] = time.monotonic()
        self.counts[key] = self.counts.get(key, 0) + 1
        self.log.write(json.dumps({"wall": time.monotonic() - self.started, "topic": self.topics[key],
                                   "message": self.to_dict(message)}) + "\n")
        if key == "position":
            self.positions.append(self.position_ned)
        if not self.is_ap and key == "status" and message.failsafe and self.armed:
            self.failsafe_observed = True

    @property
    def position_ned(self):
        msg = self.latest["position"]
        return enu_to_ned([msg.pose.position.x, msg.pose.position.y, msg.pose.position.z]) if self.is_ap else [msg.x, msg.y, msg.z]

    @property
    def armed(self):
        msg = self.latest["status"]
        return msg.armed if self.is_ap else msg.arming_state == msg.ARMING_STATE_ARMED

    @property
    def yaw_enu(self):
        msg = self.latest["position"]
        return quaternion_yaw(msg.pose.orientation) if self.is_ap else ned_yaw_to_enu(msg.heading)

    def ready(self):
        required = ("status", "position", "velocity", "origin") if self.is_ap else ("status", "position")
        if not all(key in self.latest for key in required):
            return False
        if not all(pub.get_subscription_count() for pub in self.publishers.values()):
            return False
        if not all(client.service_is_ready() for client, _ in self.services.values()):
            return False
        if not self.is_ap:
            status, pos = self.latest["status"], self.latest["position"]
            if status.system_id != 22:
                raise RuntimeError(f"Unexpected DDS PX4 system ID {status.system_id}")
            if not 0 < pos.timestamp < 10**12:
                raise RuntimeError("Expected PX4 simulation microseconds with UXRCE_DDS_SYNCT=0")
            return pos.xy_valid and pos.z_valid
        return True

    def mode_confirmed(self, mode):
        status = self.latest["status"]
        return status.mode == mode if self.is_ap else status.nav_state == {
            6: status.NAVIGATION_STATE_OFFBOARD, 3: status.NAVIGATION_STATE_POSCTL}[mode]

    def command(self, command_id, parameters):
        self.latest.pop("ack", None)
        record = {"command_id": command_id, "parameters": parameters, "wall": time.monotonic() - self.started}
        if self.is_ap:
            if command_id == 400:
                key, fields = "arm", {"arm": bool(parameters[0])}
            elif command_id == 176:
                key, fields = "mode", {"mode": int(parameters[1])}
            elif command_id == 22:
                key, fields = "takeoff", {"alt": float(parameters[6])}
            elif command_id == 21:
                key, fields = "mode", {"mode": 9}  # ArduCopter LAND.
            else:
                raise ValueError(f"Unsupported native ArduCopter diagnostic command {command_id}")
            client, cls = self.services[key]
            request = cls.Request(**fields)
            self.pending = client.call_async(request)
            record.update(transport="ros2_service", endpoint=client.srv_name, request=self.to_dict(request))
        else:
            msg = self.command_type(timestamp=self.px4_timestamp(),
                                    command=command_id, target_system=22, target_component=1,
                                    source_system=245, source_component=191, from_external=True)
            for index, value in enumerate(parameters, 1):
                setattr(msg, f"param{index}", float(value))
            self.publishers["command"].publish(msg)
            record.update(transport="ros2_topic", endpoint=self.publishers["command"].topic_name,
                          request=self.to_dict(msg))
        self.commands.append(record)

    def command_done(self):
        if self.is_ap:
            return self.pending is not None and self.pending.done()
        ack = self.latest.get("ack")
        return (ack is not None and ack.command == self.commands[-1]["command_id"]
                and ack.target_system == 245 and ack.target_component == 191)

    def check_command(self):
        response = self.pending.result() if self.is_ap else self.latest["ack"]
        self.commands[-1]["response"] = self.to_dict(response)
        accepted = (getattr(response, "status", getattr(response, "result", False)) if self.is_ap else response.result == 0)
        if not accepted:
            raise RuntimeError(f"Native DDS command rejected: {self.commands[-1]}")

    def pump(self):
        # Drain high-rate native messages without a background executor/thread.
        for _ in range(20):
            self.ros.spin_once(self.node, timeout_sec=0)
        now = time.monotonic()
        if self.setpoint is None or now - self.last_send < (0.2 if self.is_ap else 0.025):
            return
        self.last_send = now
        stamp = self.node.get_clock().now()
        if self.is_ap:
            origin = self.latest["origin"].position
            lat, lon = offset_latlon(origin.latitude, origin.longitude, *self.setpoint[:2])
            msg = self.position_type(coordinate_frame=6, type_mask=0xDF8,
                                     latitude=lat, longitude=lon, altitude=float(-self.setpoint[2]))
            if self.target_yaw_enu is not None:
                if not math.isfinite(self.target_yaw_enu):
                    raise ValueError("Diagnostic target yaw must be finite")
                msg.type_mask &= ~msg.IGNORE_YAW
                msg.yaw = float(self.target_yaw_enu)
            msg.header.frame_id = "map"
            msg.header.stamp = stamp.to_msg()
        else:
            timestamp = self.px4_timestamp()
            self.publishers["offboard"].publish(self.offboard_type(timestamp=timestamp, position=True))
            msg = self.position_type(timestamp=timestamp, position=[float(v) for v in self.setpoint],
                                     velocity=[math.nan] * 3, acceleration=[math.nan] * 3,
                                     jerk=[math.nan] * 3, yaw=0.0, yawspeed=math.nan)
        self.publishers["position"].publish(msg)
        self.log.write(json.dumps({"wall": now - self.started, "published": self.publishers["position"].topic_name,
                                   "message": self.to_dict(msg), "ros_time_us": stamp.nanoseconds // 1000,
                                   "px4_position_timestamp": None if self.is_ap else self.latest["position"].timestamp}) + "\n")
        self.counts["setpoints_sent"] = self.counts.get("setpoints_sent", 0) + 1

    def px4_timestamp(self):
        # Each FC owns its simulation clock. A 3x SITL clock must not be replaced
        # with the Agent wall clock; the launcher disables UXRCE_DDS_SYNCT.
        if time.monotonic() - self.received_at.get("position", 0) > 2:
            raise RuntimeError("Cannot command PX4 with a stale simulation timestamp")
        return self.latest["position"].timestamp

    def assert_fresh(self):
        for key in ("position", "status"):
            if time.monotonic() - self.received_at.get(key, 0) > 2:
                raise RuntimeError(f"Native DDS {key} is missing/stale >2 wall seconds")

    def snapshot(self):
        return {"position_ned": self.position_ned, "armed": self.armed,
                "yaw_enu_rad": self.yaw_enu,
                "status": self.to_dict(self.latest["status"])}

    def report(self):
        return {"topics": self.topics, "received_counts": self.counts, "commands": self.commands,
                "failsafe_observed_while_armed": self.failsafe_observed,
                "graph_topics": self.node.get_topic_names_and_types(),
                "graph_services": self.node.get_service_names_and_types(),
                "position_samples": len(self.positions),
                "max_height_m": max((-p[2] for p in self.positions), default=None),
                "final": self.snapshot() if "status" in self.latest and self.positions else None,
                "min_waypoint_error_m": min((math.dist(p, [3, 2, -3]) for p in self.positions), default=None)}

    def close(self):
        self.node.destroy_node()
        self.ros.shutdown()
        self.log.close()
