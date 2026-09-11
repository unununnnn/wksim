"""Launch the bridge after its ControlNode session and 1 ms /clock are live."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    required = {
        "run_id": "Non-empty public control-session run ID.",
        "mission_id": "Non-empty planner mission ID.",
        "fallback_yaw": "Finite map-ENU yaw in radians; EGO does not publish yaw.",
        "authority_anchor_ns": (
            "External /clock epoch anchor in nanoseconds, exactly aligned to 1 ms."
        ),
    }
    declarations = [
        DeclareLaunchArgument(name, description=description)
        for name, description in required.items()
    ]
    bridge = Node(
        package="prometheus_control",
        executable="trajectory_bridge_node",
        name="wksim_trajectory_bridge",
        output="screen",
        parameters=[{
            "run_id": LaunchConfiguration("run_id"),
            "uav_id": 1,
            "use_sim_time": True,
            "mission_id": LaunchConfiguration("mission_id"),
            "fallback_yaw": LaunchConfiguration("fallback_yaw"),
            "authority_anchor_ns": LaunchConfiguration("authority_anchor_ns"),
        }],
    )
    return LaunchDescription([*declarations, bridge])
